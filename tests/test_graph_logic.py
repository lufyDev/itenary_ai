"""Offline tests for the deterministic parts of the agent. No API calls.

Run: venv/bin/python -m unittest discover tests
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

from langgraph.graph import END  # noqa: E402

import critic  # noqa: E402
import graph  # noqa: E402
import planner  # noqa: E402

AGG = {"budget": {"min": 5000, "max": 8000, "recommended": 6500}}
TRIP = {"title": "Delhi to Bir", "source": "Delhi", "destination": "Bir", "durationDays": 3}


def day(n, cost):
    return {"day": n, "schedule": [{"start": "09:00", "end": "11:00", "kind": "activity",
                                    "activity": "a"}],
            "stay": "s", "estimatedCostPerPerson": cost}


def itinerary(costs, total=None):
    return {"summary": "x", "days": [day(i + 1, c) for i, c in enumerate(costs)],
            "totalEstimatedCostPerPerson": sum(costs) if total is None else total,
            "tradeOffExplanation": "none"}


def quiet(fn, *args):
    with redirect_stdout(io.StringIO()):
        return fn(*args)


class StructuralChecks(unittest.TestCase):
    def check(self, it):
        return critic._run_structural_checks(it, TRIP, AGG)

    def test_valid_plan_passes(self):
        self.assertEqual(self.check(itinerary([2000, 2000, 2500])), [])

    def test_cheaper_than_minimum_is_allowed(self):
        self.assertEqual(self.check(itinerary([1000, 1000, 1000])), [])

    def test_over_maximum_is_rejected(self):
        issues = self.check(itinerary([3000, 3000, 3000]))
        self.assertTrue(any("over the group's maximum budget" in i for i in issues), issues)

    def test_total_must_match_day_sum(self):
        # The production failure: total copied from the target, days summed to 3100.
        issues = self.check(itinerary([800, 1500, 800], total=6500))
        self.assertTrue(any("doesn't match the sum" in i for i in issues), issues)

    def test_small_rounding_difference_is_fine(self):
        self.assertEqual(self.check(itinerary([1000, 1000, 1000], total=3050)), [])

    def test_wrong_day_count_is_rejected(self):
        issues = self.check(itinerary([2000]))
        self.assertTrue(any("Duration mismatch" in i for i in issues), issues)


class CriticNode(unittest.TestCase):
    def test_rejection_keeps_the_draft_for_the_planner(self):
        draft = itinerary([2000])
        state = {"trip": TRIP, "aggregated_data": AGG, "itinerary": draft,
                 "repair_instructions": None, "rejected_itinerary": None, "attempt_count": 0}
        out = quiet(critic.critic_node, state)
        self.assertIsNone(out["itinerary"])
        self.assertEqual(out["rejected_itinerary"], draft)
        self.assertEqual(out["attempt_count"], 1)

    def test_over_budget_asks_planner_to_decrease(self):
        state = {"trip": TRIP, "aggregated_data": AGG, "itinerary": itinerary([4000, 4000, 4000]),
                 "repair_instructions": None, "rejected_itinerary": None, "attempt_count": 0}
        out = quiet(critic.critic_node, state)
        self.assertEqual(out["repair_instructions"]["repairInstructions"]["budgetAdjustment"], "decrease")


class PlannerSchema(unittest.TestCase):
    def days_schema(self, duration):
        fmt = planner.build_response_format(duration)
        itin = fmt["json_schema"]["schema"]["properties"]["itinerary"]["anyOf"][0]
        return itin["properties"]["days"]

    def test_pins_day_count(self):
        days = self.days_schema(3)
        self.assertEqual((days["minItems"], days["maxItems"]), (3, 3))

    def test_unknown_duration_leaves_count_open(self):
        self.assertNotIn("minItems", self.days_schema("?"))

    def test_schema_is_strict(self):
        fmt = planner.build_response_format(3)
        self.assertTrue(fmt["json_schema"]["strict"])


class PlannerRouter(unittest.TestCase):
    def test_first_call_goes_to_tools(self):
        state = {"itinerary": None, "tool_results": {}, "attempt_count": 0}
        self.assertEqual(quiet(graph.planner_router, state), "tool")

    def test_empty_planner_after_tools_retries_planner_not_tools(self):
        state = {"itinerary": None, "tool_results": {"research": []}, "attempt_count": 1}
        self.assertEqual(quiet(graph.planner_router, state), "planner")

    def test_gives_up_after_max_attempts(self):
        state = {"itinerary": None, "tool_results": {"research": []},
                 "attempt_count": graph.MAX_ATTEMPTS}
        self.assertEqual(quiet(graph.planner_router, state), END)

    def test_itinerary_goes_to_critic(self):
        state = {"itinerary": itinerary([1000]), "tool_results": {"research": []}, "attempt_count": 0}
        self.assertEqual(quiet(graph.planner_router, state), "critic")


if __name__ == "__main__":
    unittest.main()
