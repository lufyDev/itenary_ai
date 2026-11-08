"""Timed day schedules: format, travel-time preferences, and the checks code
can do without an LLM.

A day used to be three free-text slots (morning / afternoon / evening). The
planner wrote "bus leaves at 18:00" under MORNING and "arrive at 05:30" under
AFTERNOON of the same day, and an overnight bus had no honest place to go.
Each day is now a list of entries with a start and end time, so an overnight
leg is one entry whose end time is earlier than its start (it ran past
midnight), and the next day can't begin before it arrives.
"""

ENTRY_KINDS = ["travel", "activity", "meal", "rest"]

# When the group wants to leave the source city, and when they want to be back
# there at the end. "any" means no preference.
TIME_PREFERENCES = ["morning", "afternoon", "evening", "any"]

# Inclusive minute ranges. Together they cover 04:00 to 23:59, so an overnight
# bus that gets in at 04:30 still counts as "morning".
PREFERENCE_WINDOWS = {
    "morning": (4 * 60, 11 * 60 + 59),
    "afternoon": (12 * 60, 16 * 60 + 59),
    "evening": (17 * 60, 23 * 60 + 59),
}

TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


def window_text(preference):
    """'evening (17:00 to 23:59)', or None when there's no preference."""
    window = PREFERENCE_WINDOWS.get(preference)
    if not window:
        return None
    start, end = window
    return f"{preference} ({fmt(start)} to {fmt(end)})"


def fmt(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_minutes(value):
    """'18:30' -> 1110. None for anything that isn't a valid HH:MM time."""
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    hours, mins = value[:2], value[3:]
    if not (hours.isdigit() and mins.isdigit()):
        return None
    h, m = int(hours), int(mins)
    if h > 23 or m > 59:
        return None
    return h * 60 + m


def _in_window(minutes, preference):
    window = PREFERENCE_WINDOWS.get(preference)
    if not window:
        return True
    return window[0] <= minutes <= window[1]


def move_entries_after_overnight(days):
    """Moves entries that follow an overnight journey to the start of the next day.

    The planner keeps writing Day 1 as "the day we get there": the 18:00-06:00
    overnight bus, then "06:00 check in" on the same day. A time after the bus
    arrives can only mean the next morning, so moving those entries is not a
    guess. They move only when they fit: starting at or after the arrival and
    finishing before the next day's first entry. Otherwise the plan is left as
    it is and the checks send it back to the planner.

    Mutates `days` and returns how many entries moved.
    """
    moved = 0
    for today, tomorrow in zip(days, days[1:]):
        entries = today.get("schedule")
        if not isinstance(entries, list):
            continue
        for position, entry in enumerate(entries[:-1]):
            start, end = to_minutes(entry.get("start")), to_minutes(entry.get("end"))
            if start is None or end is None or end >= start:
                continue
            trailing = entries[position + 1:]
            if not _fits_before_next_day(trailing, end, tomorrow.get("schedule")):
                break
            today["schedule"] = entries[: position + 1]
            tomorrow["schedule"] = trailing + list(tomorrow.get("schedule") or [])
            moved += len(trailing)
            break
    return moved


def _fits_before_next_day(entries, arrival, next_day_entries):
    cursor = arrival
    for entry in entries:
        start, end = to_minutes(entry.get("start")), to_minutes(entry.get("end"))
        if start is None or end is None or start < cursor or end < start:
            return False
        cursor = end
    next_first = to_minutes((next_day_entries or [{}])[0].get("start")) if next_day_entries else None
    return next_first is None or cursor <= next_first


def check_schedules(days, trip):
    """Returns a list of human-readable problems with the days' timings."""
    issues = []
    # Minute of the day the previous day's overnight entry arrives, if any.
    carried_until = None

    for index, day in enumerate(days):
        label = f"Day {day.get('day', index + 1)}"
        entries = day.get("schedule")
        if not isinstance(entries, list) or not entries:
            issues.append(f"{label}: schedule is empty")
            carried_until = None
            continue

        prev_end = carried_until
        prev_text = "the overnight journey from the day before arrives"
        for position, entry in enumerate(entries):
            start = to_minutes(entry.get("start"))
            end = to_minutes(entry.get("end"))
            name = f"{label} {entry.get('start')}-{entry.get('end')}"
            if start is None or end is None:
                issues.append(f"{name}: times must be 24-hour HH:MM")
                prev_end = None
                continue
            if start == end:
                issues.append(f"{name}: start and end time are the same")

            if prev_end is not None and start < prev_end:
                issues.append(
                    f"{name} starts before {prev_text} ({fmt(prev_end)}). "
                    "Entries must not overlap and must be in time order. A journey's arrival "
                    "is its own \"end\" time, not a separate entry."
                )

            crosses_midnight = end < start
            if crosses_midnight and position != len(entries) - 1:
                issues.append(
                    f"{name} is overnight and arrives at {entry.get('end')} the next day, so it "
                    f"must be the last entry of {label}. Everything after it on {label} actually "
                    f"happens the day after; {label} should end with this journey."
                )

            prev_end = None if crosses_midnight else end
            prev_text = "the previous entry ends"

        last_start = to_minutes(entries[-1].get("start"))
        last_end = to_minutes(entries[-1].get("end"))
        if last_start is not None and last_end is not None and last_end < last_start:
            carried_until = last_end
        else:
            carried_until = None

    issues.extend(_check_empty_mornings(days, trip))
    issues.extend(_check_preferences(days, trip))
    return issues


LATEST_FIRST_ENTRY = 12 * 60


def _check_empty_mornings(days, trip):
    """Flags a day after Day 1 with nothing planned before midday.

    The usual case is the last day: an overnight bus home at 16:00 and nothing
    before it, so a morning at the destination is wasted. Day 1 is exempt,
    since the group is at home until it leaves.
    """
    issues = []
    destination = trip.get("destination", "the destination")
    for index, day in enumerate(days[1:], start=2):
        entries = day.get("schedule") or []
        first = to_minutes(entries[0].get("start")) if entries else None
        if first is not None and first > LATEST_FIRST_ENTRY:
            issues.append(
                f"Day {day.get('day', index)} has nothing planned before {entries[0]['start']}. "
                f"Plan the morning in {destination} (sights, breakfast, lunch) before it."
            )
    return issues


def _travel_entries(day):
    return [
        e for e in (day.get("schedule") or [])
        if e.get("kind") == "travel" and to_minutes(e.get("start")) is not None
        and to_minutes(e.get("end")) is not None
    ]


def _length(entry):
    return (to_minutes(entry["end"]) - to_minutes(entry["start"])) % (24 * 60)


def _hours(minutes):
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m"


def _main_leg(day):
    """The longest travel entry of a day: the bus or train, not the cab to the station."""
    travel = _travel_entries(day)
    return max(travel, key=_length) if travel else None


def _check_return_length(days):
    """The way back is the same route, so it can't take a fraction of the time.

    The planner wrote a 4-hour "12:00-16:00" Manali to Delhi bus after a
    12-hour overnight one out.
    """
    if len(days) < 2:
        return []
    out, back = _main_leg(days[0]), _main_leg(days[-1])
    if not out or not back:
        return []
    longer, shorter = max(_length(out), _length(back)), min(_length(out), _length(back))
    if longer - shorter >= 3 * 60 and shorter < 0.6 * longer:
        return [
            f"The journey out ({out['start']} to {out['end']}) takes {_hours(_length(out))} but the "
            f"journey back ({back['start']} to {back['end']}) takes {_hours(_length(back))}. It's the "
            "same route, so both should take about the same time; \"start\" is departure and "
            "\"end\" is arrival."
        ]
    return []


def _check_preferences(days, trip):
    issues = []
    if not days:
        return issues
    issues.extend(_check_return_length(days))
    source = trip.get("source", "the starting city")

    departure = trip.get("departurePreference", "any")
    if departure in PREFERENCE_WINDOWS:
        travel = _travel_entries(days[0])
        if not travel:
            issues.append(f"Day 1 has no travel entry for leaving {source}")
        elif not _in_window(to_minutes(travel[0]["start"]), departure):
            issues.append(
                f"The group wants to leave {source} in the {window_text(departure)}, "
                f"but Day 1's first travel starts at {travel[0]['start']}"
            )

    back = trip.get("returnPreference", "any")
    if back in PREFERENCE_WINDOWS:
        travel = _travel_entries(days[-1])
        if not travel:
            issues.append(f"The last day has no travel entry for getting back to {source}")
        elif not _in_window(to_minutes(travel[-1]["end"]), back):
            outbound = _main_leg(days[0]) if len(days) > 1 else None
            journey = _length(outbound) if outbound else _length(travel[-1])
            issues.append(_late_or_early_return(travel[-1], journey, back, source, trip.get("destination")))

    return issues


def _late_or_early_return(entry, journey, preference, source, destination):
    """The rejection for a return at the wrong time, with the maths done.

    "Arrive in the evening" on a 13-hour route means leaving before 11:00, and
    gpt-4o-mini doesn't work that out reliably on its own; told only that the
    arrival was wrong, it kept picking another overnight bus. `journey` comes
    from the outbound leg when there is one: the draft's own return time can
    be the thing that's wrong.
    """
    window_start, window_end = PREFERENCE_WINDOWS[preference]
    leave_from = fmt((window_start - journey) % (24 * 60))
    leave_by = fmt((window_end - journey) % (24 * 60))
    return (
        f"The group wants to be back in {source} in the {window_text(preference)}, but the "
        f"return ({entry['start']} to {entry['end']}) arrives at {entry['end']}. The journey "
        f"takes about {_hours(journey)}, so leave {destination or 'the destination'} between "
        f"{leave_from} and {leave_by} on the last day. The return is one travel entry whose "
        f"\"end\" is the arrival time; plan the rest of the last day around it."
    )
