import hashlib
from datetime import datetime, timedelta, timezone

from openai import OpenAI
import chromadb
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

chroma = chromadb.PersistentClient(path="./chroma_db")
collection = chroma.get_or_create_collection("travel")

MAX_AGE_DAYS = 30


def _embed(text: str) -> list[float]:
    return client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    ).data[0].embedding


def has_fresh_data(destination: str) -> bool:
    """Check if we already have non-stale docs for a destination."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).timestamp()
    results = collection.get(
        where={
            "$and": [
                {"destination": destination.lower()},
                {"ingested_at": {"$gte": cutoff}},
            ]
        },
        limit=1,
    )
    return len(results["ids"]) > 0


def retrieve_knowledge(query: str, destination: str) -> list[str]:
    """Retrieve cached docs for a destination using semantic search."""
    try:
        embedding = _embed(query)
        results = collection.query(
            query_embeddings=[embedding],
            n_results=5,
            where={"destination": destination.lower()},
        )
        return results["documents"][0] if results["documents"] else []
    except Exception as e:
        print(f"[RAG] Error retrieving knowledge: {e}")
        return []


def ingest_documents(destination: str, documents: list[str]) -> int:
    """Embed and store documents in ChromaDB, returns count ingested."""
    now = datetime.now(timezone.utc).timestamp()
    dest_key = destination.lower()

    # Remove old docs for this destination before re-ingesting
    try:
        old = collection.get(where={"destination": dest_key})
        if old["ids"]:
            collection.delete(ids=old["ids"])
    except Exception:
        pass

    ids, embeddings, metadatas = [], [], []
    for i, doc in enumerate(documents):
        doc_hash = hashlib.md5(doc.encode()).hexdigest()[:10]
        ids.append(f"{dest_key}-{i}-{doc_hash}")
        embeddings.append(_embed(doc))
        metadatas.append({"destination": dest_key, "ingested_at": now})

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return len(ids)
