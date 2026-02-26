from rag_tool import retrieve_knowledge


def retrieve_travel_knowledge(state: dict):

    try:
        destination = state["trip"]["title"]
        docs = retrieve_knowledge(destination)
        state["tool_results"]["rag"] = docs
    except Exception as e:
        print(f"[Tool] Error fetching travel knowledge: {e}")
        state["tool_results"]["rag"] = []

    return state