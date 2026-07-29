# Build Data Explorer App

## Overview

Build a full-stack Data Explorer App for CockroachDB tables with FastAPI.

Read first:
- SELECT clause: https://www.cockroachlabs.com/docs/stable/select-clause
- Full-text search: https://www.cockroachlabs.com/docs/stable/full-text-search
- Trigram indexes: https://www.cockroachlabs.com/docs/stable/trigram-indexes

## Instructions

### Core Rules

- Use a virtual environment via `venv`
- Use `uv` for Python project/dependency management.
- Do not manually author `pyproject.toml` or `uv.lock`; let `uv` generate/update them.
- Use this backend install set:
  - `uv add fastapi 'uvicorn[standard]' 'psycopg[binary,pool]' pydantic-settings python-dotenv`
- Depending on user request: consider combining this app with the [SQL Agent Chatbot](./sql_agent_chatbot.md).
  - If the user explicitly only wants a data viewer/explorer, create this app independently
  - If the user wants a fully featured chat and data explorer, combine the apps
  - If no explicit instructions are given, ask the user their preference before continuing
  - See the [Next Steps](#next-steps) section for more details

### Fast Setup Commands

Project bootstrap:

```bash
uv init data_explorer
cd data_explorer
uv venv
uv add fastapi 'uvicorn[standard]' 'psycopg[binary,pool]' pydantic-settings python-dotenv
```

### Workflow Contract

1. Build backend and frontend in one pass.
2. Create `.env` from the canonical template in `environment_requirements.md`, then add app-specific fields (for example, `CORS_ORIGINS`).
3. Before asking user to fill env, do non-secret local sanity checks that do not require real credentials (imports/compile/startup-shape checks).
4. Ask user to fill real env values:
   - Mandatory: `DATABASE_URL`
   - Optional: none for this app
5. After the user confirms, verify backend starts without errors and provide exact commands to run in the terminal.

Do not ask avoidable questions that you can resolve from context.

### Directory Structure

Use a modular layout like:

```text
data_explorer/
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
- services: business/query logic
- models: request/response schemas
- config/lifespan: wiring and startup/shutdown

### Backend Requirements

- FastAPI async app with lifespan.
- Async connection pool (`psycopg_pool.AsyncConnectionPool`) opened in lifespan and closed on shutdown. See [Async Client](async_client.md).
- Ensure no async blocking operations.
- Not a full CRUD implementation - this is only for viewing data in CockroachDB tables.
- Endpoints for:
  - `GET /health`
  - `GET /env_check`: returns what env values are missing (if any) for verification on app start
  - `GET /tables`: return available tables (from `information_schema`)
  - `GET /data/{table_name}?xx=xx&yy=yy`: return data with optional arguments (more later), and pagination
- Pydantic settings should read from process environment; local `.env` loading is optional for local development.

### Env Rules

Mandatory:
- `DATABASE_URL`

CORS:

- Default `CORS_ORIGINS` should include:
  - `http://localhost:3000`
  - `http://127.0.0.1:3000`
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`

### FastAPI standards

1. Do not use hardcoded status values, use `status` from FastAPI, for example:

```python
from fastapi import status
status.HTTP_200_OK # code 200
status.HTTP_404_NOT_FOUND # code 404
# and more
```

2. Use a Pydantic `BaseModel` for the `request` and `response_model` in all endpoints that require it. Ensure schema validation to mitigate user-error on the API.

3. Use path parameters and query parameters for GET endpoints instead of payloads, for example:

```python
@app.get("/items/{item_id}")
async def read_item(item_id: str):
    return {"item_id": item_id}
```

```python
@app.get("/items/")
async def read_item(skip: int = 0, limit: int = 10):
    return fake_items_db[skip : skip + limit]
```

4. Implement best practices for error-handling, do early returns and provide the correct status codes when necessary.

5. Use proper logging for API usage, not simple print statements.

### SQL Identifier Safety (Required)

Table and column names cannot be sent as query parameters. Never interpolate user-provided identifiers directly:

- Validate `table_name` against the list introspected from `information_schema.tables`.
- Validate `sort_on` against the columns introspected for that table.
- After validation, quote identifiers with `psycopg.sql.Identifier` (or double quotes) when building statements.
- All *values* (search terms, limits, offsets) must be bound parameters (`%s`), never string-formatted.

### FastAPI endpoints

Basic structure of endpoints. Customise according to user preference or suitability. Do not follow exactly, this is a guideline only.

Ensure you also set up standard FastAPI procedures, such as global error handling, logging, dependencies. Set up an async pool manager that connects on startup (via lifespan) and closes gracefully on app exit, use a dependency injection to add the pool to the relevant endpoints.

#### GET /health

This is a standard health check. For example:

```python
from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: str

@app.get("/health", tags=["health"], response_model=HealthResponse)
async def health_check() -> HealthResponse:
    logger.info("Health check requested")
    return HealthResponse(status="healthy")
```

#### GET /env_check

Check what environment variables the backend has access to, used to verify the user's CockroachDB configuration is correct. For example:

```python
import os
from pydantic import BaseModel

class EnvCheckResponse(BaseModel):
    database_url: bool

@app.get("/env_check", tags=["health"])
async def env_check() -> EnvCheckResponse:
    logger.info("Environment check requested")
    return EnvCheckResponse(
        database_url = os.getenv("DATABASE_URL") is not None,
    )
```

### GET /tables

Check what tables are available. For example:

```python
from pydantic import BaseModel

class TablesResponse(BaseModel):
    tables: list[str]

@app.get("/tables", tags=["tables"])
async def tables() -> TablesResponse:

    # include pool management to import async pool here

    logger.info("Tables requested")
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )).fetchall()
    return TablesResponse(tables=[r[0] for r in rows])
```

Tip: consider expanding this endpoint to include column metadata. `information_schema.columns` gives you name, data type, and nullability per table:

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = %s
ORDER BY ordinal_position;
```

You can also surface `SHOW CREATE TABLE <table>` for a full schema view, and estimated row counts from `SHOW TABLES` for the table list UI.

#### GET /data/{table_name}

Retrieve data from a table, using pagination, sorting and keyword search.

```python
from fastapi import HTTPException, Query, status
from psycopg import sql
from pydantic import BaseModel
from typing import Any

async def get_table_columns(pool, table_name: str) -> dict[str, str]:
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )).fetchall()
    return {name: dtype for name, dtype in rows}

class GetDataResponse(BaseModel):
    data_types: dict[str, str]
    items: list[dict[str, Any]]

@router.get("/data/{table_name}")
async def get_data(
    table_name: str,
    page_size: int = Query(default=10, ge=1, le=100),
    page_number: int = Query(default=1, ge=1),
    query: str = Query(default=""),
    sort_on: str | None = Query(default=None),
    ascending: bool = Query(default=True),
) -> GetDataResponse:

    # include pool management to import async pool here

    data_types = await get_table_columns(pool, table_name)
    if not data_types:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="table not found")
    if sort_on is not None and sort_on not in data_types:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unknown sort column")

    table = sql.Identifier(table_name)
    where = sql.SQL("")
    params: list[Any] = []

    if query != "":
        # Keyword search: ILIKE across string columns (see search options below)
        text_cols = [c for c, t in data_types.items() if t in ("text", "character varying")]
        if text_cols:
            where = sql.SQL("WHERE ") + sql.SQL(" OR ").join(
                sql.SQL("{} ILIKE {}").format(sql.Identifier(c), sql.Placeholder())
                for c in text_cols
            )
            params += [f"%{query}%"] * len(text_cols)

    order = sql.SQL("")
    if sort_on is not None:
        order = sql.SQL("ORDER BY {} {}").format(
            sql.Identifier(sort_on),
            sql.SQL("ASC" if ascending else "DESC"),
        )

    stmt = sql.SQL("SELECT * FROM {} {} {} LIMIT {} OFFSET {}").format(
        table, where, order, sql.Placeholder(), sql.Placeholder()
    )
    params += [page_size, page_size * (page_number - 1)]

    async with pool.connection() as conn:
        cur = await conn.execute(stmt, params)
        col_names = [d.name for d in cur.description]
        rows = await cur.fetchall()

    return GetDataResponse(
        data_types=data_types,
        items=[dict(zip(col_names, row)) for row in rows],
    )
```

### Search and Pagination Options

CockroachDB has no BM25 endpoint like Weaviate; pick a keyword search strategy per table:

- **ILIKE** (default above): zero setup, but only fast with a [trigram index](https://www.cockroachlabs.com/docs/stable/trigram-indexes): `CREATE INDEX ON <table> USING GIN (<col> gin_trgm_ops);`
- **Full-text search** (v23.1+): stemming and ranking, closest to BM25-style relevance:

```sql
SELECT * FROM articles
WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
ORDER BY ts_rank(to_tsvector('english', content), plainto_tsquery('english', %s)) DESC
LIMIT %s;
```

  Accelerate with a computed `TSVECTOR` column and a GIN full-text index.

Pagination:

- **LIMIT/OFFSET** (shown above) is fine for a data explorer UI with bounded page depth.
- **Keyset pagination** scales better for deep pages: `WHERE (sort_col, id) > (%s, %s) ORDER BY sort_col, id LIMIT %s`, passing the last row of the previous page. Offer it if the user expects large tables.

### Post-Env Hand-Holding (Required)

After user says required env values are set, provide the terminal commands to run the backend:

```bash
cd data_explorer/backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then:

- Ask user to start terminal.
- Run smoke tests yourself against running services.
- Report pass/fail in plain language and fix blockers.

Do not offload detailed testing steps to the user unless they explicitly ask.

## Troubleshooting

- Connection/TLS errors on startup: ensure `DATABASE_URL` is the full `postgresql://...` string from CockroachDB Cloud including `sslmode=verify-full`.
- `relation ... does not exist`: check `table_schema` filter and that the SQL user has `SELECT` on the table.
- Slow ILIKE searches on large tables: add a trigram index or switch to full-text search.
- For any other issues, refer to the official library/package documentation using web search.

## Done Criteria

- Backend healthy.
- All endpoints work.
- User can run server in terminal with provided commands.

## Next Steps

This application is currently a data explorer backend. You may optionally offer to integrate it with the [SQL Agent Chatbot](./sql_agent_chatbot.md) based on user preference.

If the user chooses to combine these two applications, implement the integration as follows:

- Create or use a directory `/routes` which separate functions for SQL agent chat and data exploration. Import the routers in the `main.py` file
- If a frontend is requested, the frontend should have multiple pages/tabs depending on design choices so that data exploration and chat is separated
- Consider crossovers between functionalities, e.g. a chat button from the data viewer/table viewer which takes the user to chat with that table selected.
- Run quick tests to ensure the integration is seamless and the user can use both the chatbot and data explorer without any issues.

### Frontend

When the user explicitly asks for a frontend, use this reference as guideline:

- [Frontend Interface](frontend_interface.md): Build a Next.js frontend to interact with the CockroachDB backend.
