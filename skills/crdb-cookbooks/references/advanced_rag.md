# Advanced RAG Cookbook

Build advanced RAG functionality with CockroachDB.

Read first:
- Basic RAG cookbook, important to start from this base. MUST READ: [Basic RAG Cookbook](./basic_rag.md)

Docs to reference if needed:
- VECTOR data type: https://www.cockroachlabs.com/docs/stable/vector
- Vector indexes: https://www.cockroachlabs.com/docs/stable/vector-indexes
- Full-text search: https://www.cockroachlabs.com/docs/stable/full-text-search


## Core Rules

First implement the basic strategy from [here](./basic_rag.md). Then modify according to this guide.

- Use a virtual environment via `venv`
- Use `uv` for Python project/dependency management.
- Do not manually author `pyproject.toml` or `uv.lock`; let `uv` generate/update them.
- Use this install set: `uv add 'psycopg[binary]' python-dotenv dspy openai`
- Add `cohere` or `voyageai` if using an external reranker.
- Customise this cookbook to the users specification, ask them for details if not given.

Assume the user has data already to be used, do not create data unless asked to.

Before any vector work, resolve where the embeddings come from: follow the "Embeddings: Ask the User First" section in the [Basic RAG Cookbook](./basic_rag.md). Existing embeddings dictate the model and `VECTOR(n)` dimension; otherwise ask the user which provider/model to use.

**No Query Agent equivalent:** Weaviate's advanced RAG guide offers its hosted Query Agent as a shortcut. CockroachDB has no managed equivalent — implement the techniques in this guide directly, or build the [SQL Agent Chatbot](./sql_agent_chatbot.md) pattern if the user wants an end-to-end agent over their tables.

## Env Rules

Mandatory:
- `DATABASE_URL`
- An embedding provider key (e.g. `OPENAI_API_KEY`)

External provider keys:
- Fill only keys actually used by the app (add `COHERE_API_KEY` or `VOYAGE_API_KEY` for re-ranking).

## Advanced RAG overview

* Query re-writer: *Change user input text into a query text using an LLM*
* Query decomposition: *Change query into multiple sub-queries each re-written with an LLM*
* Filtering: *Use an LLM to define SQL WHERE clauses combined with vector search in one query*
* Re-ranking: *Score the final results by a more advanced model (external reranker API)*
* Prompt engineering: *Add chain of thought, Tree of thoughts, ReAct*

## Query Re-writer

```python
class QueryRewriter(dspy.Signature):
    """
    Rewrite the user's query into a more relevant search term that is a more relevant search term for searching a database.
    """
    input_query: str = dspy.InputField(description="The original user query")
    rewritten_query: str = dspy.OutputField(
        description=(
            "A single search term that is more relevant to the user's query. "
            "Include only relevant information, it does not need to be a full sentence or question "
        )
    )
```

Modify the `query_transformation` function:

```python
def query_transformation(query: str) -> list[str]:
    lm = dspy.LM(subtask_model_name)
    answer = dspy.Predict(QueryRewriter)
    pred = answer(input_query=query, lm=lm)
    return [pred.rewritten_query]
```

## Query Decomposition

```python
class QueryRewriter(dspy.Signature):
    """
    Rewrite the user's query into a more relevant search terms that are more relevant search term for searching a database.
    """
    input_query: str = dspy.InputField(description="The original user query")
    rewritten_queries: list[str] = dspy.OutputField(
        description=(
            "A list of search terms that are more relevant to the user's query. "
            "Each entry should include only relevant information, it does not need to be a full sentence or question "
            "Split independent searches into different entries "
            "Each entry should be relevant independently that capture a different required search aspect "
            "Do not repeat similar search terms, each one should have a unique meaning "
            "Be sparse, do not duplicate search terms "
        )
    )

def query_transformation(query: str) -> list[str]:
    lm = dspy.LM(subtask_model_name)
    answer = dspy.Predict(QueryRewriter)
    pred = answer(input_query=query, lm=lm)
    return pred.rewritten_queries
```

## LLM-created Filters

Filters can be specified by the user (for specific use-cases, perhaps), or you can get an LLM to write the filters also. Writing filters requires knowledge of the table schema, retrieved from `information_schema`.

This is where CockroachDB shines relative to dedicated vector stores: metadata filtering and vector similarity run in **one SQL query** — a plain `WHERE` clause plus a distance operator in `ORDER BY` — with full SQL expressiveness (joins, ranges, `IN` lists).

Simple version:

1. First create structured responses to format filters

```python
from pydantic import BaseModel, Field
from typing import Literal, Any

class SearchFilter(BaseModel):
    field: str = Field(description="The column to be filtered on.")
    operator: Literal["=", "!=", ">", "<"] = Field(description="The operator to be used in conjunction with the value. These are strict operators.")
    value: Any = Field(description="The value to be used in conjunction with the operator.")

class Search(BaseModel):
    filters: list[SearchFilter] = Field(description="The filters to be used in the SQL WHERE clause. This is an AND operation.")

class SearchCreation(dspy.Signature):
    """
    Create filters and search parameters for a search query in a database.
    """
    query: str = dspy.InputField()
    schema: list[dict] = dspy.InputField(desc="Schema of the table to be searched.")
    data_sample: list[dict] = dspy.InputField(desc="A sample of the data in the table to be searched.")
    search: Search = dspy.OutputField(
        desc=(
            "Your filters and search parameters, this should be a valid JSON object. "
            "This should be constructed so that it matches the goal of the user prompt."
        )
    )
```
This requires `schema` and `data_sample` as an input field to the LLM call `SearchCreation`.

2. Helper function to turn structured response into a parametrized SQL WHERE fragment. Never interpolate values; validate column names against the schema and keep values as bound parameters:

```python
_OPERATORS = {"=": "=", "!=": "!=", ">": ">", "<": "<"}

def _format_filters(
    search_filters: list[SearchFilter], valid_columns: set[str]
) -> tuple[str, tuple]:
    clauses, params = [], []
    for search_filter in search_filters:
        if search_filter.field not in valid_columns:
            continue  # LLM hallucinated a column; drop it
        op = _OPERATORS.get(search_filter.operator)
        if op is None:
            continue
        clauses.append(f'"{search_filter.field}" {op} %s')
        params.append(search_filter.value)
    return " AND ".join(clauses), tuple(params)
```

3. Combine

```python
def create_filters(query: str) -> tuple[str, tuple]:

    with get_conn() as conn:
        # Get table schema (for column names etc.). Can replace this with more
        # advanced configuration (like aggregating for unique groups)
        schema = [
            {"name": name, "type": dtype}
            for name, dtype in conn.execute(
                """
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                """,
                ("documents",),
            ).fetchall()
        ]

        # Get a sample of the data in the table to be searched
        cur = conn.execute("SELECT * FROM documents LIMIT 5")
        cols = [d.name for d in cur.description]
        data_sample = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Create search parameters
    search_parameters = dspy.ChainOfThought(SearchCreation)
    search_parameters_output = search_parameters(query=query, schema=schema, data_sample=data_sample, lm=dspy.LM(subtask_model_name))

    valid_columns = {c["name"] for c in schema}
    return _format_filters(search_parameters_output.search.filters, valid_columns)
```

Pass the `(filters, filter_params)` pair into the `retrieve` function from [basic_rag.md](./basic_rag.md); it appends `WHERE <filters>` before the vector `ORDER BY`.

Tip: if a filter column is highly selective and always constrained by equality, add it as a **prefix column** of the vector index (`CREATE VECTOR INDEX ON documents (category, embedding vector_cosine_ops)`) so the filtered vector search stays index-accelerated. Filters that do not match prefix columns fall back to post-filtering the ANN results.

## Re-ranking

CockroachDB has no built-in reranker modules (unlike Weaviate's collection-level reranker config). Instead, over-fetch from CockroachDB and re-rank with an external reranker API, for example Cohere:

```python
import cohere

def rerank(query: str, results: list[dict], top_n: int = 10) -> list[dict]:
    co = cohere.ClientV2()  # reads COHERE_API_KEY
    response = co.rerank(
        model="rerank-v3.5",
        query=query,
        documents=[r["content"] for r in results],
        top_n=top_n,
    )
    return [results[hit.index] for hit in response.results]
```

Modify the `retrieve` function to over-fetch, then re-rank:

```python
def retrieve(query: str, limit: int = 10, filters: str = "", filter_params: tuple = ()) -> list[dict]:

    # ...existing code, but fetch more candidates than needed:
    candidates = _vector_search(query, limit=limit * 3, filters=filters, filter_params=filter_params)

    return rerank(query, candidates, top_n=limit)
```

(this would require a Cohere API key; Voyage `rerank-2` is an equivalent alternative).

## Hybrid Search (Merged Vector + Keyword)

Weaviate fuses BM25 and vector scores server-side with a dedicated API; CockroachDB has no built-in fusion, but the same result is achieved in **one SQL statement** using CTEs and reciprocal rank fusion — one round trip, all work done in the database.

Prepare a full-text column and index once (see basic_rag.md for FTS options):

```sql
ALTER TABLE documents ADD COLUMN fts TSVECTOR
    AS (to_tsvector('english', content)) STORED;
CREATE INDEX doc_fts_idx ON documents USING GIN (fts);
```

Then rank each retrieval channel independently, fuse with RRF (`1 / (60 + rank)`), and return the top fused results:

```sql
WITH
fts_results AS (
    SELECT id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank(fts, query) DESC
           ) AS rank
    FROM documents, plainto_tsquery('english', %s) AS query
    WHERE fts @@ query
    LIMIT 50
),
vector_results AS (
    SELECT id,
           ROW_NUMBER() OVER (
               ORDER BY embedding <=> %s::vector
           ) AS rank
    FROM documents
    ORDER BY embedding <=> %s::vector
    LIMIT 50
),
rrf AS (
    SELECT COALESCE(f.id, v.id)                 AS id,
           COALESCE(1.0 / (60 + f.rank), 0.0)
         + COALESCE(1.0 / (60 + v.rank), 0.0)   AS rrf_score
    FROM fts_results f
    FULL OUTER JOIN vector_results v ON f.id = v.id
)
SELECT d.id, d.content, d.source,
       ROUND(r.rrf_score::numeric, 6) AS rrf_score
FROM rrf r JOIN documents d ON d.id = r.id
ORDER BY r.rrf_score DESC
LIMIT 10;
```

Notes:

- The query vector parameter is passed twice (window `ORDER BY` and outer `ORDER BY`); bind the same value to both placeholders. The outer `ORDER BY ... LIMIT` inside `vector_results` is what lets the vector index accelerate the scan.
- This extends to any number of retrieval channels: add another ranked CTE (e.g. an `image_embedding <=> %s::vector` channel for multimodal tables) and another `FULL OUTER JOIN` + `COALESCE(1.0 / (60 + x.rank), 0.0)` term in `rrf`.
- CockroachDB's `ts_rank` is not true BM25 (no document-length normalization), but under RRF only the rank order matters, so the fused results behave like Weaviate's hybrid search in practice.

## Prompt Engineering

This step depends on the LLM framework used. You can manually ask the LLM to include reasoning before giving its final answer, adding a reasoning sub-field to be completed before giving the final answer in structured response, or specify in DSPy to use chain-of-thought.

```python
class Generator(dspy.Signature):
    """
    Answer the question based on the context.
    Do not include any information from external sources, only use the information provided in the context.
    If you cannot answer the question based on the information provided, say "I don't know".
    """
    context: str | list[dict] =  dspy.InputField(desc="The context to answer the question.")
    query: str = dspy.InputField(desc="The question to answer.")
    answer: str = dspy.OutputField(desc="The single answer to the question with no additional communication")
```

Modify the `generate` function:

```python
def generate(query: str, context: list[dict]) -> str:
    lm = dspy.LM(generation_model_name)
    answer = dspy.Predict(Generator)
    pred = answer(context=context, query=query, lm=lm)
    return pred.answer
```

Consider other prompt engineering techniques like ReAct (if necessary but likely overkill), few-shot learning (requires advanced specification), or otherwise.

## Customisation Points

**LLM framework**

This guide used DSPy. Follow the guidelines in [here](./basic_rag.md), but most likely you will need an LLM framework involving structured responses.

**Reranker provider**

Cohere and Voyage both offer hosted rerank endpoints; ask which the user prefers (or skip re-ranking for latency-sensitive apps).

## Troubleshooting

- Connection/TLS errors: ensure `DATABASE_URL` is the full `postgresql://...` string from CockroachDB Cloud including `sslmode=verify-full`.
- Filtered vector queries slow: check whether filters match vector index prefix columns; otherwise increase `vector_search_beam_size` or restructure the index.
- LLM filter output references non-existent columns: the `_format_filters` whitelist drops them silently — log dropped filters for debugging.
- For any other issues, refer to the official library/package documentation and use web search extensively for troubleshooting.

## Done Criteria

- Create test scripts to check each function works independently with test data. Tear down tests after completion, or create a proper test suite with pytest (requires install)
- User has completed specification of the app.
