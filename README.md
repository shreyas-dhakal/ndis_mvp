# NDIS Agents MVP

## Run

### 1. Create env

From `agents/backend/`:

```bash
cp .env.example .env
```

### 2. Set your database and model config

Edit `agents/backend/.env` and set at least:

```bash
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres?sslmode=require

CHAT_PROVIDER=azure_openai
AGENT_PROVIDER=azure_openai
EMBEDDING_PROVIDER=azure_openai
VOICE_PROVIDER=faster_whisper

CHAT_MODEL=gpt-5.4
CHAT_DEPLOYMENT=gpt-5.4
AGENT_MODEL=gpt-5.4
AGENT_DEPLOYMENT=gpt-5.4

EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DEPLOYMENT=text-embedding-3-large
EMBEDDING_DIM=3072

AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_API_VERSION=2025-01-01-preview

AGE_ENABLED=false
```

### 3. Install backend dependencies

From `agents/backend/`:

```bash
uv sync
```

### 4. Start backend

From `agents/backend/`:

```bash
uv run uvicorn src.api.app:app --reload --port 8000
```

Backend runs on:

```text
http://localhost:8000
```

### 5. Start frontend

From `agents/frontend/`:

```bash
npm install
npm run dev
```

Frontend runs on:

```text
http://localhost:5173
```

## Notes

- Database is Supabase only
- Restart the backend after changing `.env`
- Schema is created automatically on backend startup
- With `EMBEDDING_DIM=3072`, pgvector ANN indexes are skipped because `vector` indexes are limited to 2000 dims; retrieval still works but vector search will be slower unless you reduce dimensions
