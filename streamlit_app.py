# streamlit_app.py
# Single-file Streamlit UI for Shopify RAG + chat with greeting
import os
import time
import json
import traceback
import subprocess
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
import requests

# --------------------
# Load env
# --------------------
# env_path = Path(__file__).resolve().parents[1] / ".env"
# load_dotenv(dotenv_path=env_path)

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
MONGO_DB  = os.getenv("MONGO_DB", "Shopify_Rag")
CHUNKS_COLL = os.getenv("MONGO_COLLECTION", "chunks")

LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY  = os.getenv("LLM_API_KEY")

SHOP = os.getenv("SHOPIFY_SHOP")
SHOP_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")

# --------------------
# Helpers (Mongo, ingest runner, search, LLM)
# --------------------
def get_mongo_client():
    if not MONGO_URI:
        raise RuntimeError("MONGODB_URI not set in .env")
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

def run_ingest_background():
    """Run the ingest script in a detached subprocess to avoid blocking."""
    python = os.path.join(".venv", "Scripts", "python.exe")
    script = "packages/ingest/ingest_mongo.py"
    if not os.path.exists(python):
        python = "python"
    # Start background process and detach
    subprocess.Popen([python, script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def search_atlas(query: str, k: int = 6, index_name: str = "default"):
    """
    Use Atlas Search $search if available; otherwise fallback to a simple local scoring.
    Returns list of dicts with keys: score, text, title, url, highlights
    """
    if not query or not query.strip():
        return []

    client = get_mongo_client()
    db = client[MONGO_DB]
    coll = db[CHUNKS_COLL]

    pipeline = [
        {"$search": {
            "index": index_name,
            "text": {
                "query": query,
                "path": ["text", "title"]
            }
        }},
        {"$project": {
            "text": 1,
            "title": 1,
            "source_url": 1,
            "score": {"$meta": "searchScore"},
            "highlights": {"$meta": "searchHighlights"}
        }},
        {"$sort": {"score": -1}},
        {"$limit": k}
    ]

    try:
        docs = list(coll.aggregate(pipeline))
    except Exception as e:
        # Atlas Search not available or error -> fallback scoring
        print("Atlas search failed (fallback):", str(e))
        candidates = list(coll.find({}, {"text":1,"title":1,"source_url":1}).limit(500))
        q_words = [w.lower() for w in query.split() if w.strip()]
        scored = []
        for d in candidates:
            txt = (d.get("text") or "").lower()
            sc = sum(txt.count(w) for w in q_words)
            if sc:
                scored.append({"score": float(sc), "text": d.get("text",""), "title": d.get("title"), "url": d.get("source_url")})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]

    out = []
    for d in docs:
        out.append({
            "score": float(d.get("score", 0)),
            "text": d.get("text",""),
            "title": d.get("title"),
            "url": d.get("source_url"),
            "highlights": d.get("highlights", [])
        })
    return out


def call_llm(prompt: str, max_tokens: int = 512, model: str = None, system_prompt: str = None):
    """
    Call Groq / OpenAI-style chat/completions endpoint.
    - Expects LLM_BASE_URL and LLM_API_KEY in env (load_dotenv() already called).
    - model: optional override; defaults to env LLM_MODEL or "openai/gpt-oss-20b".
    - system_prompt: optional system instruction (defaults to a helpful assistant prompt).
    Returns assistant text on success or raises on non-recoverable errors.
    """
    base = os.getenv("LLM_BASE_URL")
    key  = os.getenv("LLM_API_KEY")
    if not base or not key:
        raise RuntimeError("LLM_BASE_URL / LLM_API_KEY not set in .env")

    model = model or os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
    system_prompt = system_prompt or os.getenv(
        "LLM_SYSTEM_PROMPT",
        "You are a helpful assistant. Use the provided source passages and cite sources when possible."
    )

    url = base.rstrip("/") + "/chat/completions"  # Groq / OpenAI chat endpoint
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        # you can tune temperature in .env via LLM_TEMPERATURE
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.0"))
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        # helpful debug on non-200
        if not resp.ok:
            # Include response text in the error to help debugging
            raise RuntimeError(f"LLM request failed [{resp.status_code}]: {resp.text[:2000]}")
        j = resp.json()
        # Typical chat response shape: choices[0].message.content
        if "choices" in j and len(j["choices"]) > 0:
            c = j["choices"][0]
            # Chat style
            if isinstance(c.get("message"), dict) and c["message"].get("content"):
                return c["message"]["content"]
            # fallback to legacy 'text'
            if c.get("text"):
                return c["text"]
        # fallback return entire json if shape unexpected
        return json.dumps(j)
    except Exception as e:
        # bubble up with context (caller/UI will catch and show fallback excerpts)
        raise RuntimeError(f"call_llm error: {e}") from e


# --------------------
# Streamlit UI: session state initialization & helpers
# --------------------
st.set_page_config(page_title="Shopify RAG • Streamlit", layout="wide", initial_sidebar_state="collapsed")
# small styling
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(135deg,#0b486b 0%, #3b6978 100%); color: #fff;}
    .chat-user { background: #ffdca8; color: #111; padding: .6rem; border-radius: .6rem; margin: .4rem 0;}
    .chat-bot  { background: rgba(255,255,255,0.06); color: #fff; padding: .6rem; border-radius: .6rem; margin: .4rem 0;}
    .muted { color: rgba(255,255,255,0.6); font-size: 0.9rem; }
    .small-btn { padding: .5rem 1rem; border-radius: .5rem; background: #ffd24d; color:#1b2b2f; border:none; }
    </style>
    """, unsafe_allow_html=True
)

# init session state for chat messages
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "who": "assistant",
            "text": "Hello! 👋 I’m AI Doc Assistant. How are you doing today? What can I help you with — product info, policies, returns, or something else?",
            "ts": time.time()
        }
    ]

def append_message(who: str, text: str):
    st.session_state.messages.append({"who": who, "text": text, "ts": time.time()})

def render_chat_area():
    # Render messages with simple styling
    for m in st.session_state.messages:
        if m["who"] == "user":
            st.markdown(f"<div class='chat-user'><strong>You</strong>: {m['text']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-bot'><strong>Assistant</strong>: {m['text']}</div>", unsafe_allow_html=True)

# --------------------
# Layout: left (controls), right (chat)
# --------------------
col1, col2 = st.columns([2,3])

with col1:
    st.markdown("## 🔁 Ingest (non-blocking)")
    st.markdown("Click to pull the latest data from Shopify and index it into MongoDB. Runs in the background so you can keep using the UI.")
    # ingest button
    im_available = os.path.exists("packages/ingest/ingest_mongo.py")
    if not im_available:
        st.warning("Ingest script not found at packages/ingest/ingest_mongo.py — you can still upload PDFs manually.")
    else:
        if st.button("Ingest Shopify (background)"):
            try:
                run_ingest_background()
                st.success("Ingest started in background. Check Mongo after a few seconds.")
            except Exception:
                st.error("Failed to start ingest; see traceback below.")
                st.text(traceback.format_exc())

    st.markdown("---")
    st.markdown("### 📦 Mongo status & quick ops")
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        st.success("Connected to MongoDB (ping OK)")
        st.markdown(f"- DB: `{MONGO_DB}`")
        st.markdown(f"- Collection: `{CHUNKS_COLL}`")
        try:
            n = client[MONGO_DB][CHUNKS_COLL].count_documents({})
            st.markdown(f"- Chunks in collection: **{n}**")
        except Exception:
            st.markdown("- Chunks count: could not read (check collection name)")
    except Exception as e:
        st.error("Cannot connect to MongoDB. Check MONGODB_URI in .env and Atlas network access.")
        st.text(str(e))

    st.divider()
    if st.button("Show 5 recent chunks"):
        try:
            client = get_mongo_client()
            db = client[MONGO_DB]
            cursor = db[CHUNKS_COLL].find({}, {"text":1, "title":1}).sort("_id",-1).limit(5)
            for i, d in enumerate(cursor, start=1):
                st.markdown(f"**chunk {i} — {d.get('title','(no title)')}**")
                st.write(d.get("text","")[:800])
        except Exception:
            st.error("Failed to fetch recent chunks")
            st.text(traceback.format_exc())

    st.divider()
    st.markdown("### Upload & index a single PDF (optional)")
    uploaded = st.file_uploader("Upload a PDF to index (this uses ingest-style chunker)", type=["pdf"])
    if uploaded is not None:
        if st.button("Index uploaded PDF"):
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(uploaded)
                pages = [p.extract_text() or "" for p in reader.pages]
                text = "\n".join(pages)
                # chunk
                parts = []
                words = text.split()
                max_words = 280
                buf = []
                for w in words:
                    buf.append(w)
                    if len(buf) >= max_words:
                        parts.append(" ".join(buf)); buf=[]
                if buf: parts.append(" ".join(buf))
                client = get_mongo_client()
                db = client[MONGO_DB]
                doc_id = str(int(time.time()))
                docs = []
                for idx, p in enumerate(parts):
                    docs.append({"doc_id": doc_id, "chunk_id": idx, "text": p, "title": uploaded.name})
                if docs:
                    db[CHUNKS_COLL].insert_many(docs)
                    st.success(f"Indexed {len(docs)} chunks into Mongo.")
                else:
                    st.info("No textual content found to index.")
            except Exception:
                st.error("Failed to index uploaded PDF")
                st.text(traceback.format_exc())

with col2:
    st.markdown("## 💬 Chat with your indexed shop data")
    st.markdown("<div class='muted'>Ask a question about your shop, products, or policies. The assistant will search your indexed chunks and give grounded answers.</div>", unsafe_allow_html=True)
    st.markdown("---")

    # Chat display
    chat_container = st.container()
    with chat_container:
        render_chat_area()

    # Ask form (keeps input + button together)
    with st.form(key="ask_form", clear_on_submit=False):
        user_q = st.text_input("Your question", placeholder="e.g. Is the 'Urban Messenger' water-resistant?", key="query_input")
        submitted = st.form_submit_button("Ask")
    if submitted:
        if not user_q or not user_q.strip():
            st.warning("Type a question first")
        else:
            append_message("user", user_q)
            # show updated chat immediately
            chat_container.empty()
            with chat_container:
                render_chat_area()

            # placeholder for assistant typing
            typing_slot = chat_container.empty()
            typing_slot.markdown("<div class='chat-bot'><em>Assistant is searching and generating an answer…</em></div>", unsafe_allow_html=True)

            # Perform search + generation
            try:
                hits = []
                with st.spinner("Searching your indexed chunks..."):
                    try:
                        hits = search_atlas(user_q, k=6, index_name=os.getenv("ATLAS_SEARCH_INDEX","default"))
                    except Exception as e_search:
                        print("search error:", e_search)
                        hits = []
                # show results preview
                if not hits:
                    typing_slot.markdown("<div class='chat-bot'><em>No matching chunks found. Try ingesting data or rephrase your question.</em></div>", unsafe_allow_html=True)
                    append_message("assistant", "I couldn't find matching information in your indexed data. Try running ingestion or ask a different question.")
                else:
                    # display results in chat (brief)
                    results_texts = []
                    for i, h in enumerate(hits, start=1):
                        excerpt = (h.get("text","") or "")[:800].replace("\n", " ")
                        results_texts.append(f"Result {i} — score {h.get('score',0):.2f}\n{excerpt}\nSource: {h.get('title','')} — {h.get('url','')}")
                    # Build LLM prompt
                    prompt = "You are an assistant. Use the passages below (with sources) to answer the user's question concisely and cite sources.\n\n"
                    prompt += "\n\n---\n\n".join(results_texts)
                    prompt += f"\n\nQuestion: {user_q}\n\nAnswer:"
                    # call LLM and replace placeholder
                    try:
                        with st.spinner("Generating answer from LLM (this may take a moment)..."):
                            answer = call_llm(prompt)
                    except Exception as e_llm:
                        print("LLM error:", e_llm)
                        answer = "Sorry — I couldn't generate an answer right now (LLM error). I can still show the top matched excerpts:\n\n" + "\n\n".join(results_texts[:3])
                    # append assistant message
                    typing_slot.empty()
                    append_message("assistant", answer)
                # refresh chat area
                chat_container.empty()
                with chat_container:
                    render_chat_area()
            except Exception:
                typing_slot.empty()
                st.error("Search/generation failed — see details below")
                st.text(traceback.format_exc())

    # small note / quick actions
    st.markdown("---")
    st.markdown("**Helpful tips:**")
    st.markdown("- Click **Ingest Shopify** to refresh your indexed data (runs in background).")
    st.markdown("- Use **Show 5 recent chunks** to verify ingestion wrote data into Mongo.")
    st.markdown("- If LLM is slow, you'll see a spinner; the assistant will appear when the response is ready.")

st.caption("Streamlit UI — runs ingest_mongo in background if present. Start with Ingest Shopify then ask questions.")
