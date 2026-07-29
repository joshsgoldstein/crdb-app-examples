# Project Setup Contract (All Cookbooks)

Use this reference before generating any cookbook app.

## Goal

Set up a safe default project layout that prevents accidental secret leaks and keeps setup instructions consistent across all cookbooks.

## Required Order

1. Create project directory.
2. Initialize git immediately.
3. Create `.gitignore` before any local `.env` file.
4. Create `.env` from [environment_requirements.md](environment_requirements.md).
5. Ask user to fill required values (`DATABASE_URL`) and only the optional keys they need.

## Required Files

### `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/

# Node
node_modules/
.next/
out/
dist/

# Local env files (never commit secrets)
.env
.env.*
secrets/

# TLS certs downloaded from CockroachDB Cloud
*.crt
.postgresql/

# Common local artifacts
.DS_Store
```

### `.env`

- Use the canonical template as provided in [environment_requirements.md](environment_requirements.md).
- Keep real `.env` values local only.

## Python Toolchain

- Python 3.12+.
- Use `uv` for Python project/dependency management.
- Do not manually author `pyproject.toml` or `uv.lock`; let `uv` generate/update them.
- Backend apps use FastAPI with the modular layout described in each cookbook (`routers/`, `services/`, `models/`, `config.py`, `lifespan.py`).

## CockroachDB Connection Contract

All cookbooks share the same connection conventions:

- Connect with the `DATABASE_URL` from CockroachDB Cloud. It looks like:

  ```text
  postgresql://<user>:<password>@<cluster-host>:26257/defaultdb?sslmode=verify-full
  ```

  Copy it from the cluster's **Connect** dialog at [CockroachDB Cloud](https://cockroachlabs.cloud). Depending on the cluster, it may also include `&sslrootcert=<path-to>/root.crt`.

- Driver choices (pick one per app and stay consistent):
  - **psycopg 3** (default for cookbooks): `uv add "psycopg[binary]"`, connect with `psycopg.connect(os.environ["DATABASE_URL"])`.
  - **SQLAlchemy**: `uv add sqlalchemy sqlalchemy-cockroachdb "psycopg[binary]"`. You must use the `cockroachdb://` URL prefix (e.g. `cockroachdb+psycopg://...`) so SQLAlchemy loads the CockroachDB dialect — a plain `postgresql://` prefix will not use the dialect.

### Transaction Retry Guidance (Required)

CockroachDB may abort a transaction under contention with `SQLSTATE 40001` (message begins with `restart transaction`). Every cookbook app that writes data must handle this client-side:

- With SQLAlchemy, wrap write transactions in `run_transaction` from `sqlalchemy_cockroachdb`, which retries `40001` automatically.
- With psycopg, use a retry loop that catches `psycopg.errors.SerializationFailure`, rolls back, sleeps with exponential backoff, and retries up to `max_retries`:

```python
import random
import time

import psycopg


def run_transaction(conn, op, max_retries: int = 3):
    """Execute op(conn) in a transaction, retrying on 40001 serialization errors."""
    for retry in range(1, max_retries + 1):
        try:
            with conn.transaction():
                result = op(conn)
            return result
        except psycopg.errors.SerializationFailure:
            if retry == max_retries:
                raise
            time.sleep((2**retry) * 0.1 * (random.random() + 0.5))
```

Read-only endpoints generally do not need retry loops, but long-lived apps should still treat `40001` as retryable.

## Git Baseline

Run these commands in every new cookbook app:

```bash
git init
git add .gitignore
git commit -m "initialize project baseline"
```

## Claude Safety Baseline (Recommended)

For projects developed with Claude Code, add deny rules for local secret files:

```json
{
  "permissions": {
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./**/.env)",
      "Read(./**/.env.*)",
      "Read(./secrets/**)"
    ]
  }
}
```

Save this to `.claude/settings.json` at project root.
