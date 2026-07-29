# Basic RAG Cookbook

Build basic RAG functionality with CockroachDB as the vector store.
For advanced strategies, [see here](./advanced_rag.md).


Docs to reference if needed:
- VECTOR data type: https://www.cockroachlabs.com/docs/stable/vector
- Vector indexes: https://www.cockroachlabs.com/docs/stable/vector-indexes
- Full-text search: https://www.cockroachlabs.com/docs/stable/full-text-search
- Trigram indexes: https://www.cockroachlabs.com/docs/stable/trigram-indexes

## Core Rules

- Use a virtual environment via `venv`
- Use `uv` for Python project/dependency management.
- Do not manually author `pyproject.toml` or `uv.lock`; let `uv` generate/update them.
- Use this install set: `uv add 'psycopg[binary]' python-dotenv dspy openai`
- Customise this cookbook to the users specification, ask them for details if not given.

Assume the user has data already to be used, do not create data unless asked to.

**Key difference from Weaviate:** CockroachDB has no built-in vectorizer modules. Weaviate can embed text server-side (`near_text`); CockroachDB stores and searches vectors but your application must generate embeddings itself with an external provider (OpenAI, Voyage, Cohere, etc.) at both ingest time and query time — always with the same model.

## Embeddings: Ask the User First

Because all vectorization is client-side, ask the user where the embeddings for their data are before writing any code:

- **Data is already embedded** (existing `VECTOR` column, pgvector export, precomputed vectors in files): get the model name and dimension. Load the vectors as-is (`%s::vector`), size `VECTOR(n)` to match, and use that same model for query-time embedding. Do not re-embed. Skip the ingestion section below.
- **Data is not embedded yet**: agree on a provider and model (see the Embedding Provider question under Customisation), then follow the Chunking and Embedding section below.

Ingestion and query embeddings must come from the same model — a mismatch fails loudly (`expected N dimensions, not M`) if the dimensions differ, or silently degrades retrieval if they don't.

## Env Rules

Mandatory:
- `DATABASE_URL`
- An embedding provider key (e.g. `OPENAI_API_KEY` or `VOYAGE_API_KEY`)

External provider keys:
- Fill only keys actually used by the app's embedding/generation setup.


## CockroachDB Connection

```python
import os
import psycopg

def get_conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])
```

Connections must be closed after completion. Wrap in `with get_conn() as conn:` blocks (psycopg closes and commits/rolls back on exit), or use `try/finally` with `conn.close()`.

For writes, use the `run_transaction` retry helper from [project_setup.md](project_setup.md) to handle `40001` serialization errors.


## Table and Vector Index

If a documents table does not exist yet, create one with a `VECTOR` column sized to the embedding model (e.g. 1536 for OpenAI `text-embedding-3-small`):

```sql
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content STRING NOT NULL,
    source STRING,
    embedding VECTOR(1536)
);
```

Requires CockroachDB v24.2+ for the `VECTOR` type; v25.2+ for vector indexes. For text embeddings, cosine distance (`<=>`) is the usual choice, so create a cosine-opclass vector index (v25.3+):

```sql
CREATE VECTOR INDEX doc_embed_idx ON documents (embedding vector_cosine_ops);
```

On v25.2 only L2 (`<->`, default `vector_l2_ops` opclass) searches are index-accelerated. If index creation fails with a feature-disabled error, an admin must run:

```sql
SET CLUSTER SETTING feature.vector_index.enabled = true;
```

Without any vector index, the same queries still work via exact (brute-force) scan — fine for small tables.


## Chunking and Embedding (Ingestion)

Only needed if the user's data is not embedded yet. Keep chunks self-contained (e.g. 200-500 tokens, split on paragraphs).

```python
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-small"  # 1536 dims; must match VECTOR(1536)

def embed(texts: list[str]) -> list[list[float]]:
    client = OpenAI()  # reads OPENAI_API_KEY
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]

def ingest(chunks: list[dict]) -> None:
    vectors = embed([c["content"] for c in chunks])
    with get_conn() as conn:
        for chunk, vec in zip(chunks, vectors):
            conn.execute(
                "INSERT INTO documents (content, source, embedding) VALUES (%s, %s, %s::vector)",
                (chunk["content"], chunk.get("source"), str(vec)),
            )
```

Note: insert vectors row-by-row (or in small transactions). CockroachDB docs warn that large batch inserts of `VECTOR` values degrade performance on indexed tables. Pass vectors as their string form (`"[0.1, 0.2, ...]"`) with a `::vector` cast.


## Key Code Blocks

RAG should have 4 pieces of core functionality:

1. Pre-retrieval
2. Retrieval
3. Post-retrieval
4. Generation

These should all be separate functions and combined into a single function, leaving scope for later editing or for the user themselves to modify it, to keep it understandable.

## Pre-retrieval

Transform the user question into a vector-database style (list of) query(ies). Basic RAG will provide no extra query transformations.

```python
def query_transformation(query: str) -> list[str]:
    return [query]
```

## Retrieval

Vector similarity search: embed the query, then rank rows by distance with the operator in `ORDER BY`. `<=>` is cosine distance, `<->` is L2, `<#>` is negative inner product — match the operator to the index opclass.

```python
def retrieve(
    query: str,
    limit: int = 10,  # optional
    filters: str = "",  # optional SQL WHERE fragment, see advanced_rag.md
    filter_params: tuple = (),
) -> list[dict]:

    query_vector = embed([query])[0]

    where = f"WHERE {filters}" if filters else ""
    with get_conn() as conn:
        cur = conn.execute(
            f"""
            SELECT id, content, source, embedding <=> %s::vector AS distance
            FROM documents
            {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (*filter_params, str(query_vector), str(query_vector), limit),
        )
        rows = cur.fetchall()

    return [
        {"id": str(r[0]), "content": r[1], "source": r[2], "distance": r[3]}
        for r in rows
    ]
```

Keyword search alternative (no BM25 in CockroachDB; use full-text search or ILIKE):

```sql
SELECT id, content, source
FROM documents
WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
ORDER BY ts_rank(to_tsvector('english', content), plainto_tsquery('english', %s)) DESC
LIMIT %s;
```

There is no built-in hybrid (fused vector + keyword) search like Weaviate's `hybrid`. If the user wants hybrid behaviour, run both queries and merge with reciprocal rank fusion in Python (see [advanced_rag.md](./advanced_rag.md)).

## Post-Retrieval

Modify the output of `retrieve`. Basic RAG will provide no extra post-processing. But you can consider adding uniqueness checks, formatting to remove properties, or more.

```python
def process_retrieval_results(objects: list[dict]) -> list[dict]:
    return objects
```


## Generation

This step depends on your LLM framework, [see below](#user-specific-customisations). Using DSPy:

```python
import dspy
def generate(query: str, context: list[dict]) -> str:
    lm = dspy.LM("<model_name>") # e.g. claude-sonnet-5, gpt-5.2, gpt-5-mini, etc.
    answer = dspy.Predict("context, query -> answer") # inputs: context, query. outputs: answer
    pred = answer(context=context, query=query, lm=lm)
    return pred.answer # answer is then an attribute of pred
```

## User-specific Customisations

If not specified ask the user about these points before implementing their respective strategies:

**LLM Framework**

You can use DSPy (works with all LiteLLM providers) or LiteLLM itself.

- DSPy: https://dspy.ai/learn/programming/language_models/
- LiteLLM: https://docs.litellm.ai/docs/

Alternatively, users can use a single model provider. What model provider will they use?

- OpenAI (https://platform.openai.com/docs/libraries)
- Anthropic (https://platform.claude.com/docs/)
- Google GenAI (https://ai.google.dev/gemini-api/docs/libraries)
- Other (such as locally hosted models), use best judgement

These may require additional installs.

**Embedding Provider**

CockroachDB has no vectorizer, so an embedding provider is always required. Which one, and which model/dimension? Common choices:

- OpenAI `text-embedding-3-small` (1536 dims) or `text-embedding-3-large` (3072 dims)
- Voyage `voyage-3` family
- Cohere `embed-v4`

The `VECTOR(n)` column must match the model's dimension, and ingestion + query must use the same model.

**Tables**

Do tables already exist and what are they called? Do they already have `VECTOR` columns, and at what dimension? Does the user want to query multiple tables or just a single one? Does it need to be customisable?

What format is the data, images or text or something else? Image search requires a multimodal embedding model (see [pdf_multimodal_rag.md](./pdf_multimodal_rag.md)).

**Search strategy**

Does the user want semantic (vector), keyword (full-text/ILIKE), or a merged hybrid of both?

Which distance metric? Cosine (`<=>`) for most text embedding models; L2 (`<->`) or inner product (`<#>`) if the model documentation says so. The vector index opclass must match.


## Troubleshooting

- Connection/TLS errors: ensure `DATABASE_URL` is the full `postgresql://...` string from CockroachDB Cloud including `sslmode=verify-full`.
- `expected 1536 dimensions, not N`: the embedding model does not match the `VECTOR(n)` column definition.
- Vector index not used (slow queries): the distance operator in `ORDER BY` must match the index opclass, and any filtered columns must be index prefix columns (see [advanced_rag.md](./advanced_rag.md)).
- For any other issues, refer to the official library/package documentation and use web search extensively for troubleshooting.

## Done Criteria

- Create test scripts to check each function works independently with test data. Tear down tests after completion, or create a proper test suite with pytest (requires install)
- User has completed specification of the app.
