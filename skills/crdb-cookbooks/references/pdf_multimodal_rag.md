# Multimodal RAG: Building Multimodal Document Search Systems With CockroachDB

## Overview

This cookbook provides instructions for implementing a Multimodal Retrieval-Augmented Generation (RAG) system over PDF document collections using a hosted multimodal embedding API for embeddings, CockroachDB `VECTOR` columns for storage and search, and Ollama with a Vision Language Model (VLM) for generation.

**Key difference from Weaviate:** Weaviate Embeddings generates multi-vector (ColBERT-style/MaxSim) embeddings server-side. CockroachDB has no built-in vectorizer and no multi-vector/MaxSim search — your application calls a multimodal embedding API (e.g. Cohere Embed v4 or Voyage `voyage-multimodal-3`) to produce **one vector per page image**, stores it in a `VECTOR` column, and searches with a distance operator. Single-vector multimodal retrieval is slightly less precise than late-interaction models but works well for page-level document search.

**Ask the user first:** all vectorization is client-side, so before writing any code ask where the embeddings for the documents are. If page-image embeddings already exist (precomputed vectors, an export from another store), get the model name and dimension, load them as-is, and use the same model for query-time text embedding — text and image queries only work against embeddings from the same multimodal model. If nothing is embedded yet, ask which multimodal provider to use (Cohere Embed v4 or Voyage `voyage-multimodal-3`); that choice fixes the `VECTOR(n)` dimension and the API key.

### Architecture

A multimodal RAG system consists of two main pipelines:

**Ingestion Pipeline:**
- Documents (PDFs, images) are converted to page images
- Each page image is sent to the multimodal embedding API, producing one embedding per page
- Page metadata + image + embedding are inserted into a CockroachDB table with a `VECTOR` column and vector index

**Query Pipeline:**
- Text queries are embedded with the same multimodal model (text and images share one embedding space)
- Relevant pages are retrieved with a cosine-distance (`<=>`) vector search in SQL
- Retrieved page images are passed to a Vision Language Model (VLM) running on Ollama with the query
- The VLM generates a natural language response based on visual and textual context



**Requirements:**
- CockroachDB v25.2+ (vector indexes; v25.3+ recommended for the cosine index opclass). Create a free cluster at [CockroachDB Cloud](https://cockroachlabs.cloud).
- A multimodal embedding API key (`COHERE_API_KEY` or `VOYAGE_API_KEY`)
- Python 3.12 or higher
- `uv` package manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- [Ollama](https://ollama.com/) installed locally for VLM generation

## Workflow Instructions

### Step 1: Setup Project and Install Dependencies

#### Project Bootstrap

Initialize a new project with `uv`:

```bash
uv init multimodal-rag
cd multimodal-rag
uv venv
```

**Install uv if needed:**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with pip
pip install uv

# Or with Homebrew
brew install uv
```

#### Install Core Dependencies

Install required libraries using `uv`:

```bash
uv add 'psycopg[binary]' cohere python-dotenv
```

**Package breakdown:**
- `psycopg[binary]`: PostgreSQL-wire driver used to connect to CockroachDB
- `cohere`: client for the Cohere Embed v4 multimodal embedding API (swap for `voyageai` if using Voyage)

#### Additional Dependencies (Install as Needed)

```bash
# For loading Hugging Face datasets
uv add datasets

# For PDF processing (pdf2image requires poppler to be installed!)
uv add pdf2image pillow

# For VLM generation via Ollama
uv add ollama
```

### Step 2: Prepare Your Document Dataset

#### Option A: Load Existing Dataset
If using a pre-existing dataset:
- Use Hugging Face `datasets` library
- Ensure dataset contains document images or can be converted to images
- Verify image format compatibility (JPEG, PNG)

#### Option B: Process Your Own Documents
For custom document collections:
1. Convert documents to images (if not already images)
   - PDFs: Use `pdf2image` or similar libraries
   - Office documents: Convert to PDF first, then to images
2. Organize with metadata (document ID, page number, title, etc.)
3. Store in a format suitable for batch processing

**Recommended structure:**
```python
{
    "document_id": str,
    "page_number": int,
    "image": PIL.Image,
    "metadata": dict  # title, author, date, etc.
}
```

### Step 3: Configure CockroachDB Table

#### CockroachDB Connection

```python
import os
import psycopg

def get_conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])
```

#### Create Table Schema

Define a table with a `VECTOR` column sized to the embedding model (1536 for Cohere `embed-v4.0` default output; 1024 for Voyage `voyage-multimodal-3`) and a cosine vector index:

```sql
CREATE TABLE IF NOT EXISTS pdf_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id STRING NOT NULL,
    page_number INT NOT NULL,
    title STRING,
    page_image BYTES NOT NULL,      -- JPEG bytes of the page
    embedding VECTOR(1536) NOT NULL,
    VECTOR INDEX page_embed_idx (embedding vector_cosine_ops)
);
```

Run it once at setup:

```python
with get_conn() as conn:
    conn.execute(open("schema.sql").read())
```

**Key Configuration Options:**
- **`page_image`**: raw JPEG bytes so retrieval can hand the image straight to the VLM. Keep each value well under 1 MB (CockroachDB's recommended per-value ceiling) — render pages at ~120-150 DPI JPEG. For very large pages, store a file path or object-store URL instead.
- **`VECTOR(1536)`**: must exactly match the embedding model's output dimension.
- **`vector_cosine_ops`**: accelerates `<=>` cosine searches (v25.3+). On v25.2, use the default L2 opclass and the `<->` operator instead.
- **Columns**: add all metadata you want to filter or display. If you always filter by `document_id`, define it as a vector index prefix column: `VECTOR INDEX (document_id, embedding vector_cosine_ops)`.

If `CREATE VECTOR INDEX` fails with a feature-disabled error, an admin must run `SET CLUSTER SETTING feature.vector_index.enabled = true;`.

### Step 4: Index Documents

#### Embed Page Images

Cohere Embed v4 embeds images and text into the same space. Images are sent as base64 data URLs:

```python
import base64
from io import BytesIO

import cohere

co = cohere.ClientV2()  # reads COHERE_API_KEY
EMBED_MODEL = "embed-v4.0"

def image_to_jpeg_bytes(image) -> bytes:
    """Convert a PIL Image to JPEG bytes."""
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()

def embed_image(jpeg_bytes: bytes) -> list[float]:
    """Embed a page image. Verify call shape against current Cohere docs."""
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("utf-8")
    response = co.embed(
        model=EMBED_MODEL,
        input_type="image",
        embedding_types=["float"],
        images=[data_url],
    )
    return response.embeddings.float_[0]

def embed_query(text: str) -> list[float]:
    response = co.embed(
        model=EMBED_MODEL,
        input_type="search_query",
        embedding_types=["float"],
        texts=[text],
    )
    return response.embeddings.float_[0]
```

(Voyage alternative: `voyageai.Client().multimodal_embed(inputs=[[image]], model="voyage-multimodal-3")` with `VECTOR(1024)`.)

#### Import Loop

Insert one row per page. **Do not batch vector inserts**: CockroachDB documents that large batch inserts of `VECTOR` values into indexed tables degrade performance — row-at-a-time (or very small transactions) is the recommended pattern.

```python
with get_conn() as conn:
    for idx, document in enumerate(your_document_dataset):
        jpeg = image_to_jpeg_bytes(document["image"])
        vector = embed_image(jpeg)

        conn.execute(
            """
            INSERT INTO pdf_documents (document_id, page_number, title, page_image, embedding)
            VALUES (%s, %s, %s, %s, %s::vector)
            """,
            (
                document["document_id"],
                document["page_number"],
                document.get("title", ""),
                jpeg,
                str(vector),
            ),
        )
        conn.commit()

        # Progress tracking
        if idx % 25 == 0:
            print(f"Indexed {idx+1}/{len(your_document_dataset)} documents")

# Clean up dataset if memory is limited
del your_document_dataset

with get_conn() as conn:
    total = conn.execute("SELECT count(*) FROM pdf_documents").fetchone()[0]
print(f"Total pages indexed: {total}")
```

**Performance Tips:**
- **No batching for vectors**: insert rows individually into vector-indexed tables (see known limitations in the vector index docs). `IMPORT INTO` is also unsupported on tables with vector indexes — for bulk loads, load first and `CREATE VECTOR INDEX` afterwards.
- **Embedding API batching is fine**: you can embed many images per API call, then insert row-by-row.
- **Image format**: JPEG at moderate quality keeps rows small and VLM-friendly.
- **Large datasets**: process in chunks, delete intermediate variables to free memory.

### Step 5: Implement Retrieval

#### Basic Query Function

Embed the query text with the same model, then rank by cosine distance:

```python
def search_documents(query_text: str, limit: int = 3) -> list[dict]:
    """Search for document pages using multimodal embeddings in CockroachDB.

    Args:
        query_text: Natural language query string
        limit: Number of results to return (default: 3)

    Returns:
        List of dicts with page metadata, similarity distances, and JPEG bytes
    """
    query_vector = embed_query(query_text)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, document_id, page_number, title, page_image,
                   embedding <=> %s::vector AS distance
            FROM pdf_documents
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (str(query_vector), str(query_vector), limit),
        ).fetchall()

    results = []
    for i, (row_id, document_id, page_number, title, page_image, distance) in enumerate(rows):
        results.append({
            "rank": i + 1,
            "id": str(row_id),
            "document_id": document_id,
            "page_number": page_number,
            "title": title,
            "distance": distance,
            "image_bytes": bytes(page_image),
        })

    return results

# Example usage
query = "How does DeepSeek-V2 compare against the LLaMA family of LLMs?"
results = search_documents(query, limit=3)

for result in results:
    print(f"{result['rank']}) Distance: {result['distance']:.4f}, "
          f"Title: \"{result['title']}\", Page: {result['page_number']}")
```

**Query Parameters:**
- **`limit`**: Number of results (1-10 recommended, consider VLM memory limits)
- **Distance**: `<=>` returns cosine distance (lower = more similar); the operator must appear in `ORDER BY` for the vector index to be used
- **Accuracy tuning**: raise `SET vector_search_beam_size = 64;` (session setting, default 32) if recall is too low

#### Metadata Filtering

Add filters to narrow search scope by document properties — plain SQL `WHERE` clauses combine directly with vector search:

```python
# Example: Filter by document ID
rows = conn.execute(
    """
    SELECT id, page_number, title, page_image
    FROM pdf_documents
    WHERE document_id = %s
    ORDER BY embedding <=> %s::vector
    LIMIT %s
    """,
    ("paper_123", str(query_vector), 5),
).fetchall()

# Example: Filter by page range
# WHERE page_number < %s

# Example: Combine multiple filters
# WHERE document_id = %s AND page_number < %s
```

Note: only equality/`IN` filters on vector index **prefix columns** are index-accelerated; other filters are applied after the ANN scan. If `document_id` filtering is common, create the index as `VECTOR INDEX (document_id, embedding vector_cosine_ops)`.

#### Keyword Search (Optional)

CockroachDB has no BM25/hybrid fusion. If pages also have extracted text (e.g. from OCR), store it in a `STRING` column and combine full-text search (`to_tsvector(...) @@ plainto_tsquery(...)`) with vector results using reciprocal rank fusion in Python — see [advanced_rag.md](./advanced_rag.md).

### Step 6: Extend to Full RAG with a Vision Language Model

#### About Ollama

[Ollama](https://ollama.com/) makes it easy to run vision language models locally with a single command. No manual model downloads, GPU configuration, or dependency management required.

**Recommended VLM models for Ollama:**
- `qwen3-vl:4b`: ~4 GB, good for limited hardware
- `qwen3-vl:8b`: ~8 GB, better quality
- `qwen3-vl:32b`: ~32 GB, highest quality
- `gemma3`: Google's multimodal model, available in 4B/12B/27B sizes
- `llava`: LLaVA model, lightweight and fast

#### Install Ollama and Pull a Model

```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Or on macOS with Homebrew
brew install ollama

# Pull a vision language model
ollama pull qwen3-vl:4b
```

Verify the model is available:
```bash
ollama list
```

#### Implement Ollama VLM Wrapper

```python
import ollama

class OllamaVLM:
    def __init__(self, model_name="qwen3-vl:4b"):
        """Initialize with an Ollama vision model name.

        Args:
            model_name: Ollama model tag (must support vision)
        """
        self.model_name = model_name

    def generate_answer(self, query, images_bytes, max_tokens=128):
        """Generate text response based on query and retrieved document images.

        Args:
            query: String text query
            images_bytes: List of raw JPEG bytes (as returned from CockroachDB)
            max_tokens: Maximum tokens to generate (default: 128)

        Returns:
            Generated text answer as string
        """
        # The Ollama SDK "images" key accepts raw bytes or path-like strings.
        # CockroachDB BYTES columns come back as bytes, so pass them directly.
        response = ollama.chat(
            model=self.model_name,
            messages=[{
                "role": "user",
                "content": query,
                "images": images_bytes,
            }],
            options={"num_predict": max_tokens},
        )

        return response["message"]["content"]

# Instantiate the VLM
vlm = OllamaVLM(model_name="qwen3-vl:4b")
```

#### Complete RAG Pipeline

```python
def multimodal_rag(query, num_documents=3, max_tokens=128):
    """Complete multimodal RAG pipeline using CockroachDB vector search + Ollama VLM.

    Args:
        query: Natural language question
        num_documents: Number of pages to retrieve (1-3 recommended)
        max_tokens: Maximum tokens for VLM response

    Returns:
        Dict with query, answer, sources, and metadata
    """
    # Step 1: Retrieve relevant pages (query embedded client-side)
    print(f"Searching for: {query}")
    retrieved_docs = search_documents(query, limit=num_documents)

    # Display retrieved sources
    print(f"\nRetrieved {len(retrieved_docs)} documents:")
    for doc in retrieved_docs:
        print(f"  - {doc['title']}, Page {doc['page_number']} "
              f"(Distance: {doc['distance']:.4f})")

    # Step 2: Extract image bytes from results
    context_images = [doc["image_bytes"] for doc in retrieved_docs]

    # Step 3: Generate answer using Ollama VLM
    print(f"\nGenerating answer...")
    answer = vlm.generate_answer(query, context_images, max_tokens=max_tokens)

    # Step 4: Return structured response
    return {
        "query": query,
        "answer": answer,
        "sources": retrieved_docs,
        "num_sources": len(retrieved_docs)
    }

# Example usage
query = "How does DeepSeek-V2 compare against the LLaMA family of LLMs?"
result = multimodal_rag(query, num_documents=1, max_tokens=128)

print(f"\nQuery: {result['query']}")
print(f"Answer: {result['answer']}")
print(f"\nBased on {result['num_sources']} source(s)")
```

#### Response Citation

Include source attribution in generated answers:

```python
def generate_with_citations(query, retrieved_docs, max_tokens=256):
    """Generate answer with source citations.

    Args:
        query: User question
        retrieved_docs: List of documents from search_documents()
        max_tokens: Maximum response length

    Returns:
        Answer string with embedded citations
    """
    # Build source references
    sources_text = "\n".join([
        f"Source {i+1}: \"{doc['title']}\", Page {doc['page_number']}"
        for i, doc in enumerate(retrieved_docs)
    ])

    # Enhanced prompt with citation instructions
    enhanced_query = f"""{query}

Available sources:
{sources_text}

Instructions: Answer the question based on the provided document images.
Cite sources in your answer using [Source N] notation."""

    # Generate answer with citations
    answer = vlm.generate_answer(
        enhanced_query,
        [doc["image_bytes"] for doc in retrieved_docs],
        max_tokens=max_tokens
    )

    return answer, retrieved_docs

# Example usage
query = "What is the architecture of GPT-4?"
answer, sources = generate_with_citations(query, search_documents(query, limit=3))
print(f"Answer: {answer}\n")
print("Sources:")
for src in sources:
    print(f"  - {src['title']}, Page {src['page_number']}")
```

## Troubleshooting

### Missing Environment Variables
```
Error: DATABASE_URL environment variable is not set
```
**Solution:** Set `DATABASE_URL` and the embedding provider key (`COHERE_API_KEY` or `VOYAGE_API_KEY`). See `environment_requirements.md`.

### Connection Errors
```
psycopg.OperationalError: connection failed
```
**Solution:** Verify `DATABASE_URL` is the full connection string from CockroachDB Cloud (with `sslmode=verify-full`) and your network can reach the cluster.

### Vector Index Creation Fails
```
ERROR: vector indexes are not enabled
```
**Solution:** The cluster is on v25.2+ but the feature flag is off. An admin must run:
```sql
SET CLUSTER SETTING feature.vector_index.enabled = true;
```
On clusters older than v25.2, omit the vector index — searches fall back to exact scans.

### Dimension Mismatch
```
ERROR: expected 1536 dimensions, not 1024
```
**Solution:** The `VECTOR(n)` column does not match the embedding model output. Recreate the column with the correct dimension or switch models; all stored and query vectors must come from the same model.

### Ollama Connection Error
```
ConnectionError: Failed to connect to Ollama
```
**Solution:** Make sure Ollama is running. Start it with:
```bash
ollama serve
```

### Ollama Model Not Found
```
ollama._types.ResponseError: model 'qwen3-vl:4b' not found
```
**Solution:** Pull the model first:
```bash
ollama pull qwen3-vl:4b
```

### Out of Memory (OOM) During VLM Generation
**Symptoms:** Out of memory errors when generating answers.

**Solutions:**
- Reduce `num_documents` — retrieve fewer documents (even 1 can work well)
- Reduce `max_tokens` — shorter responses use less memory
- Use a smaller model variant (`qwen3-vl:4b` instead of `8b`)
- Use API-based VLMs (Claude, GPT-4V, Gemini) to avoid local resource requirements entirely

### Slow Ingestion
**Symptoms:** Inserts get slower as the table grows.

**Solutions:**
- Confirm you are inserting rows individually — large batch inserts of `VECTOR` values into indexed tables are a documented performance pitfall
- For a one-time bulk load, drop/skip the vector index, load all rows, then `CREATE VECTOR INDEX` afterwards (`IMPORT INTO` does not work on tables that already have a vector index)

### Poppler Not Installed (PDF Processing)
```
Exception: Unable to get page count. Is poppler installed and in PATH?
```
**Solution:** Install poppler for `pdf2image`:
```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt-get install poppler-utils
```

## Done Criteria

The implementation is complete when:
- [ ] Project is initialized with `uv` and all dependencies are installed
- [ ] Document page images are embedded via the multimodal API and inserted into a CockroachDB table with a `VECTOR` column
- [ ] The table has a vector index whose opclass matches the query operator (`vector_cosine_ops` + `<=>`)
- [ ] `search_documents()` returns ranked results with distances for text queries
- [ ] Ollama with a vision language model generates natural language answers from retrieved document images
- [ ] The full `multimodal_rag()` pipeline retrieves pages and generates answers end-to-end

## Next Steps

- **Add metadata filtering** to narrow search scope by document ID, page range, or other columns; promote hot filter columns to vector index prefix columns
- **Approximate hybrid search** by adding OCR text + full-text search and merging with reciprocal rank fusion for better precision
- **Add response citations** using `generate_with_citations()` to attribute answers to source documents
- **Scale the dataset** by processing larger document collections with chunked processing and post-load index creation
- **Swap in API-based VLMs** (Claude, GPT, Gemini) or other Ollama vision models (`gemma3`, `llava`) as alternatives
- **Evaluate retrieval quality** by testing queries against known-relevant documents and tuning `vector_search_beam_size` and partition sizes
