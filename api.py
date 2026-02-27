import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from graph import graph

app = FastAPI()


class TripRequest(BaseModel):
    trip: dict
    aggregated_data: dict


@app.post("/generate-itinerary")
def generate_itinerary(req: TripRequest):

    destination = req.trip.get("title", "Unknown")
    group_size = req.aggregated_data.get("groupSize", "?")

    print("\n" + "=" * 60)
    print("📡 API — /generate-itinerary")
    print("=" * 60)
    print(f"  📍 Destination: {destination}")
    print(f"  👥 Group size: {group_size}")

    initial_state = {
        "trip": req.trip,
        "aggregated_data": req.aggregated_data,
        "tool_results": {},
        "itinerary": None,
        "repair_instructions": None,
    }

    try:
        start = time.time()
        result = graph.invoke(initial_state)
        elapsed = round(time.time() - start, 2)

        print(f"\n  ⏱️  Pipeline completed in {elapsed}s")

        if result["itinerary"] is None:
            print("  ❌ Pipeline finished but no itinerary was generated")
            raise HTTPException(status_code=500, detail="Failed to generate itinerary")

        print("  ✅ Itinerary returned to client")
        return {"itinerary": result["itinerary"]}

    except HTTPException:
        raise

    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))