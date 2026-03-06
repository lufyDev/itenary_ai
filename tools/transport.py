from rag_tool import has_fresh_data, retrieve_knowledge, ingest_documents
from web_search import search_transport

CATEGORY = "transport"


def transport_tool(state: dict) -> list[str]:
    """Gather transport routes and costs from source to destination."""

    destination = state["trip"]["destination"]
    source = state["trip"]["source"]
    budget = state.get("aggregated_data", {}).get("budget", {}).get("recommended")

    query = f"{source} to {destination} transport cost budget {budget or ''} INR"

    print(f"\n  🚌 [Transport] {source} → {destination}  query={query}")

    if has_fresh_data(destination, CATEGORY):
        print("     ✅ Cache hit")
    else:
        print("     🌐 Searching web...")
        docs = search_transport(source, destination, budget)
        if docs:
            count = ingest_documents(destination, CATEGORY, docs)
            print(f"     💾 Ingested {count} doc(s)")
        else:
            print("     ⚠️  No results")
            return []

    results = retrieve_knowledge(query, destination, CATEGORY)
    print(f"     📄 Retrieved {len(results)} chunk(s)")
    return results
