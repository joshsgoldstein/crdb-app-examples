# Environment Requirements for CockroachDB

Use this reference when building apps that connect to CockroachDB and require external embedding/LLM provider keys.

## Required CockroachDB Auth

- `DATABASE_URL`

The `DATABASE_URL` is the full connection string from the CockroachDB Cloud **Connect** dialog, e.g.:

```text
postgresql://<user>:<password>@<cluster-host>:26257/defaultdb?sslmode=verify-full
```

If the user does not have a cluster yet, direct them to [CockroachDB Cloud](https://cockroachlabs.cloud) to create a free cluster.

## CockroachDB Version Requirements

Unlike Weaviate, CockroachDB has no built-in vectorizer modules — embeddings are always generated in your application via an external provider, then stored in `VECTOR` columns. Version requirements for the vector features used in these cookbooks:

| Feature | Minimum version | Notes |
|---------|-----------------|-------|
| `VECTOR` data type (pgvector-compatible) | v24.2 (preview) | Operators `<->`, `<=>`, `<#>` work without an index |
| Vector indexes (`CREATE VECTOR INDEX`, C-SPANN) | v25.2 | May require `SET CLUSTER SETTING feature.vector_index.enabled = true;` |
| Cosine/inner-product index opclasses (`vector_cosine_ops`, `vector_ip_ops`) | v25.3 | In v25.2, only L2 (`<->`) searches are index-accelerated |
| Full-text search (`TSVECTOR`, `to_tsvector`, `@@`) | v23.1 | Used by the Data Explorer cookbook |

Check the cluster version with `SELECT version();`. Cookbooks that create vector indexes require **v25.2+**; recommend **v25.3+** if the app uses cosine distance (typical for text embeddings).

## External Provider Env Vars

CockroachDB never receives these keys — your application calls the provider directly for embeddings, generation, or re-ranking.

| Provider | Environment Variable(s) | Used for |
|----------|--------------------------|----------|
| Anthropic | `ANTHROPIC_API_KEY` | Generation (chat, SQL agent), agents |
| OpenAI | `OPENAI_API_KEY` | Embeddings (`text-embedding-3-*`), generation |
| Voyage AI | `VOYAGE_API_KEY` | Embeddings (incl. multimodal), re-ranking |
| Cohere | `COHERE_API_KEY` | Embeddings (incl. multimodal), re-ranking |
| Google AI Studio | `GEMINI_API_KEY` | Embeddings, generation |
| Mistral | `MISTRAL_API_KEY` | Embeddings, generation |
| HuggingFace | `HUGGINGFACE_API_KEY` | Hosted inference embeddings/generation |
| Azure OpenAI | `AZURE_API_KEY` | Embeddings, generation |
| xAI | `XAI_API_KEY` | Generation |

## Usage Notes

- Set only the provider keys your app's embedding/generation configuration actually uses.
- The embedding provider and model must stay fixed per table: the `VECTOR(n)` column dimension must match the model's output dimension, and query vectors must come from the same model as stored vectors.

## Canonical `.env` Template

Use this template in all cookbook apps. Then ask the user to fill only the values their app actually needs.

`DATABASE_URL` is mandatory for CockroachDB-connected apps.

```dotenv
# Required for CockroachDB cookbook apps (must be filled by user)
DATABASE_URL=

# Common app-level settings (uncomment when needed by the selected cookbook)
# TABLES=
# CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173

# External provider keys (uncomment only what the app actually uses)
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# VOYAGE_API_KEY=
# COHERE_API_KEY=
# GEMINI_API_KEY=
# MISTRAL_API_KEY=
# HUGGINGFACE_API_KEY=
# AZURE_API_KEY=
# XAI_API_KEY=
```

## User Fill Guidance (Required)

1. Create a local `.env` file from this template.
2. Always ask the user to fill:
   - `DATABASE_URL`
3. Ask them to uncomment and fill only the provider keys their app's embedding/generation setup requires.
4. Keep `.env` local only and gitignored.
