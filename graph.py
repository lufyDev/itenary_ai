from langgraph.graph import StateGraph, END
from state import AgentState
from planner import planner_node
from critic import critic_node
from tools import run_all_tools


workflow = StateGraph(AgentState)

workflow.add_node("planner", planner_node)
workflow.add_node("tool", run_all_tools)
workflow.add_node("critic", critic_node)


workflow.set_entry_point("planner")


MAX_ATTEMPTS = 3


def planner_router(state):

    if state["itinerary"] is None:
        # Tools only run once. A planner that comes back empty after that
        # (bad JSON, API error) used to be sent to the tool node again, which
        # looped until LangGraph's recursion limit crashed the stream.
        if state.get("tool_results"):
            attempts = state.get("attempt_count", 0)
            if attempts >= MAX_ATTEMPTS:
                print(f"\n  🔀 Router: planner → END (no itinerary after {attempts} attempts)")
                return END
            print("\n  🔀 Router: planner → planner (no itinerary returned, retrying)")
            return "planner"
        print("\n  🔀 Router: planner → tool (LLM requested knowledge lookup)")
        return "tool"

    print("\n  🔀 Router: planner → critic (itinerary ready for review)")
    return "critic"


workflow.add_conditional_edges(
    "planner",
    planner_router
)

workflow.add_edge("tool", "planner")


def critic_router(state):

    if state["repair_instructions"]:
        attempts = state.get("attempt_count", 0)
        if attempts >= MAX_ATTEMPTS:
            print(f"\n  🔀 Router: critic → END (max {MAX_ATTEMPTS} attempts reached, giving up)")
            return END
        print(f"\n  🔀 Router: critic → planner (repairs needed, attempt {attempts}/{MAX_ATTEMPTS})")
        return "planner"

    print("\n  🔀 Router: critic → END (all good, finishing!)")
    return END


workflow.add_conditional_edges(
    "critic",
    critic_router
)

graph = workflow.compile()