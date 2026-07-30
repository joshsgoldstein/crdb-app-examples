# CRDB App Examples

A standalone Agent Skill for building AI applications on [CockroachDB](https://www.cockroachlabs.com) — one-shot cookbooks for RAG pipelines, vector search, natural-language-to-SQL chatbots, data explorers, and AI agents, with CockroachDB as both the operational database and the vector store. Point an agent like Claude Code, Cursor, or GitHub Copilot at this repo and build any of the example apps end to end.

Works with any agent that supports the [Agent Skills](https://agentskills.io) format.

## Why CockroachDB for AI apps?

Your vectors live next to your transactions. One distributed, survivable database gives you `VECTOR` columns and vector indexes **plus** joins, SQL filters, full-text search, and ACID guarantees — no separate vector store to sync, and metadata filtering combines with vector similarity in a single SQL query.

## Installation

### Using npx skills (Cursor, Claude Code, Gemini CLI, etc.)

```bash
npx skills add joshsgoldstein/crdb-app-examples
```

### Using Claude Code Plugin Manager

```bash
/plugin marketplace add joshsgoldstein/crdb-app-examples
/plugin install cockroachdb@crdb-app-examples
```

### Manual: clone and point your agent to the directory

```bash
git clone https://github.com/joshsgoldstein/crdb-app-examples.git
cd crdb-app-examples
claude --plugin-dir .
```

## Quickstart

Open your agent in a folder containing your data and run:

```bash
/cockroachdb:build
```

The command inspects your data, asks every required decision up front (cluster, embeddings, LLM provider, frontend), then builds a complete app end to end — no mid-build interruptions. Or just ask in natural language: *"Build a RAG app over the files in this folder using CockroachDB."*

## Configuration

### CockroachDB Cloud

Create a free cluster in the [CockroachDB Cloud console](https://cockroachlabs.cloud) and copy its connection string.

### Required Environment Variables

```bash
export DATABASE_URL="postgresql://user:pass@your-cluster.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full"
```

Vector cookbooks additionally need an embedding provider key (CockroachDB has no built-in vectorizer — embeddings are generated client-side). For the complete env var list, see [Environment Requirements](skills/crdb-cookbooks/references/environment_requirements.md).

## Available Skills

| Skill | Description |
| --- | --- |
| [crdb-cookbooks](skills/crdb-cookbooks/SKILL.md) | One-shot blueprints for full-stack CockroachDB AI applications |

### Cookbook Index

| Cookbook | What it builds |
| --- | --- |
| [SQL Agent Chatbot](skills/crdb-cookbooks/references/sql_agent_chatbot.md) | Natural-language-to-SQL chatbot with streaming and CockroachDB-persisted chat history |
| [Data Explorer](skills/crdb-cookbooks/references/data_explorer.md) | Sorting, keyword search, and tabular views over any CockroachDB tables |
| [Basic RAG](skills/crdb-cookbooks/references/basic_rag.md) | Retrieval and generation with `VECTOR` columns and vector indexes |
| [Advanced RAG](skills/crdb-cookbooks/references/advanced_rag.md) | Re-ranking, query rewriting, LLM filter selection, and single-query hybrid search (RRF) |
| [Multimodal PDF RAG](skills/crdb-cookbooks/references/pdf_multimodal_rag.md) | Document search over page-image embeddings with VLM generation |
| [Basic Agent](skills/crdb-cookbooks/references/basic_agent.md) | Tool-calling agent with structured outputs and CockroachDB-backed SQL tools |
| [Agentic RAG](skills/crdb-cookbooks/references/agentic_rag.md) | RAG-powered agents with LLM-created filters and vector memory in CockroachDB |
| [Frontend Interface](skills/crdb-cookbooks/references/frontend_interface.md) | Next.js frontend for any cookbook backend |
| [Async Client](skills/crdb-cookbooks/references/async_client.md) | Production async patterns: pools, lifespan, `40001` retries, multi-region |

## Available Commands

| Command | Description |
| --- | --- |
| `/cockroachdb:build` | Inspect a data folder, gather all decisions up front, then build one of the cookbook apps end to end |

## Requirements

- A CockroachDB cluster — [create a free one](https://cockroachlabs.cloud)
- CockroachDB v24.2+ for the `VECTOR` type; v25.2+ for vector indexes (v25.3+ for the cosine index opclass)
- Python 3.12+ and [uv](https://docs.astral.sh/uv/) for the generated applications

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to report issues, improve a cookbook, or propose a new skill.

## Resources

- [CockroachDB Docs](https://www.cockroachlabs.com/docs/)
- [Vector Search in CockroachDB](https://www.cockroachlabs.com/docs/stable/vector-indexes)
- [Agent Skills format](https://agentskills.io)
- [Claude Code Plugins](https://code.claude.com/docs/en/plugins)

## License

[MIT](LICENSE)
