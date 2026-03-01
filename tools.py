from rag_tool import has_fresh_data, retrieve_knowledge, ingest_documents
from web_search import search_destination


def _build_query(state: dict) -> str:
    """Build a rich semantic query from the full trip context."""
    destination = state["trip"]["title"]
    agg = state.get("aggregated_data", {})

    parts = [destination]

    activities = agg.get("topActivities", [])
    if activities:
        parts.append(" ".join(activities))

    style = agg.get("majorityPreferences", {}).get("travelStyle")
    if style:
        parts.append(style)

    budget = agg.get("budget", {})
    if budget.get("recommended"):
        parts.append(f"budget around {budget['recommended']} INR per person")

    return " ".join(parts)


def retrieve_travel_knowledge(state: dict):

    print("\n" + "=" * 60)
    print("🔧 TOOL NODE — Destination Research")
    print("=" * 60)

    destination = state["trip"]["title"]
    query = _build_query(state)
    print(f"  📍 Destination: {destination}")
    print(f"  🔎 Query: {query}")

    if has_fresh_data(destination):
        print("  ✅ Fresh data found in cache (RAG)")
    else:
        print("  🌐 No fresh cache — running web search via Tavily...")
        docs = search_destination(destination)
        if docs:
            count = ingest_documents(destination, docs)
            print(f"  💾 Ingested {count} document(s) into RAG cache")
        else:
            print("  ⚠️  Web search returned no results")
            state["tool_results"]["rag"] = []
            return state

    results = retrieve_knowledge(query, destination)
    state["tool_results"]["rag"] = results

    print(f"  📄 Retrieved {len(results)} relevant chunk(s)")
    for i, doc in enumerate(results):
        preview = doc[:120].replace("\n", " ")
        print(f"     [{i + 1}] {preview}{'...' if len(doc) > 120 else ''}")

    return state
