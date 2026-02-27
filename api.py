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
    duration = req.trip.get("durationDays", "?")
    group_size = req.aggregated_data.get("groupSize", "?")
    budget = req.aggregated_data.get("budget", {})

    print("\n" + "=" * 60)
    print("📡 API — /generate-itinerary")
    print("=" * 60)
    print(f"  📍 Destination: {destination}")
    print(f"  📅 Duration: {duration} days")
    print(f"  👥 Group size: {group_size}")
    print(f"  💰 Budget: ₹{budget.get('min', '?')} – ₹{budget.get('max', '?')} (target ₹{budget.get('recommended', '?')}/person)")

    initial_state = {
        "trip": req.trip,
        "aggregated_data": req.aggregated_data,
        "tool_results": {},
        "itinerary": None,
        "repair_instructions": None,
        "attempt_count": 0,
    }

    try:
        start = time.time()
        result = graph.invoke(initial_state)
        elapsed = round(time.time() - start, 2)
        attempts = result.get("attempt_count", 0)

        print(f"\n  ⏱️  Pipeline completed in {elapsed}s ({attempts} attempt(s))")

        if result["itinerary"] is None:
            print("  ❌ Pipeline finished but no itinerary was generated")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate itinerary after {attempts} attempt(s)"
            )

        print("  ✅ Itinerary returned to client")
        return {"itinerary": result["itinerary"]}

    except HTTPException:
        raise

    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))