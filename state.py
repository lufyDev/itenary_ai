from typing import TypedDict, Dict, Any


class AgentState(TypedDict):
    trip: dict
    aggregated_data: dict
    tool_results: Dict[str, Any]
    itinerary: dict | None
    repair_instructions: dict | None
    attempt_count: int