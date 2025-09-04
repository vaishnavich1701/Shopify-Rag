# run_ONCE_CREATE_TEXT_INDEX.PY
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path
import os, sys, traceback

# 1) Load .env from project root (the file in the same folder as this script)
env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    print("ERROR: .env not found at", env_path)
    sys.exit(1)

load_dotenv(dotenv_path=env_path)

MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
MONGO_DB  = os.getenv("MONGO_DB", "Shopify_Rag")
CHUNKS_COLL = os.getenv("MONGO_COLLECTION", "chunks")

if not MONGO_URI:
    print("ERROR: MONGODB_URI not set in .env")
    sys.exit(1)

# Masked print (for logging) - do not print full password in shared logs
def mask_uri(uri: str) -> str:
    try:
        if "@" in uri:
            head, tail = uri.split("@", 1)
            if ":" in head:
                user, pwd = head.split(":", 1)
                user = user.split("//")[-1]
                return f"{uri.split('//')[0]}//{user}:<REDACTED>@{tail}"
    except Exception:
        pass
    return "<uri-present>"

print("Using MONGO_URI:", mask_uri(MONGO_URI))
print("DB:", MONGO_DB, "Collection:", CHUNKS_COLL)

# 2) Connect to MongoDB with short timeout and test connection
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000, connectTimeoutMS=8000)
    info = client.server_info()  # will raise if cannot connect
    print("Connected to MongoDB server version:", info.get("version"))
except Exception as e:
    print("ERROR: cannot connect to MongoDB. Details below:")
    traceback.print_exc()
    sys.exit(2)

# 3) Create index
db = client[MONGO_DB]
coll = db[CHUNKS_COLL]
print("Creating text index on 'text' and 'title' (this may take a while on large collections)...")
idx_name = "text_title_index"
# If index already exists, this is idempotent
try:
    coll.create_index([("text", "text"), ("title", "text")], name=idx_name)
    print("Index created (or already existed).")
except Exception:
    print("Failed to create index:")
    traceback.print_exc()
    sys.exit(3)
