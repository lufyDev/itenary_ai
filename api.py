import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from graph import graph

app = FastAPI()


class TripRequest(BaseModel):
    trip: dict
    aggregated_data: dict


def stream_agent(state):
    for event in graph.stream(state):
        for node, output in event.items():
            payload = {"node": node, "state": output}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield "data: [DONE]\n\n"


@app.post("/generate-itinerary-stream")
def generate_itinerary_stream(req: TripRequest):
    initial_state = {
        "trip": req.trip,
        "aggregated_data": req.aggregated_data,
        "tool_results": {},
        "itinerary": None,
        "repair_instructions": None,
        "attempt_count": 0,
    }

    return StreamingResponse(
        stream_agent(initial_state),
        media_type="text/event-stream",
    )