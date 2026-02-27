import json
from graph import graph

print("\n" + "🚀" * 30)
print("  ITINERARY AI — Starting Pipeline")
print("🚀" * 30)

initial_state = {
    "trip": {"title": "Jibhi"},
     "aggregated_data": {
        "groupSize": 3,
        "budget": {
            "min": 5000,
            "max": 30000,
            "recommended": 17500
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
        "conflicts": [
            "Large budget variation in group",
            "Different travel styles preferred"
        ]
    },
    "tool_results": {},
    "itinerary": None,
    "repair_instructions": None,
}

print(f"\n📌 Trip: {initial_state['trip']['title']}")
print(f"👥 Group size: {initial_state['aggregated_data']['groupSize']}")
print(f"💰 Budget: ₹{initial_state['aggregated_data']['budget']['min']} – ₹{initial_state['aggregated_data']['budget']['max']}")

result = graph.invoke(initial_state)

print("\n" + "=" * 60)
print("🏁 FINAL RESULT")
print("=" * 60)

if result["itinerary"]:
    print(json.dumps(result["itinerary"], indent=2))
else:
    print("❌ Failed to generate an itinerary.")