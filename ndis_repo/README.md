## NDIS RAG

NDIS RAG is a FastAPI-based retrieval system built on Postgres, pgvector, and Ollama.

The service ingests uploaded documents, parses them into records, splits record content into retrieval chunks, generates embeddings, and stores everything in Postgres. Retrieval combines two search strategies:

- semantic nearest-neighbor search on `chunks.embedding` using pgvector HNSW indexing
- lexical full-text search on `chunks.tsv`

The final ranking is produced with reciprocal rank fusion (RRF), which blends semantic and lexical candidates into a single result set.

### Core Flow

1. Documents are uploaded through the API.
2. Docling extracts text from supported files.
3. The content is classified into record types and split into retrieval chunks.
4. Ollama generates fixed-dimension embeddings for the chunks.
5. Documents, records, chunks, and events are stored in Postgres.
6. Queries are embedded, searched semantically and lexically, then fused into the final ranked results.

### Storage Model

- `documents`: uploaded source files and metadata
- `records`: typed structured units extracted from a document
- `chunks`: retrieval units with citations, full-text search vectors, and embeddings
- `events`: append-only ingestion and audit events

### Retrieval Stack

- Postgres `tsvector` + GIN index for lexical search
- pgvector `vector(EMBEDDING_DIM)` column for chunk embeddings
- HNSW index on `chunks.embedding` with cosine distance
- weighted RRF fusion for final ranking
- query embedding cache and Postgres connection pooling for lower latency

### Prereqs

- Docker + Docker Compose
- Ollama running locally with an embedding model available
- Python 3.13+

### Setup

1. Copy environment configuration:
   - `.env.example` -> `.env`
2. Create and activate a virtual environment:
   - `python3 -m venv .venv && source .venv/bin/activate`
3. Install dependencies:
   - `pip install -r requirements.txt`
4. Start Postgres:
   - `docker compose up -d`
5. Initialize the database schema and indexes:
   - `python -m app.scripts.init_db`
6. Start the API:
   - `python3 -m app.main`

### Frontend

Run the Streamlit frontend with:

- `streamlit run frontend/streamlit_app.py`

Set the backend base URL in the UI, then ingest files and run retrieval or grounded chat.

### Main Endpoints

- `POST /ingest/file`
  - Upload a document and store documents, records, chunks, embeddings, and metadata.
- `POST /retrieve`
  - Return hybrid retrieval results with scores, snippets, highlights, and citations.
- `POST /agent/answer`
  - Run grounded question answering over retrieved chunks.
- `GET /documents`
  - List ingested documents and counts.
- `DELETE /documents/{document_id}`
  - Remove a document and its dependent records/chunks.
- `GET /debug/stats`
  - Return document, record, and chunk counts.

### OpenAI-Compatible Chat API

The backend also exposes minimal OpenAI-compatible chat endpoints:

- `POST /v1/chat/completions`
- `GET /v1/models`

Model routing is controlled through `INFERENCE_MODEL_REGISTRY_JSON`.

### Embedding Configuration

Set these values in `.env` to match your Ollama embedding model:

- `OLLAMA_EMBED_MODEL`
- `EMBEDDING_DIM`
- `OLLAMA_EMBED_BATCH_SIZE`

For `nomic-embed-text`, `EMBEDDING_DIM=768` is the expected setting.

The service prefers Ollama's batch embedding endpoint at `/api/embed` and falls back to `/api/embeddings` when needed.

### LangSmith (Optional)

To enable LangSmith tracing, set these environment variables:

- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT` (optional; defaults to the LangSmith SDK environment default)

When `LANGSMITH_API_KEY` is present, the project automatically instruments retrieval and LLM calls.
