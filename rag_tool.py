from openai import OpenAI
import chromadb
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

chroma = chromadb.PersistentClient(
    path="./chroma_db"
)

collection = chroma.get_collection("travel")


def retrieve_knowledge(query: str):

    try:
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        ).data[0].embedding

        results = collection.query(
            query_embeddings=[embedding],
            n_results=2
        )

        return results["documents"][0]

    except Exception as e:
        print(f"[RAG] Error retrieving knowledge: {e}")
        return []