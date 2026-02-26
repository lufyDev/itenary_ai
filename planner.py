import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()


def planner_node(state):

    repair_context = ""
    if state.get("repair_instructions"):
        repair_context = f"""
IMPORTANT — Your previous itinerary was rejected.
Repair Instructions: {json.dumps(state["repair_instructions"])}
Address these issues in your new itinerary.
"""

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

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        output = response.choices[0].message.content
        parsed = json.loads(output)

        if parsed.get("action") == "USE_TOOL":
            state["itinerary"] = None
        else:
            state["itinerary"] = parsed.get("itinerary", parsed)

    except json.JSONDecodeError as e:
        print(f"[Planner] Failed to parse LLM response: {e}")
        state["itinerary"] = None

    except Exception as e:
        print(f"[Planner] API error: {e}")
        state["itinerary"] = None

    return state