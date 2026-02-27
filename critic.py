def critic_node(state):

    print("\n" + "=" * 60)
    print("🔍 CRITIC NODE")
    print("=" * 60)

    if state["itinerary"] is None:
        print("  ⏭️  No itinerary to review, skipping")
        return state

    if len(state["tool_results"]) == 0:
        print("  ❌ Verdict: REJECTED — no knowledge was retrieved")
        state["repair_instructions"] = {
            "reason": "Missing knowledge"
        }
        state["itinerary"] = None
    else:
        print("  ✅ Verdict: APPROVED — itinerary looks good")
        state["repair_instructions"] = None

    return state