# Build CockroachDB SQL Agent Chatbot

## Overview

Build a full-stack natural-language-to-SQL agent chatbot with minimal back-and-forth.

Weaviate ships a hosted Query Agent for this; CockroachDB does not have an equivalent managed agent. The CRDB analog is an LLM-powered SQL agent: Claude reads the schema, generates SQL, the backend executes it read-only, and the LLM summarises results for the user.

Read first:
- CockroachDB SELECT clause: https://www.cockroachlabs.com/docs/stable/select-clause
- Anthropic streaming: https://platform.claude.com/docs/en/api/messages-streaming

## Instructions

### Core Rules

- Use `uv` for Python project/dependency management.
- Do not manually author `pyproject.toml` or `uv.lock`; let `uv` generate/update them.
- Use this backend install set:
  - `uv add fastapi 'uvicorn[standard]' 'psycopg[binary,pool]' anthropic pydantic-settings sse-starlette python-dotenv`
- If `uv` not available, create a `requirements.txt` for pip installation
- Depending on user request: consider combining this app with the Data Explorer.
  - If the user explicitly only wants chatbot, create this app independently
  - If the user wants a fully featured chat and data explorer, combine the apps
  - If no explicit instructions are given, ask the user their preference before continuing
  - See the [Next Steps](#next-steps) section for more details

### Fast Setup Commands

Project bootstrap:

```bash
uv init chatbot
cd chatbot
uv venv
uv add fastapi 'uvicorn[standard]' 'psycopg[binary,pool]' anthropic pydantic-settings sse-starlette python-dotenv
```

### Workflow Contract

1. Build backend in one pass.
2. Create `.env` from the canonical template in `environment_requirements.md`, then add app-specific fields (for example, `TABLES`).
3. Before asking user to fill env, do non-secret local sanity checks that do not require real credentials (imports/compile/startup-shape checks).
4. Ask user to fill real env values:
   - Mandatory: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `TABLES`
   - Optional: nothing else unless the user adds features
5. After the user confirms, verify backend starts without errors and provide exact commands to run it in terminal.

Do not ask avoidable questions that you can resolve from context.

### Directory Structure

Use a modular layout like:

```text
chatbot/
  backend/
    app/
      main.py
      config.py
      lifespan.py
      dependencies.py
      routers/
      services/
      models/
    .env  # local file, never committed
```

Keep these boundaries:

- routers: HTTP only
- services: business/SQL-agent logic
- models: request/response schemas
- config/lifespan: wiring and startup/shutdown

### Backend Requirements

- FastAPI async app with lifespan.
- Async CockroachDB connection pool (`psycopg_pool.AsyncConnectionPool`) opened in lifespan and closed on shutdown. See [Async Client](async_client.md).
- SQL agent service layer (`ask` + `ask_stream`) built on the Anthropic SDK with model `claude-sonnet-5`.
- Agent loop per request:
  1. Introspect the schema of the tables in `TABLES` from `information_schema.columns` (cache it; refresh on demand).
  2. Send the schema + conversation history + user question to Claude with a system prompt instructing it to output a single read-only `SELECT` statement (or a plain-text answer when no query is needed).
  3. Validate the SQL: single statement, starts with `SELECT`/`WITH`, no `;`-chained statements. Reject anything else.
  4. Execute inside a read-only transaction (`BEGIN; SET TRANSACTION AS OF SYSTEM TIME follower_read_timestamp();` or at minimum `SET TRANSACTION READ ONLY`) with a row cap (e.g. `LIMIT 100` enforced server-side) and a statement timeout.
  5. Send the rows back to Claude to produce the final natural-language answer.
- Endpoints:
  - `GET /health`
  - `POST /chat`
  - `POST /chat/stream` (SSE): stream `progress` events (schema loaded, SQL generated, query executed), then `token` events from Claude's streamed final answer, then one `final` event.
- Pydantic settings should read from process environment; local `.env` loading is optional for local development.
- Chat history persisted in CockroachDB tables (this replaces Weaviate's in-memory chat message format):

```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions (id),
    role STRING NOT NULL,       -- 'user' | 'assistant'
    content STRING NOT NULL,
    generated_sql STRING,       -- SQL the agent ran for this turn, if any
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX (session_id, created_at)
);
```

  Wrap inserts in the shared retry helper from `project_setup.md` (`40001` handling). On each request, load the session's prior messages and map them to Anthropic `messages` format.

### Source Handling

- For every ask response, normalize output into:
  - `answer`: final natural-language text from Claude (fallback `""`)
  - `sources`: list of `{ "table": ..., "sql": ..., "row_count": ... }` describing what was queried
  - `source_count`: `len(sources)`
- `POST /chat` must return `answer`, `sources`, and `source_count` (plus `session_id`).
- `POST /chat/stream` must include the same fields in the final SSE event.
- If no query was executed, return `sources: []` and `source_count: 0`.

### Env Rules

Mandatory:
- `DATABASE_URL`
- `ANTHROPIC_API_KEY`
- `TABLES` (comma-separated list of tables the agent may query)

CORS:

- Default `CORS_ORIGINS` should include:
  - `http://localhost:3000`
  - `http://127.0.0.1:3000`
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`

### Safety Rules (Required)

- The agent must only execute read-only statements; enforce this in code, not just in the prompt.
- Prefer a dedicated SQL user with `SELECT`-only grants on the target tables:

```sql
CREATE USER chatbot_reader WITH PASSWORD '...';
GRANT SELECT ON TABLE <table> TO chatbot_reader;
```

- Always include the generated SQL in the response so the user can audit it.

### Post-Env Hand-Holding (Required)

After user says required env values are set, provide the terminal commands to run the backend:

```bash
cd chatbot/backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then:

- Ask user to start the terminal.
- Run smoke tests yourself against running services.
- Report pass/fail in plain language and fix blockers.

Do not offload detailed testing steps to the user unless they explicitly ask.

## Troubleshooting

- `OPTIONS /chat/stream 400`: fix CORS origin mismatch (`localhost` vs `127.0.0.1`).
- Connection/TLS errors on startup: ensure `DATABASE_URL` is the full `postgresql://...` string from CockroachDB Cloud including `sslmode=verify-full`.
- `SerializationFailure` (`40001`) on history writes: ensure inserts go through the retry helper.
- Claude returns non-SQL or multiple statements: tighten the system prompt and keep the code-level validation as the source of truth.
- For any other issues, refer to the official library/package documentation using web search.

## Done Criteria

- Backend healthy.
- `/chat` works and history rows appear in `chat_messages`.
- `/chat/stream` streams progress/token/final.
- `/chat` and `/chat/stream` final include `sources` and `source_count` with the generated SQL.
- User can run the server in the terminal with the provided commands.

## Next Steps


This application is currently a chatbot backend. You may optionally offer to integrate it with the [Data Explorer](./data_explorer.md) based on user preference.

If the user chooses to combine these two applications, implement the integration as follows:

- Create or use a directory `/routes` which separate functions for SQL agent chat and data exploration. Import the routers in the `main.py` file
- If a frontend is requested, the frontend should have multiple pages/tabs depending on design choices so that data exploration and chat is separated
- Consider crossovers between functionalities, e.g. a chat button from the data viewer/table viewer which takes the user to chat with that table selected.
- Run quick tests to ensure the integration is seamless and the user can use both the chatbot and data explorer without any issues.

### Frontend

When the user explicitly asks for a frontend, use this reference as guideline:

- [Frontend Interface](frontend_interface.md): Build a Next.js frontend to interact with the CockroachDB backend.
- Render source citations from `sources` and `source_count` in the chat response UI, including the generated SQL in a collapsible code block.
