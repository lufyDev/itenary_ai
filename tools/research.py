from rag_tool import has_fresh_data, retrieve_knowledge, ingest_documents
from web_search import search_research

CATEGORY = "research"


def research_tool(state: dict) -> list[str]:
    """Gather destination guide info: places, cafes, events, activities."""

    destination = state["trip"]["destination"]
    agg = state.get("aggregated_data", {})

    parts = [destination]
    activities = agg.get("topActivities", [])
    if activities:
        parts.append(" ".join(activities))
    style = agg.get("majorityPreferences", {}).get("travelStyle")
    if style:
        parts.append(style)
    query = " ".join(parts)

    print(f"\n  📍 [Research] destination={destination}  query={query}")

    if has_fresh_data(destination, CATEGORY):
        print("     ✅ Cache hit")
    else:
        print("     🌐 Searching web...")
        docs = search_research(destination)
        if docs:
            count = ingest_documents(destination, CATEGORY, docs)
            print(f"     💾 Ingested {count} doc(s)")
        else:
            print("     ⚠️  No results")
            return []

    results = retrieve_knowledge(query, destination, CATEGORY)
    print(f"     📄 Retrieved {len(results)} chunk(s)")
    return results
