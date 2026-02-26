def critic_node(state):

    if state["itinerary"] is None:
        return state

    if len(state["tool_results"]) == 0:
        state["repair_instructions"] = {
            "reason": "Missing knowledge"
        }
        state["itinerary"] = None
    else:
        state["repair_instructions"] = None

    return state