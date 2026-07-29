# Agentic RAG Cookbook

Build RAG-powered AI agents with CockroachDB.

Read first:
- Basic Agent cookbook, important to start from this base. MUST READ: [Basic Agent Cookbook](./basic_agent.md)

Docs to reference if needed:
- VECTOR data type: https://www.cockroachlabs.com/docs/stable/vector
- Vector indexes: https://www.cockroachlabs.com/docs/stable/vector-indexes
- Full-text search: https://www.cockroachlabs.com/docs/stable/full-text-search


## Core Rules

First implement the basic agent from [here](./basic_agent.md). Then modify according to this guide.

- Use a virtual environment via `venv`
- Use `uv` for Python project/dependency management.
- Do not manually author `pyproject.toml` or `uv.lock`; let `uv` generate/update them.
- Use this install set: `uv add 'psycopg[binary]' python-dotenv dspy openai`
- Customise this cookbook to the users specification, ask them for details if not given.

Assume the user has data already to be used, do not create data unless asked to.

Before building vector-backed tools or memory, resolve where the embeddings come from: follow the "Embeddings: Ask the User First" section in the [Basic RAG Cookbook](./basic_rag.md). If the user's data is already embedded, use that model and dimension for the RAG tools; agent memory written by this app can use any model, but keep one model per table.

**Substitutions from the Weaviate version:** Weaviate's agentic RAG guide offers the hosted Query Agent and the Elysia framework as prebuilt shortcuts. Neither has a CockroachDB equivalent — this guide implements the same capabilities directly: the [SQL Agent Chatbot](./sql_agent_chatbot.md) covers the "prebuilt agentic query service" role, and the patterns below cover RAG tools and memory.

## Env Rules

Mandatory:
- An LLM provider API key (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
- `DATABASE_URL`
- An embedding provider key (e.g. `OPENAI_API_KEY`) for vector tools and memory

External provider keys:
- Fill only keys actually used by the app's embedding/generation setup.


## Agentic RAG Overview

* Naive RAG tool: *Basic vector retrieval as a single tool for the RouterAgent*
* Hierarchical RAG: *LLM-created SQL filters and search parameters as a sub-agent tool*
* Vector memory: *Store and retrieve facts across sessions using a CockroachDB table with a `VECTOR` column*
* SQL agent: *Natural-language-to-SQL agent over full tables — see [SQL Agent Chatbot](./sql_agent_chatbot.md)*


## Naive RAG Tool

A simple retrieval tool that the RouterAgent can call. Pass this as a tool to the RouterAgent from the [basic agent cookbook](./basic_agent.md). Uses the shared `get_conn()` and `embed()` helpers from [basic_rag.md](./basic_rag.md).

```python
import os
import psycopg

def retrieve_data(query: str) -> str:
    """
    Given a query (free text), return the most relevant documents from the database using vector search.
    """
    query_vector = embed([query])[0]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(
            """
            SELECT content, source
            FROM documents
            ORDER BY embedding <=> %s::vector
            LIMIT 5
            """,
            (str(query_vector),),
        ).fetchall()
    return f"{[{'content': r[0], 'source': r[1]} for r in rows]}"
```

Customise the search type (vector `<=>`, full-text `@@`, or a merged hybrid — see [advanced_rag.md](./advanced_rag.md)), `LIMIT`, and returned columns based on the use case.


## Hierarchical RAG (LLM-created Filters)

Instead of simple retrieval, use an LLM sub-agent to construct SQL filters and search parameters. This makes the tool itself an agent. Because CockroachDB is SQL-native, the generated filters become a `WHERE` clause in the same statement as the vector search.

1. Structured response models for filters:

```python
from pydantic import BaseModel, Field
from typing import Literal, Any

class SearchFilter(BaseModel):
    field: str = Field(description="The column to be filtered on.")
    operator: Literal["=", "!=", ">", "<"] = Field(description="The operator to be used in conjunction with the value.")
    value: Any = Field(description="The value to be used in conjunction with the operator.")

class Search(BaseModel):
    query: str = Field(description="The search query to be embedded for vector search.")
    filters: list[SearchFilter] = Field(description="The filters to be used in the SQL WHERE clause.")
    limit: int = Field(description="The number of results to return.")

class SearchCreation(dspy.Signature):
    """
    Create a search query for a SQL database with vector search.
    """
    user_prompt: str = dspy.InputField()
    schema: list[dict] = dspy.InputField(desc="Schema of the table to be searched.")
    search: Search = dspy.OutputField(
        desc=(
            "Your search query and filters, this should be a valid JSON object. "
            "This should be constructed so that it matches the goal of the user prompt."
        )
    )
```

2. Helper function to convert structured filters to a parametrized SQL fragment (whitelist columns and operators, bind all values):

```python
_OPERATORS = {"=": "=", "!=": "!=", ">": ">", "<": "<"}

def format_filters(
    search_filters: list[SearchFilter], valid_columns: set[str]
) -> tuple[str, tuple]:
    clauses, params = [], []
    for search_filter in search_filters:
        if search_filter.field not in valid_columns:
            continue
        op = _OPERATORS.get(search_filter.operator)
        if op is None:
            continue
        clauses.append(f'"{search_filter.field}" {op} %s')
        params.append(search_filter.value)
    return " AND ".join(clauses), tuple(params)
```

3. The hierarchical query tool (replaces the naive retrieval tool):

```python
def query_agent_tool(table_name: str, user_prompt: str) -> str:
    """
    Given a query (free text), return the most relevant documents from the database using vector search with LLM-generated SQL filters.
    """
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        schema = [
            {"name": name, "type": dtype}
            for name, dtype in conn.execute(
                """
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                """,
                (table_name,),
            ).fetchall()
        ]
        if not schema:
            return f"Table {table_name} not found"

        query_model = dspy.ChainOfThought(SearchCreation)
        query_output = query_model(
            user_prompt=user_prompt,
            schema=schema,
            lm=dspy.LM("<subtask_model_name>")
        )

        where_sql, where_params = format_filters(
            query_output.search.filters, {c["name"] for c in schema}
        )
        where = f"WHERE {where_sql}" if where_sql else ""
        query_vector = embed([query_output.search.query])[0]

        rows = conn.execute(
            f"""
            SELECT content, source
            FROM "{table_name}"
            {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (*where_params, str(query_vector), min(query_output.search.limit, 20)),
        ).fetchall()
    return f"{[{'content': r[0], 'source': r[1]} for r in rows]}"
```

Note: `table_name` is an identifier and cannot be a bound parameter — validate it against `information_schema.tables` (the schema lookup above doubles as that check) before interpolating.

Schema information is required for the LLM to construct filters. Fetch dynamically via `information_schema` or provide manually if the schema is stable. Consider enriching the schema with sample data or enumerated values (`SELECT DISTINCT col LIMIT 20`) for better filter accuracy.


## Vector Memory (CockroachDB Table)

Store and retrieve facts across sessions using a CockroachDB table with a `VECTOR` column — the CRDB implementation of Weaviate's "vector database memory". Only add this if cross-session persistence is required.

Memory table (embedding dimension must match your embedding model):

```sql
CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_prompt STRING NOT NULL,
    memory STRING NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    VECTOR INDEX (embedding vector_cosine_ops)
);
```

Unlike Weaviate (where `text2vec_weaviate` embeds the memory server-side), the agent must embed each memory itself before inserting.

1. Memory creation signature:

```python
class MemoryCreation(dspy.Signature):
    user_prompt: str = dspy.InputField()
    assistant_response: str = dspy.InputField()
    memory: str = dspy.OutputField(
        description="A single string representing the most pertinent fact from the user/agent interaction."
    )
```

2. Add `memories` as an input to `AgentResponse`:

```python
class AgentResponse(dspy.Signature):

    # Input Fields
    history: dspy.History = dspy.InputField()
    user_prompt: str = dspy.InputField()
    available_tools: str = dspy.InputField()
    memories: list[str] = dspy.InputField(
        desc="A list of memories from previous conversations, you can use these to inform your response."
    )

    # Output Fields
    response: str = dspy.OutputField(
        description="The response to the user's prompt whilst the tool is running. Update the user on the progress of their request (if a tool is picked), or the final response to the user (if no tool is picked)."
    )
    tool: str | None = dspy.OutputField(
        description="The tool that needs to be used. Return None if no tool is needed."
    )
    tool_inputs: Dict[str, Any] | None = dspy.OutputField(
        description=(
            "The inputs for the tool. Return an empty dictionary (still include the field) if no inputs are needed. "
            "The key is the name of the input, the value is the value of the input."
        )
    )
```

3. Add `create_memory` and `retrieve_memories` methods to `RouterAgent`:

```python
import os
import psycopg

class RouterAgent:
    def __init__(self, model: str, memory_model: str | None = None, tools: List[Callable] = []):
        self.tools: list[Callable] = tools
        self.model = dspy.LM(model)
        self.memory_model = dspy.LM(memory_model) if memory_model else dspy.LM(model)
        self.agent = dspy.ChainOfThought(AgentResponse)
        self.memory_agent = dspy.Predict(MemoryCreation)
        self.conversation_history = dspy.History(messages=[])
        self.conn = psycopg.connect(os.environ["DATABASE_URL"])
        self._ensure_memory_table()

    def _ensure_memory_table(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_memory (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_prompt STRING NOT NULL,
                memory STRING NOT NULL,
                embedding VECTOR(1536) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                VECTOR INDEX (embedding vector_cosine_ops)
            )
            """
        )
        self.conn.commit()

    # ... existing methods from basic_agent.md (add_conversation_history, get_tools_and_descriptions) ...

    def create_memory(self, user_prompt: str, assistant_response: str, tool_result: str):
        if tool_result:
            assistant_response += "\n" + tool_result

        result = self.memory_agent(
            history=self.conversation_history,
            user_prompt=user_prompt,
            assistant_response=assistant_response,
            lm=self.memory_model,
        )
        vector = embed([result.memory])[0]
        self.conn.execute(
            "INSERT INTO agent_memory (user_prompt, memory, embedding) VALUES (%s, %s, %s::vector)",
            (user_prompt, result.memory, str(vector)),
        )
        self.conn.commit()
        return result.memory

    def retrieve_memories(self, user_prompt: str) -> list[str]:
        vector = embed([user_prompt])[0]
        rows = self.conn.execute(
            """
            SELECT memory FROM agent_memory
            ORDER BY embedding <=> %s::vector
            LIMIT 5
            """,
            (str(vector),),
        ).fetchall()
        return [r[0] for r in rows]
```

Call `retrieve_memories` at the start of each interaction and pass results to the `memories` field of `AgentResponse`. Call `create_memory` after each interaction.

Consider using a cheaper model for memory creation (e.g. `memory_model="<cheap_model_name>"`). Wrap the memory insert in the `40001` retry helper from `project_setup.md` if multiple agent instances share the table.


## SQL Agent (Replaces Weaviate Query Agent)

Weaviate offers a hosted Query Agent that handles collection selection, filter construction, and query optimisation automatically. There is no CockroachDB-hosted equivalent — build the same capability as a natural-language-to-SQL agent:

- Full blueprint: [SQL Agent Chatbot](./sql_agent_chatbot.md) (schema introspection, Claude-generated read-only SQL, streaming, persisted history).
- As a tool: wrap the agent loop in a function `sql_agent_tool(question: str) -> str` and pass it to the RouterAgent, so the top-level agent can delegate open-ended data questions to it.

There is also no CockroachDB analog of Elysia (Weaviate's open-source agentic framework). If the user wants a framework rather than hand-rolled loops, general frameworks (DSPy, LangGraph, the Anthropic SDK's tool-use loop) work with the CockroachDB tools defined in this guide — note the substitution to the user.


## Customisation Points

**When to use which approach:**

| Use Case | Recommended Approach |
|----------|---------------------|
| Single table, simple queries | Naive RAG tool |
| Need filters or operators | Hierarchical RAG or SQL agent tool |
| Open-ended analytical questions (aggregates, joins) | SQL Agent Chatbot pattern |
| Multi-step tasks, multiple data sources | Sequential agent with agentic loop |
| Cross-session personalisation | Add Vector Memory layer |

**Do not implement multi-agent architectures for simple retrieval tasks.**

**LLM framework**

This guide used DSPy. Follow the guidelines in [here](./basic_agent.md), but most likely you will need an LLM framework involving structured responses.


## Troubleshooting

- Connection/TLS errors: ensure `DATABASE_URL` is the full `postgresql://...` string from CockroachDB Cloud including `sslmode=verify-full`.
- DSPy signature warnings about missing fields: these can occur when using followup agents without all fields; ensure optional fields are handled.
- Vector index creation fails: cluster must be v25.2+ and may need `SET CLUSTER SETTING feature.vector_index.enabled = true;` (v25.3+ for `vector_cosine_ops`).
- LLM filter output references non-existent columns: the `format_filters` whitelist drops them silently — log dropped filters for debugging.
- For any other issues, refer to the official library/package documentation and use web search extensively for troubleshooting.

## Done Criteria

- Create test scripts to check each function works independently with test data. Tear down tests after completion, or create a proper test suite with pytest (requires install)
- User has completed specification of the app.
