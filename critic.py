import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

REQUIRED_DAY_FIELDS = {"day", "morning", "afternoon", "evening", "stay", "estimatedCostPerPerson"}
REQUIRED_TOP_FIELDS = {"summary", "days", "totalEstimatedCostPerPerson", "tradeOffExplanation"}

CRITIC_SYSTEM_PROMPT = """You are a strict travel itinerary evaluator.

Validate:
1. Budget alignment — the recommended budget is a TARGET, not an exact cap.
   The acceptable range is from the minimum budget to the maximum budget provided in the constraints.
   Any totalEstimatedCostPerPerson within this min–max range is ACCEPTABLE. Do NOT reject it.
   Only flag budget as a violation if the cost falls OUTSIDE the min–max range.
2. Duration correctness (days array length must match durationDays)
3. Respect for non-negotiables (these are hard constraints the group WANTS, e.g. "no-flights" = never include flights, "smoking-allowed" = smoking IS permitted — do NOT penalize for it)
4. Realistic activity pacing (only flag if a day is clearly impossible)
5. Fair handling of preference conflicts (tradeOffExplanation must address them)

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
- Budget within the min–max range is NEVER a violation, even if it differs from the recommended amount.
- Vague concerns ("may be high", "might feel rushed", "does not explicitly state") are NOT violations.
- Food preference (e.g. "non-veg") has nothing to do with alcohol. Do NOT conflate them.
- When in doubt, mark as valid.
"""


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

    if not isinstance(itinerary.get("totalEstimatedCostPerPerson"), (int, float)):
        issues.append("totalEstimatedCostPerPerson must be a number")

    return issues


def _run_llm_review(itinerary, aggregated_data, duration_days):
    """Subjective quality checks using an LLM."""

    budget = aggregated_data.get("budget", {})

    user_prompt = f"""Recommended Budget: ₹{budget.get("recommended")}/person
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
        state["repair_instructions"] = {
            "violations": structural_issues,
            "repairInstructions": {"budgetAdjustment": "ok", "activityDensity": "ok", "conflictHandling": "ok"},
            "feedback": "Fix structural issues before quality review"
        }
        state["itinerary"] = None
        state["attempt_count"] = state.get("attempt_count", 0) + 1
        return state

    print("     ✅ Structure OK")

    print("  🤖 Running LLM quality review...")
    review = _run_llm_review(itinerary, state["aggregated_data"], duration_days)

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
        state["itinerary"] = None
        state["attempt_count"] = state.get("attempt_count", 0) + 1
    else:
        print("\n  ✅ Verdict: APPROVED")
        state["repair_instructions"] = None

    return state