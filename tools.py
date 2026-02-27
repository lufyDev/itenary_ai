from rag_tool import retrieve_knowledge


def retrieve_travel_knowledge(state: dict):

    print("\n" + "=" * 60)
    print("🔧 TOOL NODE — RAG Retrieval")
    print("=" * 60)

    try:
        destination = state["trip"]["title"]
        print(f"  🔎 Searching knowledge base for: \"{destination}\"")

        docs = retrieve_knowledge(destination)
        state["tool_results"]["rag"] = docs

        print(f"  📄 Retrieved {len(docs)} document(s)")
        for i, doc in enumerate(docs):
            preview = doc[:120].replace("\n", " ")
            print(f"     [{i+1}] {preview}{'...' if len(doc) > 120 else ''}")

    except Exception as e:
        print(f"  ❌ Error fetching travel knowledge: {e}")
        state["tool_results"]["rag"] = []

    return state