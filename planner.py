import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()


def planner_node(state):

    print("\n" + "=" * 60)
    print("🧠 PLANNER NODE")
    print("=" * 60)

    repair_context = ""
    if state.get("repair_instructions"):
        print(f"  ⚠️  Re-running with repair instructions: {state['repair_instructions']}")
        repair_context = f"""
IMPORTANT — Your previous itinerary was rejected.
Repair Instructions: {json.dumps(state["repair_instructions"])}
Address these issues in your new itinerary.
"""
    else:
        has_knowledge = bool(state.get("tool_results", {}).get("rag"))
        print(f"  📍 Destination: {state['trip'].get('title', 'Unknown')}")
        print(f"  📚 Has retrieved knowledge: {has_knowledge}")

    prompt = f"""
You are a travel planner. Generate a detailed travel itinerary based on the given data.

Trip:
{json.dumps(state["trip"])}

Aggregated Data:
{json.dumps(state["aggregated_data"])}

Retrieved Knowledge:
{json.dumps(state["tool_results"])}

{repair_context}

You MUST respond with a JSON object in one of these two formats:

1. If you lack knowledge about the destination and need to look it up:
   {{"action": "USE_TOOL"}}

2. If you have enough information to create the itinerary:
   {{"action": "ITINERARY", "itinerary": {{ "title": "...", "days": [...], "totalEstimatedCost": "...", "tips": [...] }}}}

The itinerary should include day-by-day plans with activities, accommodation, meals,
transport, and estimated costs. Respect the group's budget, preferences, and non-negotiables.
"""

    print("  🤖 Calling GPT-4o-mini...")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        usage = response.usage
        print(f"  📊 Tokens used — prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")

        output = response.choices[0].message.content
        parsed = json.loads(output)

        action = parsed.get("action", "UNKNOWN")
        print(f"  📋 LLM decided: {action}")

        if action == "USE_TOOL":
            state["itinerary"] = None
            print("  ➡️  Result: No itinerary yet, needs tool lookup")
        else:
            state["itinerary"] = parsed.get("itinerary", parsed)
            days = len(state["itinerary"].get("days", [])) if isinstance(state["itinerary"], dict) else "?"
            print(f"  ✅ Result: Itinerary generated ({days} days)")

    except json.JSONDecodeError as e:
        print(f"  ❌ Failed to parse LLM response: {e}")
        state["itinerary"] = None

    except Exception as e:
        print(f"  ❌ API error: {e}")
        state["itinerary"] = None

    return state