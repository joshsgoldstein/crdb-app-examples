# Async Client Usage

Guide for using async CockroachDB drivers in production applications (FastAPI, async frameworks).

## 📚 Official Documentation Reference

**For agents:** If you encounter any issues not covered here, refer to the official documentation:

- **Primary Reference**: [Connect to CockroachDB](https://www.cockroachlabs.com/docs/stable/connect-to-the-database)
- **Connection Pooling**: [CockroachDB Connection Pooling Guide](https://www.cockroachlabs.com/docs/stable/connection-pooling)
- **Retry Reference**: [Transaction Retry Error Reference](https://www.cockroachlabs.com/docs/stable/transaction-retry-error-reference)
- **Drivers**: [psycopg docs](https://www.psycopg.org/psycopg3/docs/) | [asyncpg docs](https://magicstack.github.io/asyncpg/current/) | [sqlalchemy-cockroachdb](https://github.com/cockroachdb/sqlalchemy-cockroachdb)

> **Note**: CockroachDB speaks the PostgreSQL wire protocol, so any async PostgreSQL driver works. These cookbooks default to **psycopg 3 async** (`psycopg_pool.AsyncConnectionPool`); `asyncpg` and SQLAlchemy's async engine are equally valid.

## Connection Methods

Three options are provided — pick one per app and stay consistent:

### psycopg 3 Async Pool (Cookbook Default)

```bash
uv add 'psycopg[binary,pool]'
```

```python
import os
from psycopg_pool import AsyncConnectionPool

pool = AsyncConnectionPool(
    conninfo=os.environ["DATABASE_URL"],  # accepts the CockroachDB Cloud URL as-is
    min_size=1,
    max_size=10,
    open=False,  # open explicitly inside the running event loop
)

await pool.open()
async with pool.connection() as conn:
    rows = await (await conn.execute("SELECT 1")).fetchall()
await pool.close()
```

### asyncpg

```bash
uv add asyncpg
```

```python
import asyncpg

# ⚠️ asyncpg does not understand the "sslmode" query parameter from the
# CockroachDB Cloud URL — strip it and pass ssl explicitly.
dsn = os.environ["DATABASE_URL"].split("?")[0]

pool = await asyncpg.create_pool(dsn, ssl="require", min_size=1, max_size=10)
row = await pool.fetchrow("SELECT 1")
await pool.close()
```

### SQLAlchemy Async Engine

```bash
uv add sqlalchemy sqlalchemy-cockroachdb asyncpg
```

```python
from sqlalchemy.ext.asyncio import create_async_engine

# The cockroachdb+asyncpg:// prefix loads the CockroachDB dialect.
# A plain postgresql:// prefix will NOT use the dialect.
url = os.environ["DATABASE_URL"].replace("postgresql://", "cockroachdb+asyncpg://").split("?")[0]

engine = create_async_engine(url, pool_size=10, connect_args={"ssl": "require"})

async with engine.connect() as conn:
    result = await conn.execute(text("SELECT 1"))

await engine.dispose()
```

### Authentication

CockroachDB Cloud authenticates via the SQL user/password embedded in `DATABASE_URL`, plus TLS:

```text
postgresql://<user>:<password>@<cluster-host>:26257/defaultdb?sslmode=verify-full
```

- `sslmode=verify-full` is the CockroachDB Cloud default; keep it for psycopg/SQLAlchemy+psycopg.
- Some clusters also require `sslrootcert=<path>/root.crt` — download the CA cert from the Cloud console's **Connect** dialog.
- For self-hosted secure clusters, client certificates (`sslcert`/`sslkey`) are also supported.

## Critical Patterns

### ⚠️ Pool Lifecycle

Create and open the pool **inside the application's event loop** (FastAPI lifespan), and close it on shutdown. Do not open pools at module import time:

```python
# ❌ Wrong - pool opened at import time, may bind to the wrong event loop
pool = AsyncConnectionPool(conninfo=DATABASE_URL)  # opens implicitly

# ✅ Correct - construct closed, open in lifespan
pool = AsyncConnectionPool(conninfo=DATABASE_URL, open=False)
# later, inside the running loop:
await pool.open()
...
await pool.close()
```

`asyncpg.create_pool(...)` is a coroutine — it can only be called inside a running loop, which enforces this naturally.

### ⚠️ Retrying `40001` Serialization Errors

CockroachDB signals retryable transaction conflicts with `SQLSTATE 40001` (message begins with `restart transaction`). Async apps must retry these client-side with exponential backoff:

```python
import asyncio
import random

import psycopg


async def run_transaction(pool, op, max_retries: int = 3):
    """Execute op(conn) in a transaction, retrying on 40001 serialization errors."""
    for retry in range(1, max_retries + 1):
        try:
            async with pool.connection() as conn:
                async with conn.transaction():
                    return await op(conn)
        except psycopg.errors.SerializationFailure:
            if retry == max_retries:
                raise
            await asyncio.sleep((2**retry) * 0.1 * (random.random() + 0.5))
```

Rules (from the CockroachDB retry reference):

- Retry only on error code `40001`; re-raise everything else.
- The transaction context manager must roll back before the retry (psycopg's does this automatically).
- Cap retries (`max_retries`) and back off exponentially.
- With SQLAlchemy (sync), `run_transaction` from `sqlalchemy_cockroachdb` does this for you; for the async engine, implement a loop like the above around `async with session.begin()`.

### ⚠️ Bulk Operations

For large-scale data imports, do **not** loop inserts through the async pool:

- Non-vector bulk loads: use `COPY` (`cursor.copy()` in psycopg, `copy_records_to_table` in asyncpg) or `IMPORT INTO` from cloud storage.
- **Vector columns are the exception**: CockroachDB documents that large batch inserts of `VECTOR` values into indexed tables degrade performance — insert those row-by-row, and note `IMPORT INTO` is unsupported on tables that already have a vector index (load first, then `CREATE VECTOR INDEX`).

Use the async pool for:

- Web applications (FastAPI, Starlette)
- Concurrent request handling
- Interactive queries

Don't use the async pool for:

- One-off bulk data imports (use `COPY`/`IMPORT INTO` in a script instead)

## Context Manager Pattern (Recommended)

Use an async context manager to guarantee open/close:

```python
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from psycopg_pool import AsyncConnectionPool


@asynccontextmanager
async def get_crdb_pool(
    database_url: str | None = None,
    min_size: int = 1,
    max_size: int = 10,
) -> AsyncGenerator[AsyncConnectionPool, None]:
    """Open a CockroachDB connection pool with automatic cleanup."""
    pool = AsyncConnectionPool(
        conninfo=database_url or os.environ["DATABASE_URL"],
        min_size=min_size,
        max_size=max_size,
        open=False,
    )
    try:
        await pool.open(wait=True)  # fail fast if the cluster is unreachable
        yield pool
    finally:
        await pool.close()

# Usage
async def example():
    async with get_crdb_pool() as pool:
        async with pool.connection() as conn:
            rows = await (await conn.execute("SHOW TABLES")).fetchall()
```

> **Note**: `open(wait=True)` blocks until `min_size` connections are established, surfacing bad credentials/URLs at startup instead of on first request.

## FastAPI Integration

Use lifespan management for a shared pool across requests:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: open pool to CockroachDB
    app.state.pool = AsyncConnectionPool(
        conninfo=os.environ["DATABASE_URL"],
        min_size=1,
        max_size=10,
        open=False,
    )
    await app.state.pool.open(wait=True)

    yield

    # Shutdown: close pool
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/tables")
async def list_tables():
    async with app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )).fetchall()
    return {"tables": [r[0] for r in rows]}
```

**Reference**: [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)

## Common Pitfalls

### 1. asyncpg and `sslmode`

```python
# ❌ Wrong - asyncpg raises on the sslmode query parameter
pool = await asyncpg.create_pool(
    "postgresql://user:pass@host:26257/defaultdb?sslmode=verify-full"
)

# ✅ Correct - strip the query string, pass ssl explicitly
pool = await asyncpg.create_pool(
    "postgresql://user:pass@host:26257/defaultdb",
    ssl="require",  # or an ssl.SSLContext loaded with the cluster CA for full verification
)
```

psycopg accepts the CockroachDB Cloud URL unmodified — one reason it is the cookbook default.

### 2. Event-Loop Binding

```python
# ❌ Wrong - pool created/opened in one loop, used in another
# (common with pytest-asyncio, gunicorn preload, or global pools opened at import)

# ✅ Correct - open the pool inside lifespan / the running loop, one pool per process
```

With multiple uvicorn/gunicorn workers, each worker process gets its own pool via lifespan; never share a pool across processes.

### 3. SQLAlchemy Dialect Prefix

```python
# ❌ Wrong - CockroachDB dialect not loaded, retries and DDL quirks unhandled
engine = create_async_engine("postgresql+asyncpg://...")

# ✅ Correct - cockroachdb prefix loads the dialect from sqlalchemy-cockroachdb
engine = create_async_engine("cockroachdb+asyncpg://...")
```

**Naming pattern:**

- Sync: `cockroachdb+psycopg://` (or `cockroachdb://` for the default driver)
- Async: `cockroachdb+asyncpg://`

### 4. Pool Sizing

```python
# ❌ Wrong - giant pool "just in case"
pool = AsyncConnectionPool(conninfo=..., max_size=200)

# ✅ Correct - modest pool sized to workload
pool = AsyncConnectionPool(conninfo=..., max_size=10)
```

**Rule:** CockroachDB's guidance is roughly (cores × 4) total connections across the whole cluster, divided among your app processes. Oversized pools increase contention (and `40001` retries) without adding throughput. On CockroachDB Cloud Basic, also mind the cluster connection limits.

### 5. Holding Connections Across Awaits

Acquire a connection, run the query, release it. Do not hold a pooled connection open across long external awaits (LLM calls, HTTP requests) — embed first or generate first, then touch the database.

## Multi-Cluster Example

Managing pools to multiple CockroachDB clusters (e.g. regional clusters or prod/dev):

```python
@asynccontextmanager
async def get_multi_cluster_pools(
    clusters: dict[str, str]
) -> AsyncGenerator[dict[str, AsyncConnectionPool], None]:
    """Open pools to multiple CockroachDB clusters.

    Args:
        clusters: Dict of {cluster_id: database_url}
    """
    pools: dict[str, AsyncConnectionPool] = {}

    try:
        # Open pools to all clusters
        for cluster_id, url in clusters.items():
            pool = AsyncConnectionPool(conninfo=url, min_size=1, max_size=5, open=False)
            await pool.open(wait=True)
            pools[cluster_id] = pool

        yield pools

    finally:
        # Close all pools
        for pool in pools.values():
            await pool.close()

# Usage
async def example():
    clusters = {
        "prod": os.environ["DATABASE_URL_PROD"],
        "dev": os.environ["DATABASE_URL_DEV"],
    }

    async with get_multi_cluster_pools(clusters) as pools:
        async with pools["prod"].connection() as conn:
            prod_tables = await (await conn.execute("SHOW TABLES")).fetchall()
```

**Multi-region note:** a single CockroachDB cluster can span regions — usually you need only *one* pool pointed at the nearest regional endpoint, not one pool per region. For read-heavy, staleness-tolerant endpoints in multi-region clusters, consider follower reads (`AS OF SYSTEM TIME follower_read_timestamp()`) to serve from the local region.

## Environment Variables

See [Environment Requirements](environment_requirements.md) for provider API keys.

```python
import os

# Read from environment
database_url = os.environ["DATABASE_URL"]

# Provider keys are used by your app directly (never sent to CockroachDB)
openai_key = os.getenv("OPENAI_API_KEY")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")
```

## Testing Async Code

```python
import pytest

@pytest.mark.asyncio
async def test_crdb_connection():
    async with get_crdb_pool() as pool:
        async with pool.connection() as conn:
            row = await (await conn.execute("SELECT 1")).fetchone()
            assert row[0] == 1
```

## Quick Reference

| Task              | Pattern                                            | Await?  |
| ----------------- | -------------------------------------------------- | ------- |
| Create pool       | `AsyncConnectionPool(conninfo=..., open=False)`    | No      |
| Open pool         | `pool.open(wait=True)`                             | **Yes** |
| Acquire conn      | `async with pool.connection() as conn:`            | **Yes** |
| Run query         | `conn.execute(sql, params)`                        | **Yes** |
| Fetch rows        | `cur.fetchall()` / `cur.fetchone()`                | **Yes** |
| Transaction       | `async with conn.transaction():`                   | **Yes** |
| Retry 40001       | `run_transaction(pool, op)` helper above           | **Yes** |
| Close pool        | `pool.close()`                                     | **Yes** |

## Troubleshooting

### Common Issues

| Issue                                                  | Solution                                                              |
| ------------------------------------------------------ | --------------------------------------------------------------------- |
| `sslmode` errors with asyncpg                          | Strip query params from the URL; pass `ssl=` explicitly (Pitfall #1)  |
| Pool hangs or "attached to a different loop"           | Open the pool in lifespan, one pool per process (Pitfall #2)          |
| `SerializationFailure` / `40001` under load            | Add the retry loop with backoff; shrink transactions; reduce pool size |
| `certificate verify failed`                            | Download `root.crt` from the Cloud console; point `sslrootcert` at it  |
| Startup succeeds but first query fails                 | Use `pool.open(wait=True)` to validate credentials at startup          |
| SQLAlchemy ignores CockroachDB behaviours              | Use the `cockroachdb+asyncpg://` prefix, not `postgresql://` (Pitfall #3) |

### Getting Help

**For agents:** When encountering errors:

1. Check the [Common Pitfalls](#common-pitfalls) section above
2. Check the [Transaction Retry Error Reference](https://www.cockroachlabs.com/docs/stable/transaction-retry-error-reference) for `40001` specifics
3. Search the [CockroachDB Community Forum](https://forum.cockroachlabs.com/) and driver GitHub issues for similar reports
4. Refer to the [connection pooling docs](https://www.cockroachlabs.com/docs/stable/connection-pooling)

## Additional Resources

### Official Documentation

- **Primary**: [Connect to CockroachDB](https://www.cockroachlabs.com/docs/stable/connect-to-the-database)
- **Pooling**: [Connection Pooling](https://www.cockroachlabs.com/docs/stable/connection-pooling)
- **Retries**: [Transaction Retry Error Example](https://www.cockroachlabs.com/docs/stable/transaction-retry-error-example)
- **SQLAlchemy Adapter**: [sqlalchemy-cockroachdb](https://github.com/cockroachdb/sqlalchemy-cockroachdb)

### Framework Integration

- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [psycopg_pool AsyncConnectionPool](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
- [Python Async Context Managers](https://docs.python.org/3/reference/datamodel.html#asynchronous-context-managers)

### Community

- [CockroachDB Community Forum](https://forum.cockroachlabs.com/)
- [CockroachDB Blog](https://www.cockroachlabs.com/blog/)
