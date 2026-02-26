from graph import graph


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

result = graph.invoke(initial_state)

print(result["itinerary"])