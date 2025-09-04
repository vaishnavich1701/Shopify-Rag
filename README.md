# Shopify RAG Assistant is a compact demo / starter project that shows how to:

1) Pull product and policy content from a Shopify store,

2) Chunk and store those snippets in MongoDB Atlas,

3) Search indexed chunks using Atlas Search (preferred) or a local heuristic fallback,

4) Generate grounded, cited answers using an LLM provider (Groq in examples),

5) Provide a developer-friendly Streamlit UI to ingest, inspect, and chat with your shop data.

6) It’s designed for rapid prototyping of a product-help chatbot that can deflect support tickets and help shoppers get instant answers.

## Features

1) Ingest Shopify products + policies into MongoDB (ingest script).

2) Store plain text chunks in a MongoDB collection (no embeddings required — uses Atlas Search).

## Streamlit UI:

1) Background ingestion button (non-blocking).

2) Quick Mongo status / recent chunk viewer.

3) Upload & index single PDFs.

4) Chat UI with greeting, search, and LLM generation.

5) Pluggable LLM provider (Groq/OpenAI-compatible). Simple call_llm() wrapper included.

6) Simple fallback search if Atlas Search not available.


