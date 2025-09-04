# Shopify RAG Assistant

A compact starter/demo that turns your Shopify store content into a Retrieval-Augmented Generation (RAG) assistant.
It fetches product & policy text, chunks and indexes it in MongoDB Atlas (Atlas Search recommended), then answers shopper questions using a configurable LLM via a friendly Streamlit UI.

## Key points (short)

1) Pulls product & policy content from Shopify.
2) Chunks and stores plain text snippets in MongoDB Atlas (no embeddings required if using Atlas Search).
3) Searches indexed chunks using Atlas Search (preferred) with a simple local fallback.
4) Generates grounded, cited answers via a pluggable LLM (Groq / OpenAI compatible).
5) Provides a Streamlit UI for ingesting, inspecting, and chatting with your indexed shop data.

## Features

1) Ingest Shopify products + policies into MongoDB (background option available).
2) Store chunked plain text in a collection (fields: text, title, source_url, …).
3) Search via Atlas Search $search pipeline (highly recommended) with a lightweight fallback if not available.
4) Chat UI with a friendly greeting, typed user messages, and assistant responses.
5) Upload & index single PDFs from the UI.
6) Pluggable LLM: call_llm() wrapper—swap provider and model in .env.
7) Non-blocking ingestion: run ingestion as a background process from Streamlit.
