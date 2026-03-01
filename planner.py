import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

ITINERARY_SCHEMA = """{
  "summary": "string — brief overview of the trip plan",
  "days": [
    {
      "day": 1,
      "morning": "string — morning activity with details",
      "afternoon": "string — afternoon activity with details",
      "evening": "string — evening activity with details",
      "stay": "string — accommodation name and type",
      "estimatedCostPerPerson": 0
    }
  ],
  "totalEstimatedCostPerPerson": 0,
  "tradeOffExplanation": "string — explain how group conflicts were resolved"
}"""


SYSTEM_PROMPT = f"""You are an autonomous travel planning agent.

Your goal is to create a realistic, budget-conscious itinerary grounded in verified data.

You have ONE tool available:
- retrieve_travel_knowledge: Researches the destination via web search and cached knowledge to gather real-world information (places, costs, transport, stays, activities).

Tool Rules:
- If Existing Tool Results is empty ({{}}), respond with {{"action": "USE_TOOL"}} to research the destination.
- If Existing Tool Results already contains ANY data, you MUST NOT call the tool again.
  Use the retrieved data combined with your own knowledge to finalize the itinerary.
- The tool can only be called ONCE. After that, finalize with whatever information you have.

Respond with valid JSON ONLY using ONE of these formats:

TO USE A TOOL (only if Tool Results is empty):
{{"action": "USE_TOOL"}}

TO FINALIZE (required if Tool Results has data):
{{"action": "ITINERARY", "itinerary": <itinerary object>}}

The itinerary object MUST strictly match this schema:
{ITINERARY_SCHEMA}

Rules:
- All costs are in INR (₹) per person.
- "tradeOffExplanation" must specifically address each group conflict.
- Never violate any non-negotiable constraint.
"""


def planner_node(state):

    attempt = state.get("attempt_count", 0)

    print("\n" + "=" * 60)
    print(f"🧠 PLANNER NODE (critic rejections so far: {attempt})")
    print("=" * 60)

    destination = state["trip"].get("title", "Unknown")
    duration = state["trip"].get("durationDays", "?")
    has_knowledge = bool(state.get("tool_results", {}).get("rag"))
    print(f"  📍 Destination: {destination}")
    print(f"  📅 Duration: {duration} days")
    print(f"  📚 Has retrieved knowledge: {has_knowledge}")

    repair_section = "None"
    if state.get("repair_instructions"):
        repair_section = json.dumps(state["repair_instructions"], indent=2)
        print("  ⚠️  Re-running with repair feedback")

    user_prompt = f"""CURRENT TASK STATE

Trip:
{json.dumps(state["trip"], indent=2)}

Aggregated Group Data:
{json.dumps(state["aggregated_data"], indent=2)}

Existing Tool Results:
{json.dumps(state.get("tool_results", {}), indent=2)}

Repair Instructions (from critic):
{repair_section}

Additional Rules:
- The "days" array MUST have exactly {duration} entries, numbered 1 to {duration}.
- "totalEstimatedCostPerPerson" should be close to ₹{state["aggregated_data"].get("budget", {}).get("recommended")}.

Decide the NEXT BEST ACTION.
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
            response_format={"type": "json_object"}
        )

        usage = response.usage
        print(f"  📊 Tokens — prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")

        output = response.choices[0].message.content
        parsed = json.loads(output)

        action = parsed.get("action", "UNKNOWN")
        print(f"  📋 LLM decided: {action}")

        if action == "USE_TOOL":
            state["itinerary"] = None
            print("  ➡️  Result: Requesting tool lookup")
        else:
            state["itinerary"] = parsed.get("itinerary", parsed)
            days_count = len(state["itinerary"].get("days", [])) if isinstance(state["itinerary"], dict) else "?"
            total_cost = state["itinerary"].get("totalEstimatedCostPerPerson", "?") if isinstance(state["itinerary"], dict) else "?"
            print(f"  ✅ Itinerary generated — {days_count} days, ₹{total_cost}/person")

    except json.JSONDecodeError as e:
        print(f"  ❌ Failed to parse LLM response: {e}")
        state["itinerary"] = None

    except Exception as e:
        print(f"  ❌ API error: {e}")
        state["itinerary"] = None

    return state