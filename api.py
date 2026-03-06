import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from graph import graph

app = FastAPI()


class Budget(BaseModel):
    min: int
    max: int
    recommended: int


class MajorityPreferences(BaseModel):
    travelStyle: str
    foodPreference: str
    accommodationType: str


class Trip(BaseModel):
    title: str
    source: str
    destination: str
    durationDays: int


class AggregatedData(BaseModel):
    source: str
    destination: str
    groupSize: int
    budget: Budget
    majorityPreferences: MajorityPreferences
    topActivities: list[str] = []
    nonNegotiables: list[str] = []
    conflicts: list[str] = []


class TripRequest(BaseModel):
    trip: Trip
    aggregated_data: AggregatedData


def stream_agent(state):
    for event in graph.stream(state):
        for node, output in event.items():
            payload = {"node": node, "state": output}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield "data: [DONE]\n\n"


@app.post("/generate-itinerary-stream")
def generate_itinerary_stream(req: TripRequest):
    initial_state = {
        "trip": req.trip.model_dump(),
        "aggregated_data": req.aggregated_data.model_dump(),
        "tool_results": {},
        "itinerary": None,
        "repair_instructions": None,
        "attempt_count": 0,
    }

    return StreamingResponse(
        stream_agent(initial_state),
        media_type="text/event-stream",
    )