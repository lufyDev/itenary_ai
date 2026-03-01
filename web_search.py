import os
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def _run_searches(queries: list[str]) -> list[str]:
    """Run a list of Tavily queries, deduplicate, and return cleaned doc chunks."""
    all_docs: list[str] = []
    seen_urls: set[str] = set()

    for query in queries:
        try:
            response = tavily.search(
                query=query,
                max_results=5,
                search_depth="basic",
                include_answer=True,
            )

            if response.get("answer"):
                all_docs.append(f"[Summary — {query}]\n{response['answer']}")

            for result in response.get("results", []):
                url = result.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                content = result.get("content", "").strip()
                if not content or len(content) < 80:
                    continue

                title = result.get("title", "")
                all_docs.append(f"[{title}] ({url})\n{content}")

        except Exception as e:
            print(f"[WebSearch] Query failed: {query!r} — {e}")

    return all_docs


def search_research(destination: str) -> list[str]:
    """Search for destination guide: places, cafes, events, activities."""
    queries = [
        f"{destination} travel guide things to do best places to visit",
        f"{destination} famous cafes restaurants local food events activities",
    ]
    docs = _run_searches(queries)
    print(f"[WebSearch:research] Collected {len(docs)} doc(s) for '{destination}'")
    return docs


def search_stays(destination: str, accommodation_type: str) -> list[str]:
    """Search for accommodation options and pricing."""
    queries = [
        f"{destination} {accommodation_type} cost per night reviews",
        f"{destination} best hostels budget hotels where to stay prices",
    ]
    docs = _run_searches(queries)
    print(f"[WebSearch:stays] Collected {len(docs)} doc(s) for '{destination}'")
    return docs


def search_transport(source: str, destination: str, budget: int | None) -> list[str]:
    """Search for transport routes and costs from source to destination."""
    budget_hint = f"under {budget} INR" if budget else ""
    queries = [
        f"{source} to {destination} how to reach best transport options bus train {budget_hint}".strip(),
        f"{source} to {destination} travel cost cheapest route duration",
    ]
    docs = _run_searches(queries)
    print(f"[WebSearch:transport] Collected {len(docs)} doc(s) for '{source} → {destination}'")
    return docs
