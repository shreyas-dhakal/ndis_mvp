import asyncio
import argparse
import os

from docling.document_converter import DocumentConverter

from app.core.config import DATA_DIR
from app.db.ingest_store import store_chunks_and_records
from app.ingest.chunking import chunk_for_record_type
from app.ingest.typeclassify import classify_record_type
from app.ingest.types import ParsedDoc, ParsedRecord
from app.inference.embeddings import embed_texts_async
from app.routes.ingest import parse_docling_document

from app.db.pgvector_adapter import close_pool, connect
from psycopg.rows import dict_row


def _file_mime_type(path: str) -> str | None:
    import mimetypes

    mime, _ = mimetypes.guess_type(path)
    return mime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="local")
    parser.add_argument("--author", default="user")
    parser.add_argument("--doc_type", default="document")
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    args = parser.parse_args()

    converter = DocumentConverter()

    try:
        # Re-ingest only files whose current records have no chunks.
        with connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                files = [
                    os.path.join(DATA_DIR, f)
                    for f in os.listdir(DATA_DIR)
                    if os.path.isfile(os.path.join(DATA_DIR, f))
                ]
                if args.limit and args.limit > 0:
                    files = files[: args.limit]

                for saved_path in sorted(files):
                    filename = os.path.basename(saved_path)
                    # original_filename was the raw upload name (after we prefix uuid on disk)
                    original_filename = filename.split("_", 1)[1] if "_" in filename else filename

                    cur.execute(
                        """
                        select count(*) as chunks_count
                        from chunks c
                        join records r on r.record_id = c.record_id
                        join documents d on d.document_id = c.document_id
                        where d.original_filename = %s
                        """,
                        [original_filename],
                    )
                    chunks_count = cur.fetchone()["chunks_count"]
                    if chunks_count and chunks_count > 0:
                        continue

                    print(f"Re-ingesting: {filename}")
                    dl_doc = converter.convert(saved_path).document
                    parsed: ParsedDoc = parse_docling_document(dl_doc)

                    record_objs: list[ParsedRecord] = []
                    for block in parsed.blocks:
                        if not (block.text or "").strip():
                            continue
                    r_type = classify_record_type(block.text)
                    chunks = chunk_for_record_type(
                        record_type=r_type,
                        text=block.text,
                        section=block.section,
                        provenance_pointer=block.provenance_pointer,
                        title=block.title,
                    )
                    record_objs.append(
                        ParsedRecord(
                            record_type=r_type,
                                title=block.title,
                                content=block.text,
                                provenance_pointer=block.provenance_pointer,
                                section=block.section,
                                chunks=chunks,
                            )
                        )

                    global_idx = 0
                    for r in record_objs:
                        for c in r.chunks:
                            c.global_index = global_idx
                            global_idx += 1

                    all_chunk_texts = [c.chunk_text for r in record_objs for c in r.chunks]
                    embeddings = asyncio.run(embed_texts_async(all_chunk_texts))

                    if not embeddings:
                        print(f"Skipping {filename}: no chunkable text")
                        continue

                    created = store_chunks_and_records(
                        source=args.source,
                        author=args.author,
                        doc_type=args.doc_type,
                        original_filename=original_filename,
                        mime_type=_file_mime_type(saved_path),
                        parsed_doc=parsed,
                        records=record_objs,
                        chunk_embeddings=embeddings,
                        chunk_embedding_order=[c.global_index for r in record_objs for c in r.chunks],
                    )

                    print(
                        f"Stored document_id={created['document_id']} "
                        f"records={created['records_created']} chunks={created['chunks_created']}"
                    )
    finally:
        close_pool()


if __name__ == "__main__":
    main()
