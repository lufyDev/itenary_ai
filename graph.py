from langgraph.graph import StateGraph, END
from state import AgentState
from planner import planner_node
from critic import critic_node
from tools import retrieve_travel_knowledge


workflow = StateGraph(AgentState)

workflow.add_node("planner", planner_node)
workflow.add_node("tool", retrieve_travel_knowledge)
workflow.add_node("critic", critic_node)


workflow.set_entry_point("planner")


def planner_router(state):

    if state["itinerary"] is None:
        print("\n  🔀 Router: planner → tool (no itinerary yet, fetching knowledge)")
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
        print("\n  🔀 Router: critic → planner (repairs needed, looping back)")
        return "planner"

    print("\n  🔀 Router: critic → END (all good, finishing!)")
    return END


workflow.add_conditional_edges(
    "critic",
    critic_router
)

graph = workflow.compile()