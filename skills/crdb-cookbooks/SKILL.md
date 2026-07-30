---
name: crdb-cookbooks
description: Use this skill when the user wants to build AI applications with CockroachDB (CRDB) — including vector search with the VECTOR type and vector indexes, natural-language-to-SQL chatbots, RAG pipelines, and AI agents backed by CockroachDB. It contains a high-level index of architectural patterns, 'one-shot' blueprints, and best practices for common use cases. Currently, it includes references for building a SQL Agent Chatbot, Data Explorer, Multimodal PDF RAG (Document Search), Basic RAG, Advanced RAG, Basic Agent, Agentic RAG, and optional guidance on how to build a frontend for each of them.
license: MIT
compatibility: Requires Python 3.12+, uv, and network access to a CockroachDB cluster (v25.2+ for vector cookbooks)
metadata:
  author: cockroach-labs
  version: "0.1.0"
---

# CockroachDB Cookbooks

## Overview

This skill provides an index of implementation guides and foundational requirements for building CockroachDB-powered AI applications. Use the references to quickly scaffold full-stack applications with best practices for connection management, environment setup, transaction retry handling, and application architecture.

### CockroachDB Cloud Cluster

If the user does not have a cluster yet, direct them to the cloud console to register and create a free cluster. Create a CockroachDB cluster via [CockroachDB Cloud](https://cockroachlabs.cloud).

## Before Building Any Cookbook

Follow these shared guidelines before generating any cookbook app:

- [Project Setup Contract](references/project_setup.md)
- [Environment Requirements](references/environment_requirements.md)

### Embeddings: Ask the User First

CockroachDB has no built-in vectorizer — embeddings are always generated client-side. Before building any vector-search cookbook (Basic RAG, Advanced RAG, Multimodal PDF RAG, Agentic RAG), ask the user where the embeddings for their data come from:

1. **Data is already embedded** (existing `VECTOR` column, pgvector migration, precomputed vectors in files): ask which model produced them and its dimension. Load them as-is — do not re-embed. The `VECTOR(n)` column and all query-time embeddings must use that same model and dimension.
2. **Data is not embedded yet**: ask which embedding provider and model to use (e.g. OpenAI `text-embedding-3-small`, Voyage `voyage-3`, Cohere `embed-v4`). This choice fixes the `VECTOR(n)` dimension, the required API key, and the query path.

Never mix models between ingestion and query — mismatches surface as `expected N dimensions` errors or as silently poor retrieval.

Then proceed to the specific cookbook reference below.

## Cookbook Index

- [SQL Agent Chatbot](references/sql_agent_chatbot.md): Build a full-stack natural-language-to-SQL chatbot using Claude with streaming and CockroachDB-persisted chat history.
- [Data Explorer](references/data_explorer.md): Build a full-stack data explorer app including sorting, keyword search and tabular view of CockroachDB tables.
- [Multimodal RAG: Building Document Search](references/pdf_multimodal_rag.md): Build a multimodal Retrieval-Augmented Generation (RAG) system storing page-image embeddings in CockroachDB `VECTOR` columns, with Ollama and Qwen3-VL for generation.
- [Basic RAG](references/basic_rag.md): Implement basic retrieval and generation with CockroachDB as the vector store. Useful for most forms of semantic data retrieval from CockroachDB tables.
- [Advanced RAG](references/advanced_rag.md): Improve on basic RAG by adding extra features such as re-ranking, query decomposition, query re-writing, LLM filter selection combined with vector search in a single SQL query.
- [Basic Agent](references/basic_agent.md): Build a tool-calling AI agent with structured outputs using DSPy. Covers AgentResponse signatures, RouterAgent, SQL tool design, and sequential multi-step loops.
- [Agentic RAG](references/agentic_rag.md): Build RAG-powered AI agents with CockroachDB. Covers naive RAG tools, hierarchical RAG with LLM-created SQL filters, and vector memory implemented as a CockroachDB table with a `VECTOR` column.

## Interface (Optional)

Use this when the user explicitly asks for a frontend for their CockroachDB backend.

- [Frontend Interface](references/frontend_interface.md): Build a Next.js frontend to interact with the CockroachDB backend.

## Client Usage

- [Async Client](references/async_client.md): Guide for using async CockroachDB drivers in production applications (FastAPI, async frameworks). Covers asyncpg, psycopg async, SQLAlchemy async engine, pool lifecycle management, retry handling for `40001` errors, common pitfalls, and multi-cluster setups.
