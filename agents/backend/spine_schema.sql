CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS age;
EXCEPTION
    WHEN undefined_file OR feature_not_supported THEN
        RAISE NOTICE 'Apache AGE is not installed in this Postgres runtime; graph retrieval stays disabled.';
END
$$;

CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('person', 'org')),
    display_name TEXT NOT NULL,
    aliases TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    original_filename TEXT,
    mime_type TEXT,
    sha256 TEXT,
    storage_path TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS entity_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'about',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (entity_id, document_id, relation_type)
);

CREATE TABLE IF NOT EXISTS records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID REFERENCES entities(id),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    record_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'dismissed')),
    body JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT NOT NULL,
    author TEXT NOT NULL,
    transcript TEXT,
    pdf_path TEXT,
    title TEXT,
    content TEXT,
    provenance_pointer TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tsv TSVECTOR,
    created_at TIMESTAMPTZ DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    confirmed_by TEXT,
    actioned_at TIMESTAMPTZ,
    actioned_by TEXT
);

CREATE TABLE IF NOT EXISTS entity_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    record_id UUID NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'about',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (entity_id, record_id, relation_type)
);

ALTER TABLE records ADD COLUMN IF NOT EXISTS document_id UUID REFERENCES documents(id) ON DELETE CASCADE;
ALTER TABLE records ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE records ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE records ADD COLUMN IF NOT EXISTS provenance_pointer TEXT;
ALTER TABLE records ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE records ADD COLUMN IF NOT EXISTS tsv TSVECTOR;

CREATE TABLE IF NOT EXISTS links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_record_id UUID REFERENCES records(id) ON DELETE CASCADE,
    to_record_id UUID REFERENCES records(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id UUID NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    record_type TEXT NOT NULL,
    section TEXT,
    offset_start INTEGER,
    offset_end INTEGER,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    chunk_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR({{EMBEDDING_DIM}}),
    tsv TSVECTOR,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    record_id UUID REFERENCES records(id) ON DELETE CASCADE,
    params JSONB,
    result_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_sha256_unique ON documents (sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_documents_entity_id ON entity_documents (entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_documents_document_id ON entity_documents (document_id);
CREATE INDEX IF NOT EXISTS idx_records_entity_id ON records (entity_id);
CREATE INDEX IF NOT EXISTS idx_records_document_id ON records (document_id);
CREATE INDEX IF NOT EXISTS idx_records_record_type ON records (record_type);
CREATE INDEX IF NOT EXISTS idx_records_created_at ON records (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_records_tsv ON records USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_records_title_trgm ON records USING GIN (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_entity_records_entity_id ON entity_records (entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_records_record_id ON entity_records (record_id);
CREATE INDEX IF NOT EXISTS idx_links_from_record_id ON links (from_record_id);
CREATE INDEX IF NOT EXISTS idx_links_to_record_id ON links (to_record_id);
CREATE INDEX IF NOT EXISTS idx_chunks_record_id ON chunks (record_id);
CREATE INDEX IF NOT EXISTS idx_chunks_record_chunk_index ON chunks (record_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_record_type ON chunks (record_type);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_text_trgm ON chunks USING GIN (chunk_text gin_trgm_ops);
DO $$
BEGIN
    IF {{EMBEDDING_DIM}} <= 2000 THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)';
    ELSE
        RAISE NOTICE 'Skipping ANN index on chunks.embedding because vector dimensions (%) exceed pgvector index limits for vector; retrieval will use sequential vector scan unless dimensions are reduced.', {{EMBEDDING_DIM}};
    END IF;
END
$$;
