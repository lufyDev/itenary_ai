# ItineraryAI — AI Microservice

> **Live** as part of [itineraryai.in](https://itineraryai.in) — this is an internal microservice, not directly exposed to the public. It's called by the main backend.

This is the AI brain behind [ItineraryAI](https://github.com/lufyDev/itenaryAI), a group trip planning system. The main app (Node.js + Next.js) handles user auth, trip creation, survey collection, and preference aggregation. Once all group members have submitted their preferences and the system has aggregated them, the main backend fires a request to this microservice — and this is where the magic happens.

This microservice takes in the group's aggregated travel preferences and generates a detailed, day-by-day itinerary using an **agentic LLM pipeline** with real-time web research, a planner-critic feedback loop, and a RAG-backed caching layer.

## How It Fits Into the System

```
┌─────────────────────────────────────────────────────┐
│              Main ItineraryAI Backend               │
│                                                     │
│  User auth, trip creation, surveys, aggregation     │
│                                                     │
│  POST /generate-itinerary-stream ───────────────►   │
└─────────────────────────────────┬───────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │   This Microservice     │
                    │                         │
                    │  Agentic LLM pipeline   │
                    │  Web research tools     │
                    │  RAG cache (ChromaDB)   │
                    │                         │
                    │  ◄── SSE stream back ── │
                    └─────────────────────────┘
```

The main backend sends a POST request with the trip info and aggregated group data. This microservice streams back the itinerary as Server-Sent Events (SSE) so the frontend can show real-time progress as the AI works through its planning loop.

## Architecture

The core of this service is an **agentic loop** built with [LangGraph](https://github.com/langchain-ai/langgraph). It's not a single LLM call — it's a multi-step workflow where different "nodes" collaborate to produce a high-quality itinerary.

### The Loop

```
                    ┌──────────┐
          ┌────────►│ Planner  │◄────────────────────┐
          │         └────┬─────┘                     │
          │              │                           │
          │     (no itinerary yet?)          (needs revision?)
          │              │                           │
          │              ▼                           │
          │         ┌──────────┐              ┌──────────┐
          └─────────│  Tools   │              │  Critic  │
                    └──────────┘              └────┬─────┘
                                                   │
                                              (all good?)
                                                   │
                                                   ▼
                                                  END
```

**1. Planner** — The planner is the main brain. It uses OpenAI's `gpt-4o-mini` model. On its first run, it sees that there's no research data yet, so it asks for a tool call. After the tools return with real data, the planner uses that data (combined with its own knowledge) to craft a full itinerary.

**2. Tools** — Three research tools run **in parallel** using a thread pool:
   - **Destination Research** — Searches for things to do, local attractions, cafes, events, activities at the destination.
   - **Stay/Accommodation Research** — Finds real hotels, hostels, homestays with pricing for the group's preferred accommodation type.
   - **Transport Research** — Finds routes and costs from the source city to the destination (buses, trains, cabs, etc.).

**3. Critic** — Once the planner produces an itinerary, the critic reviews it. It runs two layers of checks:
   - **Structural checks** (no LLM needed) — Are all required fields present? Does the day count match? Are costs actual numbers?
   - **LLM review** — Does the itinerary respect the budget range? Are non-negotiables honored? Is the pacing realistic? Are group conflicts addressed in the trade-off explanation?

   If the critic finds issues, it sends repair instructions back to the planner, which tries again. This loop runs up to **3 attempts** before giving up with whatever it has.

### RAG Pipeline (Cost Optimization)

Every tool search goes through a **RAG (Retrieval-Augmented Generation) cache** powered by ChromaDB and OpenAI embeddings.

```
Tool needs data for "Jibhi"
        │
        ▼
  Has fresh data in ChromaDB? ──── Yes ──► Retrieve from cache
        │                                    (skip Tavily API call)
        No
        │
        ▼
  Search via Tavily API
        │
        ▼
  Embed results with OpenAI
  (text-embedding-3-small)
        │
        ▼
  Store in ChromaDB with metadata
  (destination, category, timestamp)
        │
        ▼
  Retrieve relevant chunks
```

The idea is simple: if someone already searched for "Jibhi" recently, we don't burn another Tavily API call. The cached embeddings are valid for **30 days**, after which a fresh search is triggered.

Each tool stores its data under a separate category (`research`, `stays`, `transport`), so they don't step on each other.

## API Contract

### Endpoint

```
POST /generate-itinerary-stream
Content-Type: application/json
```

### Request Body

```json
{
  "trip": {
    "title": "Jibhi Weekend Getaway",
    "source": "Delhi",
    "destination": "Jibhi",
    "durationDays": 3,
    "departurePreference": "evening",
    "returnPreference": "morning"
  },
  "aggregated_data": {
    "source": "Delhi",
    "destination": "Jibhi",
    "groupSize": 3,
    "budget": {
      "min": 5000,
      "max": 15000,
      "recommended": 10000
    },
    "majorityPreferences": {
      "travelStyle": "balanced",
      "foodPreference": "non-veg",
      "accommodationType": "budget-hotel"
    },
    "topActivities": ["trekking", "waterfalls", "local-markets", "camping", "cafes"],
    "nonNegotiables": ["no-flights", "no-alcohol"],
    "conflicts": ["some members wanted luxury, others wanted budget"]
  }
}
```

| Field | Description |
|-------|-------------|
| `trip.title` | Name of the trip |
| `trip.source` | Origin city (where the group is traveling from) |
| `trip.destination` | Where the group is going |
| `trip.durationDays` | Days at the destination (travel days before and after aren't counted) |
| `trip.departurePreference` | Optional. When to leave the source: `morning`, `afternoon`, `evening` or `any` (default) |
| `trip.returnPreference` | Optional. When to be back at the source, same values |
| `aggregated_data.groupSize` | Number of people in the group |
| `aggregated_data.budget` | Min/max/recommended budget per person (INR) |
| `aggregated_data.majorityPreferences` | What most of the group voted for |
| `aggregated_data.topActivities` | Top 5 activities the group wants to do |
| `aggregated_data.nonNegotiables` | Hard constraints (e.g., "no-flights", "vegetarian-only") |
| `aggregated_data.conflicts` | Detected disagreements between group members |

### Response (SSE Stream)

The response is a `text/event-stream`. Each event is a JSON payload showing which node just ran and the current state:

```
data: {"node": "planner", "state": { ... }}

data: {"node": "tool", "state": { ... }}

data: {"node": "planner", "state": { ... }}

data: {"node": "critic", "state": { ... }}

data: [DONE]
```

The `node` field tells you which part of the pipeline just completed (`planner`, `tool`, or `critic`). When the node is `planner` and the state contains an `itinerary`, that's the generated plan.

### Itinerary Schema

The final itinerary (found in the state when the planner produces it) looks like this:

```json
{
  "summary": "Two days in Jibhi, overnight bus both ways...",
  "days": [
    {
      "day": 0,
      "schedule": [
        {"start": "19:00", "end": "19:45", "kind": "travel", "activity": "Metro to ISBT Kashmere Gate..."},
        {"start": "20:30", "end": "06:30", "kind": "travel", "activity": "Overnight Volvo Delhi to Aut, ~10 hrs, ₹1,250..."}
      ],
      "stay": "Overnight Volvo (Delhi to Aut)",
      "estimatedCostPerPerson": 1300
    },
    {
      "day": 1,
      "schedule": [
        {"start": "06:30", "end": "08:30", "kind": "travel", "activity": "Shared cab Aut to Jibhi..."},
        {"start": "08:30", "end": "10:00", "kind": "rest", "activity": "Check in, breakfast..."},
        {"start": "10:30", "end": "12:30", "kind": "activity", "activity": "Walk to Jibhi Waterfall..."}
      ],
      "stay": "Riverside guesthouse, Jibhi",
      "estimatedCostPerPerson": 2400
    },
    {
      "day": 2,
      "schedule": [
        {"start": "08:00", "end": "12:30", "kind": "activity", "activity": "Serolsar Lake trek..."},
        {"start": "19:30", "end": "05:30", "kind": "travel", "activity": "Overnight Volvo Aut to Delhi..."}
      ],
      "stay": "Overnight Volvo (Aut to Delhi)",
      "estimatedCostPerPerson": 2900
    }
  ],
  "totalEstimatedCostPerPerson": 6600,
  "tradeOffExplanation": "The group had a mix of budget and adventure preferences..."
}
```

Each day is a list of timed entries (24-hour `HH:MM`, `kind` is `travel`, `activity`, `meal` or `rest`). An entry whose `end` is earlier than its `start` runs past midnight: an overnight bus is one entry, it ends its day, and the next day can't start before it arrives. Days are calendar dates.

`durationDays` counts days **at the destination** (Day 1 to Day N). Journeys don't eat into them: a long journey out goes on **Day 0**, the day before Day 1, and a long daytime journey back goes on **Day N+1**. An overnight return leaves on the evening of Day N and needs no extra day. So a "3-day" Delhi→Manali trip is Day 0 (Friday-night bus), Days 1–3 (Sat–Mon), and an overnight bus home from Day 3 arriving Tuesday morning. The example above is the 2-day demo trip.

The trip can carry `departurePreference` (when to leave the source) and `returnPreference` (when to be back there), each `morning` (04:00–11:59), `afternoon` (12:00–16:59), `evening` (17:00–23:59) or `any` (the default).

What code checks and fixes, without the LLM (`schedule.py`, `planner.py`):
- entries in time order with no overlaps; an overnight entry is the last of its day
- entries the planner put after an overnight bus on the same day move to the next morning, when they fit
- the return leg takes about as long as the outbound one
- days are numbered 1..N, with optional travel days 0 and N+1
- a 6+ hour journey on Day 1 or a daytime one on Day N gets sent to Day 0 / Day N+1
- no day at the destination starts after midday (a wasted last morning)
- zero-length entries are dropped
- Day 1's first travel starts in the departure window; the last travel arrives in the return window, with the rejection working out when to leave
- the trip total is recomputed as the sum of the day costs

Itineraries saved before this format have `morning` / `afternoon` / `evening` strings instead of `schedule`; the frontend renders both.

All costs are in **INR (₹) per person**. Day 1 always includes travel from the source city, and the last day includes the return journey.

## Tech Stack

| Component | What's Used |
|-----------|-------------|
| API Framework | FastAPI |
| LLM (Planner & Critic) | OpenAI — `gpt-4o-mini` |
| Embeddings | OpenAI — `text-embedding-3-small` |
| Agent Framework | LangGraph |
| Vector Database | ChromaDB (persistent, local) |
| Web Search | Tavily API |
| Streaming | SSE via FastAPI's `StreamingResponse` |

## Project Structure

```
├── api.py              # FastAPI app — SSE streaming endpoint
├── main.py             # CLI entrypoint for local testing
├── graph.py            # LangGraph workflow — wires planner, tools, critic
├── state.py            # AgentState TypedDict (shared state shape)
├── planner.py          # Planner node — LLM generates or revises the itinerary
├── critic.py           # Critic node — structural + LLM validation
├── rag_tool.py         # RAG layer — ChromaDB embed/store/retrieve
├── web_search.py       # Tavily search wrapper (research, stays, transport)
├── ingest.py           # One-off script to seed ChromaDB with local data
├── tools/
│   ├── __init__.py     # Runs all three tools in parallel
│   ├── research.py     # Destination research tool
│   ├── stays.py        # Accommodation search tool
│   └── transport.py    # Transport routes tool
└── data/
    └── jibhi_guide.txt # Sample local travel guide for seeding
```

## Setup

### Prerequisites

- Python 3.11+
- API keys for OpenAI and Tavily

### 1. Clone and set up the virtual environment

```bash
git clone <repo-url>
cd itenary_ai

python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install fastapi uvicorn openai langgraph chromadb tavily-python python-dotenv pydantic
```

### 3. Set up environment variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
```

| Variable | What It's For |
|----------|---------------|
| `OPENAI_API_KEY` | Used by the planner, critic, and RAG layer for LLM calls and text embeddings |
| `TAVILY_API_KEY` | Used by the web search module for real-time destination research |

### 4. Run the server

```bash
uvicorn api:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

### (Optional) Run locally via CLI

If you want to test the pipeline without the API, you can use the CLI entrypoint:

```bash
python main.py
```

This runs a hardcoded Jibhi trip through the full pipeline and prints the result.

### (Optional) Seed ChromaDB

To pre-populate the vector database with a local travel guide:

```bash
python ingest.py
```

This loads `data/jibhi_guide.txt` into ChromaDB so the tools can retrieve it without hitting the Tavily API.

## Production Deployment

This microservice runs as a Docker container on **Railway**, in the same project as the main ItineraryAI API. See [DEPLOY.md](./DEPLOY.md) for the steps.

- **Not exposed to the internet**: it has no public domain, and the main Node.js backend calls it over Railway's private network
- A **volume** at `/app/chroma_db` keeps the destination cache across restarts and redeploys
- It **sleeps when idle** and wakes on the next request, and the backend retries while it boots

Earlier versions ran directly on an AWS EC2 instance under systemd, without containers. That instance was shut down when its free tier ended.

## Redeployment

Pushing to the deployed branch triggers a rebuild on Railway.

## Monitoring

Logs and memory use are in the service's Deployments and Metrics tabs on Railway. `GET /health` returns `{"status": "ok"}`, but calling it wakes the service if it's asleep.

## How a Request Flows

Here's what happens end-to-end when the main backend sends a request:

1. **Request arrives** at `POST /generate-itinerary-stream` with trip info and aggregated group data.

2. **Planner (Round 1)** — Sees that `tool_results` is empty. Responds with `{"action": "USE_TOOL"}` to request research.

3. **Tools run in parallel** — All three tools (research, stays, transport) fire simultaneously:
   - Each tool checks ChromaDB for cached data.
   - If no fresh cache exists, it searches the web via Tavily, embeds the results, and stores them in ChromaDB.
   - Relevant chunks are retrieved and returned.

4. **Planner (Round 2)** — Now has real data about the destination, accommodations, and transport. Uses this data plus its own knowledge to generate a complete itinerary.

5. **Critic** — Reviews the itinerary for structural correctness and quality. If it passes, we're done. If not, it sends repair instructions back to the planner.

6. **Planner (Round 3, if needed)** — Revises the itinerary based on the critic's feedback.

7. **Stream ends** — A `[DONE]` event is sent, and the frontend has the final itinerary.

Each step is streamed as an SSE event, so the frontend can show progress in real time.

## Related

- [**itenaryAI**](https://github.com/lufyDev/itenaryAI) — The main app (Node.js backend + Next.js frontend). Handles user auth, trip creation, survey collection, preference aggregation, and calls this microservice to generate itineraries.
