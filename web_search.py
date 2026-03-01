import os
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

SEARCH_QUERIES = [
    "{dest} travel guide things to do best places to visit",
    "{dest} budget accommodation hostels hotels cost per night",
    "{dest} how to reach transport options from Delhi Mumbai Bangalore",
]


def search_destination(destination: str) -> list[str]:
    """Run multiple Tavily searches and return cleaned document chunks."""
    all_docs: list[str] = []
    seen_urls: set[str] = set()

    for template in SEARCH_QUERIES:
        query = template.format(dest=destination)
        try:
            response = tavily.search(
                query=query,
                max_results=5,
                search_depth="basic",
                include_answer=True,
            )

            if response.get("answer"):
                all_docs.append(
                    f"[Summary — {query}]\n{response['answer']}"
                )

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

    print(f"[WebSearch] Collected {len(all_docs)} document(s) for '{destination}'")
    return all_docs
