import json
from graph import graph

print("\n" + "🚀" * 30)
print("  ITINERARY AI — Starting Pipeline")
print("🚀" * 30)

initial_state = {
    "trip": {
        "title": "Jibhi",
        "durationDays": 3,
    },
     "aggregated_data": {
        "groupSize": 3,
        "budget": {
            "min": 5000,
            "max": 15000,
            "recommended": 10000
        },
        "majorityPreferences": {
            "travelStyle": "balanced",
            "foodPreference": "non-veg",
            "accommodationType": "budget-hotel"
        },
        "topActivities": [
            "trekking",
            "waterfalls",
            "local-markets",
            "camping",
            "cafes"
        ],
        "nonNegotiables": [
            "no-flights",
            "no-alcohol",
            "smoking-allowed"
        ],
        "conflicts": []
    },
    "tool_results": {},
    "itinerary": None,
    "repair_instructions": None,
    "attempt_count": 0,
}

print(f"\n📌 Trip: {initial_state['trip']['title']}")
print(f"📅 Duration: {initial_state['trip']['durationDays']} days")
print(f"👥 Group size: {initial_state['aggregated_data']['groupSize']}")
print(f"💰 Budget: ₹{initial_state['aggregated_data']['budget']['min']} – ₹{initial_state['aggregated_data']['budget']['max']} (target ₹{initial_state['aggregated_data']['budget']['recommended']}/person)")

result = graph.invoke(initial_state)

print("\n" + "=" * 60)
print(f"🏁 FINAL RESULT ({result.get('attempt_count', '?')} attempt(s))")
print("=" * 60)

if result["itinerary"]:
    print(json.dumps(result["itinerary"], indent=2))
else:
    print("❌ Failed to generate an itinerary.")