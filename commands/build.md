---
description: One-shot build — inspect the data in the current folder, gather the few required decisions up front, then build a complete CockroachDB-powered AI app end to end
argument-hint: [optional: which app — rag | advanced-rag | chatbot | data-explorer | pdf-rag | agent | agentic-rag]
---

# Build a CockroachDB AI App (One Shot)

Build a complete, working application from the data in the current folder using the `crdb-cookbooks` skill. The goal is **zero mid-build interruptions**: gather every decision up front, then execute end to end without stopping to ask further questions.

## Step 1: Inspect the data folder

Look at what is in the current working directory before asking anything:

- File types (CSV, JSON, JSONL, Parquet, PDFs, images, plain text, SQL dumps)
- Approximate size and row/document counts
- Whether any files already contain embeddings (columns/fields of float arrays — note the dimension)
- Whether a `.env` with `DATABASE_URL` already exists

Use this to pre-fill answers: only ask the user things the folder cannot tell you.

## Step 2: Gather ALL decisions up front (one round of questions)

Ask everything in a single interaction, then never ask again:

1. **Which app?** (skip if given as an argument or obvious from the data): Basic RAG, Advanced RAG, SQL Agent Chatbot, Data Explorer, Multimodal PDF RAG, Basic Agent, or Agentic RAG. Recommend one based on the data (PDFs → pdf_multimodal_rag; tabular → data_explorer or sql_agent_chatbot; text corpus → basic_rag).
2. **Cluster**: is there a `DATABASE_URL`? If not, direct the user to create a free cluster at https://cockroachlabs.cloud and paste the connection string now.
3. **Embeddings** (vector apps only, per the skill's "Embeddings: Ask the User First" section): already embedded (which model, what dimension) or which provider to use — and collect the API key env var now.
4. **LLM provider** and API key for generation/agents.
5. **Frontend**: API-only, or also the Next.js frontend?

## Step 3: Build without stopping

Load the `crdb-cookbooks` skill and follow the relevant cookbook exactly — project setup contract, environment requirements, then the chosen cookbook. Ingest the folder's data, create schema/indexes, implement the backend (and frontend if requested), and verify by running the app and executing at least one real end-to-end query against the user's data before declaring success.

Report at the end: what was built, how to run it, and one example request/response produced against the real data.
