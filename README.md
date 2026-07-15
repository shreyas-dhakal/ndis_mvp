# Agents MVP

`agents/` is the merged MVP application.

It combines:

- NDIS progress note generation
- task and incident review workflow
- document ingestion
- retrieval and grounded chat
- one FastAPI backend
- one React frontend
- one PostgreSQL + pgvector database
- local Ollama models for all LLM and embedding work

## Local-Only Runtime

This project is now configured so the AI stack runs locally after the initial model download.

Local components:

- note generation: Ollama
- incident classification: Ollama
- retrieval chat: Ollama
- embeddings: Ollama
- audio transcription: `faster-whisper`
- database: local Docker Postgres with `pgvector`

After the first run:

- Ollama models stay cached locally
- Whisper models stay cached locally
- the app does not require Groq or Hugging Face tokens

## What The App Does

### 1. Note Generation

- create an NDIS progress note from transcript text or audio
- review and revise the note
- generate a PDF
- save the approved note into the shared database
- create follow-up incident tasks when triggers match

### 2. Document Ingestion And Grounded Chat

- upload PDF, DOCX, TXT, CSV, and other supported files
- extract text into records and chunks
- generate embeddings into the same database
- query uploaded evidence through the Chat UI

## Single Database Design

Everything uses one PostgreSQL database.

The shared schema stores:

- LangGraph checkpoints
- generated notes
- incident tasks
- uploaded documents
- extracted records
- retrieval chunks
- vector embeddings
- events and links

There is no second retrieval database.

## Stack

- Backend: FastAPI
- Frontend: React + Vite
- Database: PostgreSQL + pgvector
- LLM runtime: Ollama
- Transcription: faster-whisper
- Parsing: Docling

## Prerequisites

- Docker Desktop
- Python 3.12+
- Node.js 18+
- `uv`
- Ollama installed locally

## First-Time Setup

### 1. Start the database

From `agents/`:

```bash
docker compose up -d
```

Check status:

```bash
docker compose ps
```

### 2. Pull the local Ollama models

Recommended:

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

Notes:

- `qwen3:8b` is used for note generation, incident classification, and grounded chat by default.
- `nomic-embed-text` is used for embeddings.
- the first audio transcription run will download the selected `faster-whisper` model locally and cache it.

### 3. Configure `.env`

Copy the example file first:

```bash
cp .env.example .env
```

Default contents:

```bash
DATABASE_URL=postgresql://langgraph:langgraph123@localhost:5432/langgraph_db
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:8b
OLLAMA_AGENT_MODEL=qwen3:8b
OLLAMA_EMBED_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

Optional tuning:

```bash
OLLAMA_EMBED_BATCH_SIZE=32
OLLAMA_EMBED_CONCURRENCY=4
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=8
RETRIEVAL_SEMANTIC_CANDIDATES=60
RETRIEVAL_LEXICAL_CANDIDATES=60
RETRIEVAL_RRF_K=50
```

For audio note generation, the UI's Whisper size choices map to local `faster-whisper` downloads.
The first time you use `small`, `medium`, or `large-v3`, that model is downloaded and cached locally.

### 4. Install backend dependencies

```bash
uv sync
```

### 5. Start the backend

```bash
uv run uvicorn src.api.app:app --reload --port 8000
```

The schema is created automatically on startup.

### 6. Install frontend dependencies

In another terminal:

```bash
cd frontend
npm install
```

### 7. Start the frontend

```bash
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

Backend URL:

```text
http://localhost:8000
```

## After First Run

Once you have:

- pulled the Ollama models
- run Whisper transcription once for each model size you want cached

the app runs locally using cached models.

You do not need:

- Groq API access
- Hugging Face API access
- any hosted LLM endpoint

## Recommended Demo Flow

1. Start Docker Compose.
2. Make sure Ollama is running.
3. Start the backend.
4. Start the frontend.
5. Upload a few documents.
6. Ask questions in Chat.
7. Generate a note from transcript text.
8. Show the Tasks tab if a trigger is created.

## Main UI Areas

### Chat

- grounded answers over uploaded documents
- shows retrieved evidence below answers

### Note Generator

- transcript or audio input
- human review loop
- PDF output

### Tasks

- pending review tasks
- confirmed tasks
- approve, dismiss, and action actions

### Documents Sidebar

- upload files
- list stored documents
- remove documents

## Main API Endpoints

### Notes

- `POST /generate/text`
- `POST /generate/audio`
- `POST /generate/resume`
- `GET /download/pdf`

### Tasks

- `GET /tasks`
- `POST /tasks/{task_id}/approve`
- `POST /tasks/{task_id}/dismiss`
- `POST /tasks/{task_id}/action`

### Documents And Retrieval

- `GET /documents`
- `POST /documents`
- `DELETE /documents/{document_id}`
- `POST /ingest/file`
- `POST /retrieve`
- `POST /agent/answer`
- `POST /chat`

## Database Commands

Start DB:

```bash
docker compose up -d
```

Stop DB:

```bash
docker compose down
```

Delete DB data too:

```bash
docker compose down -v
```

Open Postgres shell:

```bash
docker exec -it agents-postgres psql -U langgraph -d langgraph_db
```

## Ollama Commands

List models:

```bash
ollama list
```

Pull default chat model:

```bash
ollama pull qwen3:8b
```

Pull embedding model:

```bash
ollama pull nomic-embed-text
```

Start Ollama app or daemon before using the backend.

## Troubleshooting

### Backend says database connection refused

Start the DB:

```bash
docker compose up -d
```

### Upload works but semantic search is not available

Make sure Ollama is running and the embedding model is pulled:

```bash
ollama pull nomic-embed-text
```

### Note generation or classification fails

Make sure Ollama is running and the chat model is pulled:

```bash
ollama pull qwen3:8b
```

### First audio transcription is slow

That is expected while `faster-whisper` downloads the local model cache.

### I changed models in `.env`

Restart the backend after editing `.env` so the new Ollama model settings are loaded.

## Project Structure

```text
agents/
  frontend/
  src/
    agent/        local note generation and classifier workflow
    api/          FastAPI app
    rag/          ingestion, embeddings, retrieval, grounded chat
  docker-compose.yml
  spine_schema.sql
```

## One-Command Summary

From `agents/`:

```bash
docker compose up -d
uv sync
uv run uvicorn src.api.app:app --reload --port 8000
```

Then in another terminal:

```bash
cd frontend
npm install
npm run dev
```
