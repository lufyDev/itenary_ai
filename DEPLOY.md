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

A scale-to-zero container host (Cloud Run, Fly.io) sidesteps both: the 400MB
is irrelevant in an image, the filesystem is writable, streaming is native,
and the request timeout is minutes not seconds.

The `chroma_db/` directory is gitignored but **not** in `.dockerignore`, so
`docker build` copies your local copy into the image and the container starts
with a pre-warmed cache. Writes at runtime work but only last the lifetime of
the instance — see "Known limits".

## Deploy (Cloud Run)

```bash
gcloud run deploy itineraryai-agent \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600 \
  --concurrency 4 \
  --max-instances 2 \
  --set-env-vars "OPENAI_API_KEY=...,TAVILY_API_KEY=..."
```

Flags that matter:

- `--timeout 600` — the agent loop runs up to 3 planner/critic attempts. The
  Express proxy gives up at 180s; keep this comfortably above that.
- `--concurrency 4` — a generation is CPU- and memory-heavy. The default of 80
  would let a handful of requests thrash one instance.
- `--max-instances 2` — spend ceiling. Also keeps the in-memory rate limiter
  on the Express side roughly honest.
- `--memory 2Gi` — chromadb + langgraph imports are not small, and Chroma's
  store counts against memory on Cloud Run.

Scale-to-zero is the default (`--min-instances 0`), which is what keeps this
near free. Cold start is roughly 8-15s while chromadb and langgraph import.
If that ever matters, `--min-instances 1` removes it for a few dollars a month.

## Local

```bash
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

`main.py` is the CLI harness for running the graph without HTTP. It is
excluded from the image.

## Env

See `.env.example`. `OPENAI_API_KEY` and `TAVILY_API_KEY` are required;
`GROQ_API_KEY` only matters if the planner/critic get switched back to Groq.

**Set a hard spend cap on the OpenAI account.** This service is reachable
from the public internet and spends money per call.

## Known limits

- **Cache is per-instance.** `chroma_db/` ships pre-warmed in the image and is
  writable at runtime, but a new instance starts from the baked copy and
  anything ingested since is lost. Acceptable for a demo. The real fix is
  moving these vectors into MongoDB Atlas Vector Search — embeddings already
  come from OpenAI `text-embedding-3-small`, so Chroma is pure vector storage
  here, and the move would also drop ~240MB of dependencies.
- **If the image build fails on a missing wheel**, add
  `RUN apt-get update && apt-get install -y --no-install-recommends build-essential`
  before the `pip install` line. All current deps publish cp313 manylinux
  wheels, so it should not be needed.
