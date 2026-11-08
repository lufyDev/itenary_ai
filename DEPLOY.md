# Deploying the agent service

FastAPI + LangGraph, one real endpoint (`POST /generate-itinerary-stream`,
Server-Sent Events) plus `GET /health`.

## Why a container and not Lambda

Two hard constraints, both found in the code:

1. **Bundle size.** `site-packages` is ~400MB — `onnxruntime` (71MB),
   `kubernetes` (81MB), `chromadb_rust_bindings` (50MB), `grpc` (39MB), all
   pulled in by `chromadb`. Lambda's zip limit is 250MB unzipped, so Lambda
   would mean a container image via ECR anyway.
2. **Writable filesystem.** `rag_tool.py` uses
   `chromadb.PersistentClient(path="./chroma_db")` and `ingest_documents()`
   writes to it. Lambda's only writable directory is an ephemeral `/tmp`, so
   the destination cache would die on every cold start and every request
   would re-run three Tavily searches plus re-embedding.

A container on Railway sidesteps both: the 400MB is irrelevant in an image, a
volume gives Chroma a disk that lasts, and streaming works natively.

## Deploy (Railway)

Add this as a service in the **same Railway project** as the Express API, from
the `lufyDev/itenary_ai` repo. Railway finds the Dockerfile at the repo root.

Variables:

```
OPENAI_API_KEY=...
TAVILY_API_KEY=...
PORT=8080
```

Settings:

- **Networking: do not generate a public domain.** This service has no auth of
  its own, so only Express should be able to reach it. Railway gives it a private
  address automatically, shown as `RAILWAY_PRIVATE_DOMAIN` under "variables added
  by Railway". Express calls that address on port 8080, which is why `PORT` is
  fixed above.
- **Service name:** `itineraryai-agent`, for readability. Click the service card
  to rename it. This doesn't need a redeploy, and it doesn't change the private
  address, which stays what Railway set when the service was created
  (`itenaryai.railway.internal` for this one).
- **Volume: mount one at `/app/chroma_db`.** This is what keeps the destination
  cache across restarts and redeploys.
- **Serverless: turn on.** The agent sleeps when idle, which is most of what
  keeps this near the plan's included $5. Express retries while it wakes.
- **Healthcheck path:** `/health`.
- **Memory limit:** 2 GB is a sensible ceiling to start with. Check actual use
  in the metrics tab after a few generations and lower it if you can.

Cold start is roughly 8-15s while chromadb and langgraph import. If that ever
matters, turning serverless off removes it, for a few dollars more a month.

### The cache starts empty

`chroma_db/` is gitignored, so an image built from GitHub doesn't include your
local copy, and the volume starts empty anyway. The first trip to each
destination pays for its Tavily searches and embeddings, and later trips reuse
them. Running `docker build` locally still copies `chroma_db/` into the image,
because it isn't in `.dockerignore`, but on Railway the volume mounted over that
path hides it.

## Local

```bash
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

`main.py` is the CLI harness for running the graph without HTTP. It is
excluded from the image.

Offline tests for the critic, planner schema and graph routing (no API calls):

```bash
venv/bin/python -m unittest discover tests
```

## Env

See `.env.example`. `OPENAI_API_KEY` and `TAVILY_API_KEY` are required;
`GROQ_API_KEY` only matters if the planner/critic get switched back to Groq.

**Set a hard spend cap on the OpenAI account.** Express's rate limiter bounds
how many generations run, but only the spend cap bounds what they cost.

## Known limits

- **One instance only.** Railway doesn't allow replicas on a service with a
  volume, and Chroma's local store couldn't be shared between instances anyway.
  That's fine for a demo. The real fix is moving these vectors into MongoDB
  Atlas Vector Search — embeddings already come from OpenAI
  `text-embedding-3-small`, so Chroma is pure vector storage here, and the move
  would also drop ~240MB of dependencies.
- **If the image build fails on a missing wheel**, add
  `RUN apt-get update && apt-get install -y --no-install-recommends build-essential`
  before the `pip install` line. All current deps publish cp313 manylinux
  wheels, so it should not be needed.
