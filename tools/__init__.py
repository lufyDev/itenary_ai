from concurrent.futures import ThreadPoolExecutor, as_completed
from tools.research import research_tool
from tools.stays import stays_tool
from tools.transport import transport_tool


def run_all_tools(state: dict) -> dict:
    """Run all three research tools in parallel and merge results into state."""

    print("\n" + "=" * 60)
    print("🔧 TOOL NODE — Parallel Destination Research")
    print("=" * 60)

    tool_fns = {
        "research": research_tool,
        "stays": stays_tool,
        "transport": transport_tool,
    }

    results: dict[str, list[str]] = {}

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fn, state): name for name, fn in tool_fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"  ❌ [{name}] failed: {e}")
                results[name] = []

    state["tool_results"] = results

    total = sum(len(v) for v in results.values())
    print(f"\n  📊 Total chunks: {total}  "
          f"(research={len(results.get('research', []))}, "
          f"stays={len(results.get('stays', []))}, "
          f"transport={len(results.get('transport', []))})")

    return state
