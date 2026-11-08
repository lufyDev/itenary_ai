import json
from openai import OpenAI
from dotenv import load_dotenv
from schedule import ENTRY_KINDS, TIME_PATTERN, move_entries_after_overnight, window_text

load_dotenv()

client = OpenAI()

ITINERARY_SCHEMA = """{
  "summary": "string — brief overview of the trip plan",
  "days": [
    {
      "day": 1,
      "schedule": [
        {
          "start": "HH:MM — 24-hour start time",
          "end": "HH:MM — 24-hour end time (earlier than start if it runs past midnight)",
          "kind": "travel | activity | meal | rest",
          "activity": "string — what happens, with specific places, transport and costs"
        }
      ],
      "stay": "string — accommodation name and type, or the overnight bus/train",
      "estimatedCostPerPerson": 0
    }
  ],
  "totalEstimatedCostPerPerson": 0,
  "tradeOffExplanation": "string — explain how group conflicts were resolved"
}"""


_ENTRY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "start": {"type": "string", "pattern": TIME_PATTERN},
        "end": {"type": "string", "pattern": TIME_PATTERN},
        "kind": {"type": "string", "enum": ENTRY_KINDS},
        "activity": {"type": "string"},
    },
    "required": ["start", "end", "kind", "activity"],
    "additionalProperties": False,
}

_DAY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "day": {"type": "integer"},
        "schedule": {"type": "array", "items": _ENTRY_JSON_SCHEMA, "minItems": 1},
        "stay": {"type": "string"},
        "estimatedCostPerPerson": {"type": "number"},
    },
    "required": ["day", "schedule", "stay", "estimatedCostPerPerson"],
    "additionalProperties": False,
}


def build_response_format(duration_days):
    """Strict JSON schema for the planner's reply.

    Plain JSON mode let the model split the days across two "days" keys, e.g.
    {"days": [day 1], "totalEstimatedCostPerPerson": ..., "days": [day 2, day 3]}.
    json.loads keeps only the last key, so day 1 vanished and the critic saw
    a 1- or 2-day plan (6 of 10 runs on a 3-day trip). A strict schema rules
    out duplicate keys, fixes the field order (days before the total), and
    pins the number of days.
    """
    days_schema = {"type": "array", "items": _DAY_JSON_SCHEMA}
    if isinstance(duration_days, int) and duration_days > 0:
        days_schema["minItems"] = duration_days
        days_schema["maxItems"] = duration_days

    itinerary_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "days": days_schema,
            "totalEstimatedCostPerPerson": {"type": "number"},
            "tradeOffExplanation": {"type": "string"},
        },
        "required": ["summary", "days", "totalEstimatedCostPerPerson", "tradeOffExplanation"],
        "additionalProperties": False,
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "planner_decision",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["USE_TOOL", "ITINERARY"]},
                    "itinerary": {"anyOf": [itinerary_schema, {"type": "null"}]},
                },
                "required": ["action", "itinerary"],
                "additionalProperties": False,
            },
        },
    }


SYSTEM_PROMPT = f"""You are an autonomous travel planning agent.

Your goal is to create a realistic, budget-conscious itinerary grounded in verified data.
The trip has an explicit SOURCE (origin city) and DESTINATION. You must plan the full journey
from source to destination, including realistic travel logistics on Day 1 (departure) and
the return journey on the last day.

You have ONE tool action available that triggers THREE parallel research tools:
1. Destination Research — travel guide, places to visit, famous cafes, events, activities.
2. Accommodation Search — hotels, hostels, pricing for the preferred accommodation type.
3. Transport Search — best routes and costs from source to destination.

Tool Rules:
- If Existing Tool Results is empty ({{}}), respond with {{"action": "USE_TOOL"}} to research the destination.
- If Existing Tool Results already contains ANY data (under "research", "stays", or "transport" keys), you MUST NOT call the tool again.
  Use ALL retrieved data combined with your own knowledge to finalize the itinerary.
- The tool can only be called ONCE. After that, finalize with whatever information you have.

Respond with valid JSON ONLY using ONE of these formats:

TO USE A TOOL (only if Tool Results is empty):
{{"action": "USE_TOOL", "itinerary": null}}

TO FINALIZE (required if Tool Results has data):
{{"action": "ITINERARY", "itinerary": <itinerary object>}}

The itinerary object MUST strictly match this schema:
{ITINERARY_SCHEMA}

Rules:
- All costs are in INR (₹) per person.
- Day 1 must include travel from the source city to the destination with specific transport options (bus, train, cab, etc.), estimated travel time, and cost.
- The last day must include the return journey from destination back to source.
- Timings:
  - Days are calendar dates. Day 1 is the date the group leaves the source city, so if they
    leave in the evening, Day 1 holds little more than getting to the bus/train and the
    departure. Arrival and check-in belong to the date they actually happen.
  - Each day is a "schedule": entries in time order, each with a 24-hour start and end time
    ("06:30", "18:00"). Entries must not overlap.
  - Give every entry a realistic duration: real travel times between places, time to see a
    sight, meals. "kind" is "travel" for any journey (bus, train, cab, walk between areas),
    "meal" for breakfast/lunch/dinner, "rest" for check-in, free time or sleep, "activity"
    for everything else.
  - A journey is ONE travel entry: "start" is when it departs, "end" is when it arrives.
    Never add a separate "arrive" entry.
  - An overnight journey is one entry whose end time is earlier than its start, because it
    arrives the next day. It must be the LAST entry of its day, and the next day's first entry
    must start at or after its arrival. Example, overnight bus out on Day 1 and back on Day 3:
      Day 1: {{"start": "18:00", "end": "06:00", "kind": "travel", "activity": "Overnight Volvo Delhi to Manali ..."}}
      Day 2: {{"start": "06:30", "end": "07:30", "kind": "rest", "activity": "Check in at ..."}}, ...
      Day 3: ..., {{"start": "17:00", "end": "07:00", "kind": "travel", "activity": "Overnight Volvo Manali to Delhi ..."}}
    On an overnight day, "stay" is the bus or train, not a hotel.
  - Use every day at the destination: on the last day, plan the morning there before the
    return journey (e.g. a sight and lunch before a 17:00 bus).
  - Travel times must add up. If the outbound journey takes about 12 hours, the return does too.
- The itinerary must cover the FULL trip duration. Never collapse a multi-day trip into a single day, even if some days are light or mostly travel.
- If the trip duration is N days, the "days" array must contain exactly N objects, with day numbers 1 through N and no gaps.
- If retrieved data is limited, still produce a complete N-day itinerary using the available evidence plus reasonable planning assumptions.
- Before finalizing, do a self-check that the number of day entries exactly matches the requested duration. If it does not, revise before responding.
- Include location-specific activities, landmarks, and experiences at the destination.
- "tradeOffExplanation" must specifically address each group conflict.
- Never violate any non-negotiable constraint.
- Always use specific, real accommodation names from the retrieved data (e.g. "Zostel Shoja", "Mudhouse Hostel"). Never use generic placeholders like "Budget Hotel" or "Local Guesthouse".
"""


def _total_from_days(itinerary):
    """Sets the trip total to the sum of the day costs.

    The total is derived data and the model can't add: it wrote a ₹7,600 total
    over days summing to ₹5,600 and repeated it through all three revisions.
    Summing here means the budget check judges the real figure.
    """
    costs = [d.get("estimatedCostPerPerson") for d in itinerary.get("days", [])]
    if costs and all(isinstance(c, (int, float)) for c in costs):
        total = sum(costs)
        if total != itinerary.get("totalEstimatedCostPerPerson"):
            print(f"  🧮 Total set to the day sum: ₹{itinerary.get('totalEstimatedCostPerPerson')} → ₹{total:g}")
        itinerary["totalEstimatedCostPerPerson"] = total


def _timing_preference_rules(trip):
    """Prompt lines for the group's preferred departure and return times."""
    source = trip.get("source", "the starting city")
    lines = []
    leave = window_text(trip.get("departurePreference"))
    if leave:
        lines.append(
            f"- The group wants to LEAVE {source} in the {leave}. Day 1's first travel entry must "
            "start in that window. Pick the transport that fits (e.g. an overnight bus or train "
            "for an evening departure on a long route)."
        )
    back = window_text(trip.get("returnPreference"))
    if back:
        lines.append(
            f"- The group wants to ARRIVE BACK in {source} in the {back}. The last travel entry "
            "on the last day must END in that window. Work backwards from the journey time to "
            "choose when to leave: on a 12-hour route, a morning arrival means an overnight "
            "journey the evening before, and an evening arrival means leaving early that morning."
        )
    return "".join(line + "\n" for line in lines)


def planner_node(state):

    attempt = state.get("attempt_count", 0)

    print("\n" + "=" * 60)
    print(f"🧠 PLANNER NODE (critic rejections so far: {attempt})")
    print("=" * 60)

    source = state["trip"].get("source", "Unknown")
    destination = state["trip"].get("destination", state["trip"].get("title", "Unknown"))
    duration = state["trip"].get("durationDays", "?")
    tool_results = state.get("tool_results", {})
    timing_rules = _timing_preference_rules(state["trip"])
    has_knowledge = any(tool_results.get(k) for k in ("research", "stays", "transport"))
    print(f"  📍 Route: {source} → {destination}")
    print(f"  📅 Duration: {duration} days")
    print(f"  📚 Has retrieved knowledge: {has_knowledge}")

    # The critic clears "itinerary" when it rejects a draft, so the rejected
    # draft travels in its own key. Without it the planner starts from scratch
    # and, given an almost identical prompt, returns an almost identical draft.
    repair_section = ""
    if state.get("repair_instructions"):
        print("  ⚠️  Re-running with repair feedback")
        rejected = state.get("rejected_itinerary")
        draft_part = (
            f"""Your previous draft (REJECTED):
{json.dumps(rejected, indent=2, ensure_ascii=False)}

"""
            if rejected
            else ""
        )
        repair_section = f"""

REVISION REQUIRED
{draft_part}The critic rejected it for these reasons:
{json.dumps(state["repair_instructions"], indent=2)}

Revise the draft to fix every violation above. Keep the parts that were fine.
Return the complete revised itinerary, not just the changed days."""

    user_prompt = f"""CURRENT TASK STATE

Trip:
{json.dumps(state["trip"], indent=2)}

Aggregated Group Data:
{json.dumps(state["aggregated_data"], indent=2)}

Existing Tool Results:
{json.dumps(state.get("tool_results", {}), indent=2)}

Additional Rules:
- The "days" array MUST have exactly {duration} entries, numbered 1 to {duration}.
- Expected day numbers are exactly: {list(range(1, duration + 1)) if isinstance(duration, int) and duration > 0 else f"1 to {duration}"}.
- Never combine multiple trip days into one "day" object.
- If you are missing details for some middle day, make the best realistic plan you can, but still return all {duration} days.
- "totalEstimatedCostPerPerson" must not exceed ₹{state["aggregated_data"].get("budget", {}).get("max")}. Aim near ₹{state["aggregated_data"].get("budget", {}).get("recommended")} when the plan genuinely costs that much; a cheaper realistic plan is fine.
- "totalEstimatedCostPerPerson" is the sum of the days' "estimatedCostPerPerson" (code recomputes it).
{timing_rules}- Final self-check before responding:
  1. Is "action" set correctly?
  2. If action is "ITINERARY", does the itinerary include exactly {duration} day objects?
  3. Do Day 1 and Day {duration} include outbound and return travel respectively?
  4. If any answer is no, revise internally before returning JSON.

Decide the NEXT BEST ACTION.{repair_section}
"""

    print("  🤖 Calling GPT-4o-mini...")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=build_response_format(duration),
        )

        usage = response.usage
        print(f"  📊 Tokens — prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")

        output = response.choices[0].message.content
        parsed = json.loads(output)

        action = parsed.get("action", "UNKNOWN")
        print(f"  📋 LLM decided: {action}")

        if action == "USE_TOOL" or not parsed.get("itinerary"):
            state["itinerary"] = None
            print("  ➡️  Result: Requesting tool lookup")
        else:
            state["itinerary"] = parsed["itinerary"]
            _total_from_days(state["itinerary"])
            moved = move_entries_after_overnight(state["itinerary"].get("days", []))
            if moved:
                print(f"  🌙 Moved {moved} entr{'y' if moved == 1 else 'ies'} that followed an overnight journey to the next day")
            days_count = len(state["itinerary"].get("days", [])) if isinstance(state["itinerary"], dict) else "?"
            total_cost = state["itinerary"].get("totalEstimatedCostPerPerson", "?") if isinstance(state["itinerary"], dict) else "?"
            print(f"  ✅ Itinerary generated — {days_count} days, ₹{total_cost}/person")

    except json.JSONDecodeError as e:
        print(f"  ❌ Failed to parse LLM response: {e}")
        state["itinerary"] = None

    except Exception as e:
        print(f"  ❌ API error: {e}")
        state["itinerary"] = None

    # After the one tool run, no itinerary means this attempt failed. Count it,
    # so the graph retries a bounded number of times instead of looping.
    if state["itinerary"] is None and state.get("tool_results"):
        state["attempt_count"] = state.get("attempt_count", 0) + 1
        state["repair_instructions"] = {
            "violations": ["The planner did not return an itinerary"],
            "repairInstructions": {"budgetAdjustment": "ok", "activityDensity": "ok", "conflictHandling": "ok"},
            "feedback": "Return a complete itinerary with action ITINERARY",
        }

    return state