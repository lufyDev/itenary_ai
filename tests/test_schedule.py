"""Offline tests for timed schedules, travel days and travel-time preferences.

Run: venv/bin/python -m unittest discover tests
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

import planner  # noqa: E402
from schedule import (  # noqa: E402
    check_day_numbers,
    check_schedules,
    drop_zero_length_entries,
    move_entries_after_overnight,
    to_minutes,
)

# "3 days in Manali" = Sat, Sun, Mon there.
TRIP = {"source": "Delhi", "destination": "Manali", "durationDays": 3}


def e(start, end, kind="activity", activity="x"):
    return {"start": start, "end": end, "kind": kind, "activity": activity}


def days(*schedules, first=1):
    return [{"day": first + i, "schedule": s} for i, s in enumerate(schedules)]


FULL_DAY = [e("08:00", "09:00", "meal"), e("09:30", "13:00"), e("13:00", "14:00", "meal")]

# Leave Friday evening (Day 0), three days there, overnight home from Day 3
# arriving Tuesday morning.
GOOD = days(
    [e("17:00", "17:45", "travel"), e("18:00", "05:30", "travel")],
    [e("06:00", "07:00", "rest")] + FULL_DAY,
    FULL_DAY,
    FULL_DAY + [e("17:00", "06:00", "travel")],
    first=0,
)


class DayNumbers(unittest.TestCase):
    def test_travel_days_are_optional_around_the_holiday_days(self):
        for numbers in ([1, 2, 3], [0, 1, 2, 3], [1, 2, 3, 4], [0, 1, 2, 3, 4]):
            plan = [{"day": n} for n in numbers]
            self.assertEqual(check_day_numbers(plan, 3), [], numbers)

    def test_missing_or_extra_days_are_rejected(self):
        for numbers in ([1, 2], [0, 1, 2], [1, 2, 3, 4, 5], [1, 3, 4], [2, 3, 4]):
            plan = [{"day": n} for n in numbers]
            issues = check_day_numbers(plan, 3)
            self.assertTrue(issues and "Duration mismatch" in issues[0], numbers)


class Timings(unittest.TestCase):
    def test_to_minutes(self):
        self.assertEqual(to_minutes("18:30"), 1110)
        for bad in ["6:30", "24:00", "12:60", "noon", None, "12-30"]:
            self.assertIsNone(to_minutes(bad), bad)

    def test_overnight_both_ways_passes(self):
        self.assertEqual(check_schedules(GOOD, TRIP), [])

    def test_arrival_on_the_same_day_as_an_overnight_departure(self):
        # The production bug: bus leaves 18:00, then "arrive 05:30, check in"
        # and an evening on Mall Road, all on the same day.
        bad = days(
            [e("18:00", "05:30", "travel"), e("05:30", "07:00", "rest"), e("18:00", "21:00")],
            FULL_DAY, FULL_DAY, FULL_DAY, first=0,
        )
        issues = check_schedules(bad, TRIP)
        self.assertTrue(any("must be the last entry of Day 0" in i for i in issues), issues)

    def test_next_day_cannot_start_before_the_overnight_arrival(self):
        bad = days([e("18:00", "05:30", "travel")], [e("04:00", "06:00")] + FULL_DAY[1:],
                   FULL_DAY, FULL_DAY, first=0)
        issues = check_schedules(bad, TRIP)
        self.assertTrue(any("overnight journey" in i for i in issues), issues)

    def test_overlap_is_rejected(self):
        bad = days([e("09:00", "12:00"), e("11:00", "13:00")], FULL_DAY, FULL_DAY)
        issues = check_schedules(bad, TRIP)
        self.assertTrue(any("must not overlap" in i for i in issues), issues)

    def test_back_to_back_entries_are_fine(self):
        ok = days([e("09:00", "12:00"), e("12:00", "13:00", "meal")])
        self.assertEqual(check_schedules(ok, {**TRIP, "durationDays": 1}), [])

    def test_zero_length_and_empty_days(self):
        issues = check_schedules(days([e("09:00", "09:00")], []), {**TRIP, "durationDays": 2})
        self.assertTrue(any("same" in i for i in issues), issues)
        self.assertTrue(any("schedule is empty" in i for i in issues), issues)


class TravelDays(unittest.TestCase):
    def test_overnight_bus_on_day_one_eats_a_holiday_day(self):
        # What the live run produced: Day 1 was only the 21:00-09:30 bus.
        plan = days([e("21:00", "09:30", "travel")], FULL_DAY, FULL_DAY)
        issues = check_schedules(plan, TRIP)
        self.assertTrue(any("Put it on Day 0" in i for i in issues), issues)

    def test_short_journey_on_day_one_is_fine(self):
        # Delhi to Agra, 3 hours, no Day 0 needed.
        plan = days([e("06:00", "09:00", "travel")] + FULL_DAY[1:], FULL_DAY, FULL_DAY)
        self.assertEqual(check_schedules(plan, TRIP), [])

    def test_long_daytime_return_on_day_n_is_flagged(self):
        plan = days([e("18:00", "06:00", "travel")], FULL_DAY, FULL_DAY,
                    [e("06:00", "18:00", "travel")], first=0)
        issues = check_schedules(plan, TRIP)
        self.assertTrue(any("put it on Day 4" in i for i in issues), issues)

    def test_long_daytime_return_on_day_n_plus_one_is_fine(self):
        plan = days([e("18:00", "06:00", "travel")], FULL_DAY, FULL_DAY, FULL_DAY,
                    [e("06:00", "18:00", "travel")], first=0)
        self.assertEqual(check_schedules(plan, TRIP), [])


class EmptyMornings(unittest.TestCase):
    def test_last_day_with_only_the_bus_home_is_flagged(self):
        plan = days([e("18:00", "06:00", "travel")], [e("06:00", "12:00")], FULL_DAY,
                    [e("16:00", "06:00", "travel")], first=0)
        issues = check_schedules(plan, TRIP)
        self.assertTrue(any("Day 3 has nothing planned before 16:00" in i for i in issues), issues)

    def test_travel_days_are_exempt(self):
        # Day 0 starts at 18:00 and Day 4 is a travel day; neither is a day there.
        plan = days([e("18:00", "06:00", "travel")], FULL_DAY, FULL_DAY, FULL_DAY,
                    [e("06:00", "18:00", "travel")], first=0)
        self.assertEqual(check_schedules(plan, TRIP), [])


class MoveAfterOvernight(unittest.TestCase):
    def test_check_in_after_overnight_bus_moves_to_next_day(self):
        # What gpt-4o-mini wrote in 3 of 3 first drafts.
        plan = days(
            [e("17:00", "06:00", "travel"), e("06:00", "07:00", "rest", "check in")],
            [e("07:00", "08:00", "meal"), e("08:00", "12:00")],
            first=0,
        )
        self.assertEqual(move_entries_after_overnight(plan), 1)
        self.assertEqual([x["start"] for x in plan[0]["schedule"]], ["17:00"])
        self.assertEqual([x["start"] for x in plan[1]["schedule"]], ["06:00", "07:00", "08:00"])

    def test_a_move_that_would_clash_is_not_made(self):
        # A whole day planned after the bus, and the next day starting again at 07:00.
        plan = days(
            [e("17:00", "06:00", "travel"), e("06:00", "12:00")],
            [e("07:00", "08:00", "meal")],
            first=0,
        )
        self.assertEqual(move_entries_after_overnight(plan), 0)
        issues = check_schedules(plan, {**TRIP, "durationDays": 1})
        self.assertTrue(any("must be the last entry of Day 0" in i for i in issues), issues)

    def test_entries_before_the_next_days_start_are_required(self):
        plan = days([e("17:00", "06:00", "travel"), e("18:00", "21:00")], [e("09:00", "10:00")])
        self.assertEqual(move_entries_after_overnight(plan), 0)

    def test_last_day_is_not_touched(self):
        plan = days([e("09:00", "10:00")], [e("17:00", "06:00", "travel"), e("06:00", "06:30")])
        self.assertEqual(move_entries_after_overnight(plan), 0)


class ZeroLength(unittest.TestCase):
    def test_stray_zero_length_bus_is_dropped(self):
        plan = days(FULL_DAY + [e("16:00", "16:00", "travel")], [e("05:00", "17:00", "travel")])
        self.assertEqual(drop_zero_length_entries(plan), 1)
        self.assertEqual(plan[0]["schedule"], FULL_DAY)

    def test_a_day_is_never_emptied(self):
        plan = days([e("16:00", "16:00", "travel")])
        self.assertEqual(drop_zero_length_entries(plan), 0)


class Preferences(unittest.TestCase):
    def test_evening_departure_and_morning_return_met(self):
        trip = {**TRIP, "departurePreference": "evening", "returnPreference": "morning"}
        self.assertEqual(check_schedules(GOOD, trip), [])

    def test_morning_departure_not_met(self):
        trip = {**TRIP, "departurePreference": "morning"}
        issues = check_schedules(GOOD, trip)
        self.assertTrue(any("leave Delhi" in i and "Day 0's first travel starts at 17:00" in i
                            for i in issues), issues)

    def test_evening_return_points_to_the_day_after(self):
        # Outbound bus 18:00 to 05:30 is 11h 30m, so arriving 17:00-23:59 means leaving
        # 05:30-12:29: a daytime journey, which belongs on Day 4.
        trip = {**TRIP, "returnPreference": "evening"}
        issue = [i for i in check_schedules(GOOD, trip) if "back in Delhi" in i][0]
        self.assertIn("about 11h 30m", issue)
        self.assertIn("between 05:30 and 12:29", issue)
        self.assertIn("on Day 4, the day after Day 3", issue)

    def test_morning_return_points_to_the_evening_of_day_n(self):
        plan = days([e("18:00", "06:00", "travel")], FULL_DAY, FULL_DAY,
                    FULL_DAY + [e("15:00", "21:00", "travel")], first=0)
        trip = {**TRIP, "returnPreference": "morning"}
        issue = [i for i in check_schedules(plan, trip) if "back in Delhi" in i][0]
        self.assertIn("between 16:00 and 23:59 on Day 3", issue)

    def test_return_much_shorter_than_outbound_is_flagged(self):
        plan = days([e("18:00", "06:00", "travel")], FULL_DAY, FULL_DAY,
                    FULL_DAY + [e("16:00", "19:00", "travel")], first=0)
        issues = check_schedules(plan, TRIP)
        self.assertTrue(any("same route" in i for i in issues), issues)

    def test_a_short_cab_leg_does_not_count_as_the_journey(self):
        plan = days([e("17:00", "17:45", "travel"), e("18:00", "06:00", "travel")],
                    FULL_DAY, FULL_DAY,
                    FULL_DAY + [e("16:00", "16:30", "travel"), e("17:00", "05:00", "travel")],
                    first=0)
        self.assertEqual(check_schedules(plan, TRIP), [])

    def test_any_means_no_check(self):
        trip = {**TRIP, "departurePreference": "any", "returnPreference": "any"}
        self.assertEqual(check_schedules(GOOD, trip), [])

    def test_missing_travel_entry_is_flagged(self):
        no_travel = days(FULL_DAY, FULL_DAY, FULL_DAY)
        trip = {**TRIP, "departurePreference": "evening", "returnPreference": "morning"}
        issues = check_schedules(no_travel, trip)
        self.assertEqual(len(issues), 2, issues)


class PlannerPrompt(unittest.TestCase):
    def test_preferences_reach_the_prompt(self):
        rules = planner._timing_preference_rules(
            {**TRIP, "departurePreference": "evening", "returnPreference": "morning"})
        self.assertIn("LEAVE Delhi in the evening (17:00 to 23:59)", rules)
        self.assertIn("ARRIVE BACK in Delhi in the morning (04:00 to 11:59)", rules)

    def test_no_preferences_adds_nothing(self):
        self.assertEqual(planner._timing_preference_rules(TRIP), "")

    def test_total_is_recomputed_from_days(self):
        it = {"days": [{"estimatedCostPerPerson": 1500}, {"estimatedCostPerPerson": 2000}],
              "totalEstimatedCostPerPerson": 7600}
        with redirect_stdout(io.StringIO()):
            planner._total_from_days(it)
        self.assertEqual(it["totalEstimatedCostPerPerson"], 3500)

    def test_schema_allows_two_travel_days(self):
        fmt = planner.build_response_format(3)
        itin = fmt["json_schema"]["schema"]["properties"]["itinerary"]["anyOf"][0]
        self.assertEqual((itin["properties"]["days"]["minItems"],
                          itin["properties"]["days"]["maxItems"]), (3, 5))

    def test_entry_schema_pins_time_format_and_kinds(self):
        fmt = planner.build_response_format(3)
        itin = fmt["json_schema"]["schema"]["properties"]["itinerary"]["anyOf"][0]
        entry = itin["properties"]["days"]["items"]["properties"]["schedule"]["items"]
        self.assertIn("pattern", entry["properties"]["start"])
        self.assertEqual(entry["properties"]["kind"]["enum"], ["travel", "activity", "meal", "rest"])


if __name__ == "__main__":
    unittest.main()
