from rag_tool import has_fresh_data, retrieve_knowledge, ingest_documents
from web_search import search_stays

CATEGORY = "stays"


def stays_tool(state: dict) -> list[str]:
    """Gather accommodation options and pricing."""

    destination = state["trip"]["title"]
    agg = state.get("aggregated_data", {})

    accom_type = agg.get("majorityPreferences", {}).get("accommodationType", "budget hotel")
    budget = agg.get("budget", {})
    query = f"{destination} {accom_type} stay cost {budget.get('min', '')}-{budget.get('max', '')} INR"

    print(f"\n  🏨 [Stays] destination={destination}  query={query}")

    if has_fresh_data(destination, CATEGORY):
        print("     ✅ Cache hit")
    else:
        print("     🌐 Searching web...")
        docs = search_stays(destination, accom_type)
        if docs:
            count = ingest_documents(destination, CATEGORY, docs)
            print(f"     💾 Ingested {count} doc(s)")
        else:
            print("     ⚠️  No results")
            return []

    results = retrieve_knowledge(query, destination, CATEGORY)
    print(f"     📄 Retrieved {len(results)} chunk(s)")
    return results
