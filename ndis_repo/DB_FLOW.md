# Database Flow

This document summarizes how data moves through Postgres and pgvector in the application.

## Overview

The database stores documents, records, chunks, and events.

Chunks are the main retrieval unit. Each chunk stores:

- source and citation metadata
- a full-text search vector (`tsv`)
- a fixed-dimension embedding (`vector(EMBEDDING_DIM)`)

Retrieval runs against `chunks`, then joins back to `records` to return citation details.

## Main Tables

- `documents`
  - one row per uploaded file
- `records`
  - structured units extracted from a document
- `chunks`
  - retrieval units derived from records
- `events`
  - append-only ingestion and audit events
- `record_links`
  - relationship table for linking records
- `entities`
  - reserved for person and organization modeling

## ER Diagram

```mermaid
erDiagram
    DOCUMENTS ||--o{ RECORDS : contains
    DOCUMENTS ||--o{ CHUNKS : sources
    DOCUMENTS ||--o{ EVENTS : logs
    RECORDS ||--o{ CHUNKS : splits_into
    RECORDS ||--o{ EVENTS : emits
    RECORDS ||--o{ RECORD_LINKS : source_of
    RECORDS o|--o{ RECORD_LINKS : target_record
    RECORDS o|--o{ RECORD_LINKS : target_goal

    ENTITIES {
        bigint entity_id PK
        text entity_type
        text display_name
        text external_id
        jsonb metadata
    }

    DOCUMENTS {
        bigint document_id PK
        text source
        text original_filename
        text mime_type
        text sha256
        jsonb metadata
        timestamptz created_at
    }

    RECORDS {
        bigint record_id PK
        bigint document_id FK
        text record_type
        text author
        text source
        text provenance_pointer
        text title
        text content
        jsonb metadata
        tsvector tsv
    }

    CHUNKS {
        bigint chunk_id PK
        bigint record_id FK
        bigint document_id FK
        text record_type
        text section
        integer offset_start
        integer offset_end
        integer chunk_index
        text chunk_text
        jsonb chunk_metadata
        vector embedding
        tsvector tsv
    }

    RECORD_LINKS {
        bigint link_id PK
        bigint source_record_id FK
        bigint target_record_id FK
        bigint target_goal_id FK
        text link_type
        jsonb metadata
        timestamptz created_at
    }

    EVENTS {
        bigint event_id PK
        text event_type
        text source
        text author
        bigint record_id FK
        bigint document_id FK
        text provenance_pointer
        jsonb event_data
        timestamptz created_at
    }
```

## Ingestion Flow

```mermaid
flowchart TD
    A[Uploaded file] --> B[Docling parse]
    B --> C[Parsed blocks]
    C --> D[Record type classification]
    D --> E[Chunk generation]
    E --> F[Batch embeddings via Ollama]
    F --> G[Insert documents row]
    G --> H[Insert records rows]
    H --> I[Insert chunks rows]
    I --> J[Insert ingestion.completed event]
```

## Retrieval Flow

```mermaid
flowchart TD
    A[User query] --> B[Query embedding via Ollama]
    A --> C[FTS query parsing]
    B --> D[ANN candidate generation on chunks.embedding]
    C --> E[Lexical candidate generation on chunks.tsv]
    D --> F[RRF rank fusion]
    E --> F
    F --> G[Top chunk ids]
    G --> H[Join records for citation metadata]
    H --> I[Response with text, snippet, highlights, citation]
```

## Indexing

- `chunks.tsv` uses a GIN index for lexical search
- `chunks.embedding` uses an HNSW index with cosine distance for semantic search
- standard B-tree indexes are used on document, record, and filter columns

## Notes

- `chunks` is the retrieval surface for both semantic and lexical search.
- `records` stores source context and is joined after ranking to build citations.
- `events` provides traceability for ingestion operations.
- `entities` and `record_links` are present in the schema for broader modeling, but are not populated by the current ingestion path.
