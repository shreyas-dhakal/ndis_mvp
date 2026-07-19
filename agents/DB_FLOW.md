# Database Flow

This document maps how the `agents` app uses Postgres across ingestion, retrieval, note generation, trigger classification, and task review.

Primary schema source: `agents/spine_schema.sql`

Primary code paths:
- `agents/src/rag/db.py`
- `agents/src/rag/service.py`
- `agents/src/api/app.py`
- `agents/src/agent/graph.py`
- `agents/src/agent/classiferAgent.py`

## Overview

```mermaid
flowchart TD
    A[Frontend or API client] --> B[FastAPI: src/api/app.py]
    B --> C[Schema bootstrap: ensure_schema]
    B --> D[Document ingest]
    B --> E[Retrieve or chat]
    B --> F[Generate note]
    B --> G[Task review actions]

    D --> H[(documents)]
    D --> I[(records)]
    D --> J[(chunks)]

    E --> J
    E --> I

    F --> I
    F --> J
    F --> K[Classifier agent]
    K --> L[(links)]
    K --> M[(events)]
    K --> I

    G --> I
    G --> M

    N[LangGraph checkpointer] -. uses same Postgres instance .-> O[(langgraph checkpoint tables)]
    F -. workflow state .-> N
```

## Core Tables

```mermaid
erDiagram
    DOCUMENTS ||--o{ RECORDS : contains
    DOCUMENTS ||--o{ CHUNKS : contains
    RECORDS ||--o{ CHUNKS : split_into
    RECORDS ||--o{ LINKS : from_record
    RECORDS ||--o{ LINKS : to_record
    RECORDS ||--o{ EVENTS : audited_by
    ENTITIES ||--o{ RECORDS : owns

    ENTITIES {
        uuid id PK
        text entity_type
        text display_name
        text_array aliases
        timestamptz created_at
    }

    DOCUMENTS {
        uuid id PK
        text source
        text original_filename
        text mime_type
        text sha256
        text storage_path
        jsonb metadata
        timestamptz created_at
    }

    RECORDS {
        uuid id PK
        uuid entity_id FK
        uuid document_id FK
        text record_type
        text status
        jsonb body
        text source
        text author
        text transcript
        text pdf_path
        text title
        text content
        text provenance_pointer
        jsonb metadata
        tsvector tsv
        timestamptz created_at
        timestamptz confirmed_at
        text confirmed_by
        timestamptz actioned_at
        text actioned_by
    }

    CHUNKS {
        uuid id PK
        uuid record_id FK
        uuid document_id FK
        text record_type
        text section
        int offset_start
        int offset_end
        int chunk_index
        text chunk_text
        jsonb chunk_metadata
        vector embedding
        tsvector tsv
        timestamptz created_at
    }

    LINKS {
        uuid id PK
        uuid from_record_id FK
        uuid to_record_id FK
        text link_type
        timestamptz created_at
    }

    EVENTS {
        bigint id PK
        text actor
        text action
        uuid record_id FK
        jsonb params
        text result_hash
        timestamptz created_at
    }
```

## What Each Table Stores

- `documents`: one row per uploaded source file.
- `records`: the main normalized content table. This stores both ingested document records and generated operational records such as notes and incident tasks.
- `chunks`: retrieval units for search and RAG. Each chunk belongs to a record and optionally to a document.
- `links`: explicit relationships between records. Currently used to link a generated incident task back to the source note via `triggered_by`.
- `events`: append-only audit trail for task decisions and user actions.
- `entities`: present in schema but not actively populated by the current code paths.

## Write Flow 1: Document Ingestion

Code path:
- API: `POST /documents` and `POST /ingest/file`
- Function: `ingest_upload()` in `agents/src/rag/service.py`

```mermaid
flowchart TD
    A[Upload file] --> B[Save raw file to data/uploads]
    B --> C[Extract text blocks]
    C --> D[Convert blocks to ParsedRecord objects]
    D --> E[Chunk each record]
    E --> F[Generate embeddings if available]
    F --> G[Insert document row]
    G --> H[Insert one records row per parsed block]
    H --> I[Insert one chunks row per chunk]
    I --> J[Commit transaction]

    G --> K[(documents)]
    H --> L[(records)]
    I --> M[(chunks)]
```

### Ingest Writes

- `documents`
  - `source`
  - `original_filename`
  - `mime_type`
  - `sha256`
  - `storage_path`
  - `metadata.doc_type`
- `records`
  - `document_id`
  - `record_type`
  - `status = confirmed`
  - `body` with title/content/section/provenance
  - `source`
  - `author`
  - `title`
  - `content`
  - `provenance_pointer`
  - `metadata.doc_type`
  - `metadata.ingest_source = upload`
  - `tsv`
- `chunks`
  - `record_id`
  - `document_id`
  - `record_type`
  - offsets and section metadata
  - `chunk_text`
  - `chunk_metadata.source`
  - `embedding` when available
  - `tsv`

## Read Flow 1: Document Listing and Deletion

Code path:
- `GET /documents` -> `list_documents()`
- `DELETE /documents/{document_id}` -> `delete_document()`

```mermaid
flowchart TD
    A[GET /documents] --> B[Query documents]
    B --> C[Correlated counts from records and chunks]
    C --> D[Return document summaries]

    E[DELETE /documents/:id] --> F[Delete from documents returning storage_path]
    F --> G[DB cascades to records and chunks]
    G --> H[Delete physical file from disk]
```

Notes:
- Deleting a `documents` row cascades to child `records` and `chunks` because of foreign keys.
- No application-level delete is needed for those child rows.

## Read Flow 2: Retrieval and Chat

Code path:
- `POST /retrieve` -> `retrieve_chunks()`
- `POST /chat` and `POST /agent/answer` -> `answer_question()` -> `retrieve_chunks()`

```mermaid
flowchart TD
    A[User query] --> B{Embedding available?}
    B -->|Yes| C[Vector search on chunks.embedding]
    B -->|No| D[Skip semantic search]
    A --> E[FTS search on chunks.tsv]
    C --> F[Fuse semantic and lexical scores]
    D --> F
    E --> F
    F --> G[Fetch payload rows from chunks join records]
    G --> H[Build snippets and citations]
    H --> I[Optional LLM answer generation]

    C --> J[(chunks)]
    E --> J
    G --> J
    G --> K[(records)]
```

### Retrieval Reads

- Search candidates come from `chunks`.
- Citation metadata is completed by joining `chunks.record_id -> records.id`.
- `record_type`, `source`, and `candidate_chunk_ids` are used as optional filters.

## Write Flow 2: Note Generation

Code path:
- `POST /generate/text`
- `POST /generate/audio`
- `POST /generate/resume`
- Final persistence: `store_generated_note()` in `agents/src/rag/service.py`

```mermaid
flowchart TD
    A[Transcript or audio upload] --> B[LangGraph note workflow]
    B --> C[Human review interrupt]
    C -->|approved| D[Finalize note and PDF]
    D --> E[store_generated_note]
    E --> F[Insert records row of type note]
    E --> G[Insert chunks row for note text]
    G --> H[Run classifier agent]

    F --> I[(records)]
    G --> J[(chunks)]
```

### Generated Note Writes

- `records`
  - `record_type = note`
  - `status = confirmed`
  - `body = full structured note JSON`
  - `source = thread:<thread_id>`
  - `author = support_worker`
  - `title = Generated NDIS progress note`
  - `content = flattened note text`
  - `metadata.origin = note_generator`
  - `metadata.thread_id`
  - `tsv`
- `chunks`
  - one chunk covering the flattened generated note text
  - `section = generated_note`
  - optional `embedding`

## Write Flow 3: Classifier Agent and Task Creation

Code path:
- Triggered from `build_done_response()` in `agents/src/api/app.py`
- Executed by `run_agent2()` in `agents/src/agent/classiferAgent.py`
- Taxonomy source: `agents/src/agent/taxonomy.yaml`

```mermaid
flowchart TD
    A[Generated note row] --> B[Load taxonomy.yaml]
    B --> C[LLM classification on note JSON]
    C --> D{task_result?}
    D -->|No| E[Return decision only]
    D -->|Yes| F[Create incident task record]
    F --> G[Link task to note]
    G --> H[Write audit event]

    F --> I[(records)]
    G --> J[(links)]
    H --> K[(events)]
```

### Classifier Writes

If the classifier matches a trigger:

- `records`
  - `record_type = incident`
  - `status = draft`
  - `author = a2_agent`
  - `source = a2:<source_note_record_id>`
  - `body.trigger_id`
  - `body.reasoning`
  - `body.workflow`
  - `body.deadline`
- `links`
  - `from_record_id = incident task`
  - `to_record_id = source note`
  - `link_type = triggered_by`
- `events`
  - `actor = a2_agent`
  - `action = a2.trigger_matched`
  - `params.trigger_id`

If the classifier does not match:

- no DB writes occur in the classifier path
- only the in-memory decision is returned to the API response

## Read and Write Flow 4: Task Queue

Code path:
- `GET /tasks`
- `POST /tasks/{task_id}/approve`
- `POST /tasks/{task_id}/dismiss`
- `POST /tasks/{task_id}/action`

```mermaid
flowchart TD
    A[GET /tasks?view=pending] --> B[Read incident records with status=draft]
    A2[GET /tasks?view=confirmed] --> B2[Read incident records with status=confirmed and actioned_at is null]
    B --> C[Join links to source note]
    B2 --> C
    C --> D[Return task cards to frontend]

    E[Approve] --> F[Update records.status to confirmed]
    F --> G[Insert human.approve_task event]

    H[Dismiss] --> I[Update records.status to dismissed]
    I --> J[Insert human.dismiss_task event]

    K[Mark actioned] --> L[Update actioned_at and actioned_by]
    L --> M[Insert human.action_task event]

    F --> N[(records)]
    I --> N
    L --> N
    G --> O[(events)]
    J --> O
    M --> O
```

### Task State Model

```mermaid
stateDiagram-v2
    [*] --> draft: classifier creates incident
    draft --> confirmed: approve task
    draft --> dismissed: dismiss task
    confirmed --> confirmed: waiting for action
    confirmed --> actioned: actioned_at set
```

Implementation detail:
- `actioned` is not a separate `status` value.
- A task is considered actioned when `status = confirmed` and `actioned_at IS NOT NULL`.

## Record Types in Practice

The `records` table is polymorphic. Current code paths store at least these logical record types:

- ingested document-derived records: values inferred by `classify_record_type()` during ingestion
- generated support notes: `record_type = note`
- classifier-created tasks: `record_type = incident`

This makes `records` the hub of the app.

## End-to-End Operational Flow

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as FastAPI
    participant G1 as Note Graph
    participant DB as Postgres
    participant G2 as Classifier Agent

    UI->>API: upload document
    API->>DB: insert documents, records, chunks

    UI->>API: ask question
    API->>DB: read chunks + records for retrieval
    API-->>UI: answer with citations

    UI->>API: generate note
    API->>G1: invoke note workflow
    G1-->>API: approved note
    API->>DB: insert note record + note chunk
    API->>G2: classify note against taxonomy
    alt trigger matched
        G2->>DB: insert incident record
        G2->>DB: insert link to source note
        G2->>DB: insert audit event
        API-->>UI: note done + task created
    else no trigger matched
        API-->>UI: note done + no task
    end

    UI->>API: open task queue
    API->>DB: read incident records + links
    API-->>UI: tasks

    UI->>API: approve, dismiss, or action task
    API->>DB: update incident record
    API->>DB: insert audit event
```

## Non-Application Tables

`agents/src/agent/graph.py` configures a LangGraph `PostgresSaver` checkpointer.

That means the same Postgres database also stores LangGraph checkpoint tables managed by LangGraph itself. Those tables are not defined in `spine_schema.sql`, but they are part of the runtime DB footprint for note generation and resume flows.

## Practical Summary

- `documents` is the file registry.
- `records` is the source-of-truth content and task table.
- `chunks` powers retrieval.
- `links` ties classifier-created incidents back to notes.
- `events` provides an audit trail for classifier and human actions.
- Note generation and task generation are separate stages, but both persist through `records`.
