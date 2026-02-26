from dotenv import load_dotenv
from openai import OpenAI
import chromadb

load_dotenv()

client = OpenAI()

# vector database
chroma = chromadb.PersistentClient(path="./chroma_db")

collection = chroma.get_or_create_collection("travel")

with open("data/jibhi_guide.txt") as f:
    text = f.read()

embedding = client.embeddings.create(
    model="text-embedding-3-small",
    input=text
).data[0].embedding

collection.add(
    documents=[text],
    embeddings=[embedding],
    ids=["jibhi_doc"]
)

print("Knowledge stored ✅")