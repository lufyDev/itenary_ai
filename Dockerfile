# ItineraryAI — LangGraph agent service (FastAPI + SSE)
#
# Built as a container rather than a Lambda zip for two reasons:
#   1. site-packages is ~400MB (onnxruntime, chromadb rust bindings, grpc),
#      well past Lambda's 250MB unzipped limit.
#   2. ChromaDB's PersistentClient needs a writable filesystem.
# See DEPLOY.md.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so this layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code. Also pulls in chroma_db/ if present locally, shipping the
# image with a pre-warmed destination cache (see .dockerignore).
COPY . .

# Cloud Run / Fly inject PORT. 8080 is the local default.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn api:app --host 0.0.0.0 --port ${PORT} --timeout-keep-alive 300"]
