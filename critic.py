import json
from openai import OpenAI
from dotenv import load_dotenv
from schedule import check_schedules

load_dotenv()

client = OpenAI()

REQUIRED_DAY_FIELDS = {"day", "schedule", "stay", "estimatedCostPerPerson"}
REQUIRED_TOP_FIELDS = {"summary", "days", "totalEstimatedCostPerPerson", "tradeOffExplanation"}

CRITIC_SYSTEM_PROMPT = """You are a strict travel itinerary evaluator.

Validate:
1. Respect for non-negotiables (these are hard constraints the group WANTS, e.g. "no-flights" = never include flights, "smoking-allowed" = smoking IS permitted — do NOT penalize for it)
2. Realistic activity pacing (only flag if a day is clearly impossible)
3. Fair handling of preference conflicts (tradeOffExplanation must address them)
4. Route logistics — the itinerary must include realistic travel from source to destination on Day 1 and the return journey on the last day, with appropriate transport options.

Already checked in code, so do NOT flag: budget, number of days, cost arithmetic, anything about times: entry order, overlaps, overnight journeys, empty mornings, preferred departure and return times, journey durations.
Overnight travel (e.g. leaving at 2 PM and arriving at 2 AM) is normal and is NOT a violation.
A day that is mostly travel, with few or no activities, is normal and is NOT a violation.

Return STRICT JSON:

{
    "isValid": boolean,
    "violations": ["only concrete violations, empty array if none"],
    "repairInstructions": {
        "budgetAdjustment": "increase" | "decrease" | "ok",
        "activityDensity": "increase" | "decrease" | "ok",
        "conflictHandling": "improve" | "ok"
    },
    "feedback": "one-line summary of your evaluation"
}

Rules:
- "isValid" should be true if there are no real problems.
- "violations" must ONLY contain concrete, factual problems. Never include passing checks.
- Budget is NEVER a violation here; code already checked it.
- Vague concerns ("may be high", "might feel rushed", "does not explicitly state") are NOT violations.
- Food preference (e.g. "non-veg") has nothing to do with alcohol. Do NOT conflate them.
- When in doubt, mark as valid.
"""


def _log_repair_payload(violations, repair_instructions, feedback):
    payload = {
        "violations": violations,
        "repairInstructions": repair_instructions,
        "feedback": feedback,
    }
    print("  📤 Repair instructions sent to planner:")
    print(json.dumps(payload, indent=2))


def _run_structural_checks(itinerary, trip, aggregated_data):
    """Deterministic checks that don't need an LLM."""

    issues = []

    missing_top = REQUIRED_TOP_FIELDS - set(itinerary.keys())
    if missing_top:
        issues.append(f"Missing top-level fields: {missing_top}")

    expected_days = trip.get("durationDays")
    actual_days = len(itinerary.get("days", []))
    if expected_days and actual_days != expected_days:
        issues.append(f"Duration mismatch: expected {expected_days} days, got {actual_days}")

    for i, day in enumerate(itinerary.get("days", [])):
        missing = REQUIRED_DAY_FIELDS - set(day.keys())
        if missing:
            issues.append(f"Day {i+1} missing fields: {missing}")
        if not isinstance(day.get("estimatedCostPerPerson"), (int, float)):
            issues.append(f"Day {i+1}: estimatedCostPerPerson must be a number")

    if not any("missing fields" in i for i in issues):
        issues.extend(check_schedules(itinerary.get("days", []), trip))

    total = itinerary.get("totalEstimatedCostPerPerson")
    if not isinstance(total, (int, float)):
        issues.append("totalEstimatedCostPerPerson must be a number")
        return issues

    # Budget is a number comparison, so it belongs here rather than with the
    # LLM reviewer (which approved a plan outside the range in production).
    # Only the maximum is enforced: a realistic plan cheaper than the group's
    # minimum is fine, and rejecting it just teaches the planner to pad costs.
    max_budget = (aggregated_data or {}).get("budget", {}).get("max")
    if isinstance(max_budget, (int, float)) and total > max_budget:
        issues.append(
            f"Total cost ₹{total:g}/person is over the group's maximum budget of ₹{max_budget:g}"
        )

    day_costs = [d.get("estimatedCostPerPerson") for d in itinerary.get("days", [])]
    if day_costs and all(isinstance(c, (int, float)) for c in day_costs):
        day_sum = sum(day_costs)
        if abs(day_sum - total) > max(100, 0.1 * total):
            issues.append(
                f"totalEstimatedCostPerPerson (₹{total:g}) doesn't match the sum of the days (₹{day_sum:g})"
            )

    return issues


def _run_llm_review(itinerary, trip, aggregated_data, duration_days):
    """Subjective quality checks using an LLM."""

    budget = aggregated_data.get("budget", {})
    source = trip.get("source", aggregated_data.get("source", "Unknown"))
    destination = trip.get("destination", aggregated_data.get("destination", "Unknown"))

    user_prompt = f"""Route: {source} → {destination}
Recommended Budget: ₹{budget.get("recommended")}/person
Duration: {duration_days} days

Aggregated Constraints:
{json.dumps(aggregated_data, indent=2)}

Generated Itinerary:
{json.dumps(itinerary, indent=2)}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"}
        )

        usage = response.usage
        print(f"  📊 Critic tokens — prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"  ⚠️  LLM review failed ({e}), skipping subjective checks")
        return {"isValid": True, "violations": [], "repairInstructions": None, "feedback": "skipped"}


def critic_node(state):

    print("\n" + "=" * 60)
    print("🔍 CRITIC NODE")
    print("=" * 60)

    if state["itinerary"] is None:
        print("  ⏭️  No itinerary to review, skipping")
        return state

    itinerary = state["itinerary"]
    duration_days = state["trip"].get("durationDays")

    print("  🔧 Running structural checks...")
    structural_issues = _run_structural_checks(itinerary, state["trip"], state["aggregated_data"])
    if structural_issues:
        for issue in structural_issues:
            print(f"     ❌ {issue}")
        print(f"\n  🚫 Verdict: REJECTED (structural — {len(structural_issues)} issue(s))")
        over_budget = any("over the group's maximum budget" in i for i in structural_issues)
        state["repair_instructions"] = {
            "violations": structural_issues,
            "repairInstructions": {
                "budgetAdjustment": "decrease" if over_budget else "ok",
                "activityDensity": "ok",
                "conflictHandling": "ok",
            },
            "feedback": "Fix structural issues before quality review"
        }
        _log_repair_payload(
            state["repair_instructions"]["violations"],
            state["repair_instructions"]["repairInstructions"],
            state["repair_instructions"]["feedback"],
        )
        state["rejected_itinerary"] = itinerary
        state["itinerary"] = None
        state["attempt_count"] = state.get("attempt_count", 0) + 1
        return state

    print("     ✅ Structure OK")

    print("  🤖 Running LLM quality review...")
    review = _run_llm_review(itinerary, state["trip"], state["aggregated_data"], duration_days)

    is_valid = review.get("isValid", True)
    violations = review.get("violations", [])
    repair = review.get("repairInstructions", {})
    feedback = review.get("feedback", "")

    print(f"  📝 Feedback: {feedback}")

    if not is_valid and violations:
        for v in violations:
            print(f"     ❌ {v}")
        print(f"\n  🚫 Verdict: REJECTED ({len(violations)} violation(s))")
        print(f"  🔧 Repair: budget={repair.get('budgetAdjustment', 'ok')}, "
              f"density={repair.get('activityDensity', 'ok')}, "
              f"conflicts={repair.get('conflictHandling', 'ok')}")
        state["repair_instructions"] = {
            "violations": violations,
            "repairInstructions": repair,
            "feedback": feedback
        }
        _log_repair_payload(
            state["repair_instructions"]["violations"],
            state["repair_instructions"]["repairInstructions"],
            state["repair_instructions"]["feedback"],
        )
        state["rejected_itinerary"] = itinerary
        state["itinerary"] = None
        state["attempt_count"] = state.get("attempt_count", 0) + 1
    else:
        print("\n  ✅ Verdict: APPROVED")
        state["repair_instructions"] = None
        state["rejected_itinerary"] = None

    return state