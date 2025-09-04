# packages/ingest/ingest_mongo.py
import os, re, time
from typing import List, Dict
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path, override=True)

SHOP = os.getenv("SHOPIFY_SHOP")
ADMIN = os.getenv("SHOPIFY_ADMIN_TOKEN")

MONGO_URI = os.getenv("MONGODB_URI")
MONGO_DB = os.getenv("MONGO_DB", "Shopify_Rag")
CHUNKS_COLL = os.getenv("MONGO_COLLECTION", "chunks")
DOCS_COLL = "documents"

def must(var: str, name: str):
    if not var:
        raise SystemExit(f"Missing {name} in .env")
    return var

must(MONGO_URI, "MONGODB_URI")

def shopify_get(path: str, params=None) -> Dict:
    must(SHOP, "SHOPIFY_SHOP")
    must(ADMIN, "SHOPIFY_ADMIN_TOKEN")
    url = f"https://{SHOP}/admin/api/2024-07{path}"
    r = requests.get(url, headers={"X-Shopify-Access-Token": ADMIN}, params=params or {}, timeout=60)
    r.raise_for_status()
    return r.json()

def clean_html(html: str) -> str:
    return re.sub("<[^<]+?>", " ", (html or "")).replace("&nbsp;", " ").strip()

def chunk_text(text: str, max_words=280) -> List[str]:
    words = (text or "").split()
    if not words:
        return []
    out, buf = [], []
    for w in words:
        buf.append(w)
        if len(buf) >= max_words:
            out.append(" ".join(buf)); buf=[]
    if buf: out.append(" ".join(buf))
    return out

def fetch_docs() -> List[Dict]:
    print("Fetching products…")
    prods = shopify_get("/products.json", params={"limit": 50, "fields": "id,title,handle,body_html,tags,variants"}).get("products", [])
    print("Fetching policies…")
    policies = shopify_get("/policies.json").get("policies", [])
    docs: List[Dict] = []
    for p in prods:
        docs.append({
            "type": "product",
            "shop_id": str(p["id"]),
            "source_url": f"/products/{p['handle']}",
            "title": p["title"],
            "body_text": clean_html(p.get("body_html") or "")
        })
    for p in policies:
        docs.append({
            "type": "policy",
            "shop_id": SHOP,
            "source_url": f"/policies/{p['title'].lower().replace(' ','-')}",
            "title": p["title"],
            "body_text": clean_html(p.get("body") or "")
        })
    return docs

def build_chunks(docs: List[Dict]) -> List[Dict]:
    chunks: List[Dict] = []
    for d in docs:
        parts = chunk_text(d["body_text"]) or [d["title"]]
        for part in parts:
            chunks.append({
                "type": d["type"],
                "title": d["title"],
                "source_url": d["source_url"],
                "text": part,
                "shop_id": d.get("shop_id")
            })
    return chunks

def main():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    coll_chunks = db[CHUNKS_COLL]
    coll_docs = db[DOCS_COLL]

    docs = fetch_docs()
    if not docs:
        print("No products/policies fetched from Shopify.")
        return

    # reset for demo
    coll_docs.delete_many({})
    coll_chunks.delete_many({})

    print(f"Writing {len(docs)} raw documents…")
    coll_docs.insert_many(docs)

    chunks = build_chunks(docs)

    # Add chunk id (optional, helpful)
    for i, c in enumerate(chunks):
        c["chunk_id"] = i

    print("Inserting chunk documents into Mongo (no embeddings)…")
    coll_chunks.insert_many(chunks)

    print("Done. Inserted", len(chunks), "chunks into", f"{MONGO_DB}.{CHUNKS_COLL}")

if __name__ == "__main__":
    main()
