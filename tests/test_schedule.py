"""Offline tests for timed schedules and travel-time preferences.

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
from schedule import check_schedules, move_entries_after_overnight, to_minutes  # noqa: E402

TRIP = {"source": "Delhi", "destination": "Manali", "durationDays": 3}


def e(start, end, kind="activity", activity="x"):
    return {"start": start, "end": end, "kind": kind, "activity": activity}


def days(*schedules):
    return [{"day": i + 1, "schedule": s} for i, s in enumerate(schedules)]


# Overnight bus out on day 1, overnight bus back on day 3.
GOOD = days(
    [e("17:00", "17:45", "travel"), e("18:00", "05:30", "travel")],
    [e("06:00", "07:00", "rest"), e("08:00", "09:00", "meal"), e("09:30", "13:00")],
    [e("09:00", "12:00"), e("13:00", "14:00", "meal"), e("17:00", "06:00", "travel")],
)


class Timings(unittest.TestCase):
    def test_to_minutes(self):
        self.assertEqual(to_minutes("18:30"), 1110)
        for bad in ["6:30", "24:00", "12:60", "noon", None, "12-30"]:
            self.assertIsNone(to_minutes(bad), bad)

    def test_overnight_trip_passes(self):
        self.assertEqual(check_schedules(GOOD, TRIP), [])

    def test_arrival_on_the_same_day_as_an_overnight_departure(self):
        # The production bug: bus leaves 18:00, then "arrive 05:30, check in"
        # and an evening on Mall Road, all on Day 1.
        bad = days(
            [e("18:00", "05:30", "travel"), e("05:30", "07:00", "rest"), e("18:00", "21:00")],
            [e("09:00", "12:00")],
            [e("09:00", "12:00")],
        )
        issues = check_schedules(bad, TRIP)
        self.assertTrue(any("must be the last entry of Day 1" in i for i in issues), issues)

    def test_next_day_cannot_start_before_the_overnight_arrival(self):
        bad = days([e("18:00", "05:30", "travel")], [e("04:00", "06:00")], [e("09:00", "10:00")])
        issues = check_schedules(bad, TRIP)
        self.assertTrue(any("overnight journey" in i for i in issues), issues)

    def test_overlap_is_rejected(self):
        bad = days([e("09:00", "12:00"), e("11:00", "13:00")], [e("09:00", "10:00")],
                   [e("09:00", "10:00")])
        issues = check_schedules(bad, TRIP)
        self.assertTrue(any("must not overlap" in i for i in issues), issues)

    def test_back_to_back_entries_are_fine(self):
        ok = days([e("09:00", "12:00"), e("12:00", "13:00", "meal")])
        self.assertEqual(check_schedules(ok, TRIP), [])

    def test_zero_length_and_empty_days(self):
        issues = check_schedules(days([e("09:00", "09:00")], []), TRIP)
        self.assertTrue(any("same" in i for i in issues), issues)
        self.assertTrue(any("schedule is empty" in i for i in issues), issues)


class MoveAfterOvernight(unittest.TestCase):
    def test_check_in_after_overnight_bus_moves_to_next_day(self):
        # What gpt-4o-mini wrote in 3 of 3 first drafts.
        plan = days(
            [e("17:00", "06:00", "travel"), e("06:00", "07:00", "rest", "check in")],
            [e("07:00", "08:00", "meal"), e("08:00", "12:00")],
        )
        self.assertEqual(move_entries_after_overnight(plan), 1)
        self.assertEqual([x["start"] for x in plan[0]["schedule"]], ["17:00"])
        self.assertEqual([x["start"] for x in plan[1]["schedule"]], ["06:00", "07:00", "08:00"])
        self.assertEqual(check_schedules(plan, TRIP), [])

    def test_a_move_that_would_clash_is_not_made(self):
        # A whole day planned on Day 1 after the bus, and Day 2 starting again at 07:00.
        plan = days(
            [e("17:00", "06:00", "travel"), e("06:00", "12:00")],
            [e("07:00", "08:00", "meal")],
        )
        self.assertEqual(move_entries_after_overnight(plan), 0)
        issues = check_schedules(plan, TRIP)
        self.assertTrue(any("must be the last entry of Day 1" in i for i in issues), issues)

    def test_entries_before_the_arrival_time_are_left_alone(self):
        # Moving 18:00-21:00 to Day 2 would clash with Day 2's 09:00, so it stays and the
        # check sends it back to the planner.
        plan = days([e("17:00", "06:00", "travel"), e("18:00", "21:00")], [e("09:00", "10:00")])
        self.assertEqual(move_entries_after_overnight(plan), 0)
        self.assertTrue(check_schedules(plan, TRIP))

    def test_last_day_is_not_touched(self):
        plan = days([e("09:00", "10:00")], [e("17:00", "06:00", "travel"), e("06:00", "06:30")])
        self.assertEqual(move_entries_after_overnight(plan), 0)


class EmptyMornings(unittest.TestCase):
    def test_last_day_with_only_the_bus_home_is_flagged(self):
        # An approved plan from a live run: Day 3 was just "16:00-06:00 Volvo to Delhi".
        plan = days([e("18:00", "06:00", "travel")], [e("06:00", "12:00")],
                    [e("16:00", "06:00", "travel")])
        issues = check_schedules(plan, TRIP)
        self.assertTrue(any("Day 3 has nothing planned before 16:00" in i for i in issues), issues)

    def test_day_one_evening_departure_is_fine(self):
        plan = days([e("18:00", "06:00", "travel")], [e("06:00", "12:00")])
        self.assertEqual(check_schedules(plan, TRIP), [])


class Preferences(unittest.TestCase):
    def test_evening_departure_and_morning_return_met(self):
        trip = {**TRIP, "departurePreference": "evening", "returnPreference": "morning"}
        self.assertEqual(check_schedules(GOOD, trip), [])

    def test_morning_departure_not_met(self):
        trip = {**TRIP, "departurePreference": "morning"}
        issues = check_schedules(GOOD, trip)
        self.assertTrue(any("leave Delhi" in i and "17:00" in i for i in issues), issues)

    def test_return_is_judged_on_arrival_time(self):
        # Leaves at 17:00 but arrives 06:00, so "evening" is not met.
        trip = {**TRIP, "returnPreference": "evening"}
        issues = check_schedules(GOOD, trip)
        self.assertTrue(any("back in Delhi" in i and "06:00" in i for i in issues), issues)

    def test_return_rejection_says_when_to_leave(self):
        # 17:00 to 06:00 is 13h, so an evening arrival (17:00-23:59) means leaving 04:00-10:59.
        trip = {**TRIP, "returnPreference": "evening"}
        issue = [i for i in check_schedules(GOOD, trip) if "back in Delhi" in i][0]
        # The outbound bus (18:00 to 05:30) is 11h 30m, so that's the journey time used.
        self.assertIn("about 11h 30m", issue)
        self.assertIn("leave Manali between 05:30 and 12:29", issue)

    def test_return_much_shorter_than_outbound_is_flagged(self):
        plan = days([e("18:00", "06:00", "travel")], [e("09:00", "10:00")],
                    [e("12:00", "16:00", "travel")])
        issues = check_schedules(plan, TRIP)
        self.assertTrue(any("same route" in i for i in issues), issues)

    def test_a_short_cab_leg_does_not_count_as_the_journey(self):
        plan = days([e("17:00", "17:45", "travel"), e("18:00", "06:00", "travel")],
                    [e("09:00", "10:00")],
                    [e("09:00", "13:00"), e("16:00", "16:30", "travel"),
                     e("17:00", "05:00", "travel")])
        self.assertEqual(check_schedules(plan, TRIP), [])

    def test_any_means_no_check(self):
        trip = {**TRIP, "departurePreference": "any", "returnPreference": "any"}
        self.assertEqual(check_schedules(GOOD, trip), [])

    def test_missing_travel_entry_is_flagged(self):
        no_travel = days([e("09:00", "10:00")], [e("09:00", "10:00")], [e("09:00", "10:00")])
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

    def test_entry_schema_pins_time_format_and_kinds(self):
        fmt = planner.build_response_format(3)
        itin = fmt["json_schema"]["schema"]["properties"]["itinerary"]["anyOf"][0]
        entry = itin["properties"]["days"]["items"]["properties"]["schedule"]["items"]
        self.assertIn("pattern", entry["properties"]["start"])
        self.assertEqual(entry["properties"]["kind"]["enum"], ["travel", "activity", "meal", "rest"])


if __name__ == "__main__":
    unittest.main()
