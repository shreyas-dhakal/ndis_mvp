import os
import uuid
import re

from docling.document_converter import DocumentConverter
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import (
    DATA_DIR,
)
from app.db.ingest_store import store_chunks_and_records
from app.ingest.chunking import chunk_for_record_type
from app.ingest.typeclassify import classify_record_type
from app.ingest.types import ParsedDoc, ParsedRecord
from app.inference.embeddings import embed_texts_async

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestResponse(BaseModel):
    document_id: int
    records_created: int
    chunks_created: int


@router.post("/file", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    source: str = Form("local"),
    author: str = Form("user"),
    doc_type: str = Form("document"),
):
    # Persist upload to disk for traceability
    os.makedirs(DATA_DIR, exist_ok=True)
    doc_id = str(uuid.uuid4())
    saved_path = os.path.join(DATA_DIR, f"{doc_id}_{file.filename}")
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    converter = DocumentConverter()
    try:
        dl_doc = converter.convert(saved_path).document
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Docling parse failed: {e}")

    parsed = parse_docling_document(dl_doc)

    # Convert records -> chunks -> embeddings -> store
    record_objs: list[ParsedRecord] = []
    for block in parsed.blocks:
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

    # Ensure global_index is unique across ALL chunks in this ingestion run,
    # so we map embeddings back to the correct chunk deterministically.
    global_idx = 0
    for r in record_objs:
        for c in r.chunks:
            c.global_index = global_idx
            global_idx += 1

    # Embed chunk text
    all_chunk_texts = [c.chunk_text for r in record_objs for c in r.chunks]
    embeddings = await _embed_chunks(all_chunk_texts)

    # Store
    created = store_chunks_and_records(
        source=source,
        author=author,
        doc_type=doc_type,
        original_filename=file.filename,
        mime_type=file.content_type,
        parsed_doc=parsed,
        records=record_objs,
        chunk_embeddings=embeddings,
        chunk_embedding_order=[c.global_index for r in record_objs for c in r.chunks],
    )

    return IngestResponse(
        document_id=created["document_id"],
        records_created=created["records_created"],
        chunks_created=created["chunks_created"],
    )


def parse_docling_document(dl_document) -> ParsedDoc:
    blocks: list = []

    # Labels that should always start their own standalone block
    # (tables/pictures are structurally distinct, never merge them with prose)
    ATOMIC_LABELS = {"table", "picture", "formula"}

    # Labels that act as section boundaries — starting a new heading
    # should flush whatever text block we were accumulating
    HEADING_LABELS = {"section_header", "title", "page_header"}

    def clean(text: str) -> str:
        text = text.replace("\u00ad", "")
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def flush(buffer_texts, buffer_label, section, page_no, ref):
        """Turn accumulated text fragments into one Block."""
        if not buffer_texts:
            return None
        merged = clean("\n".join(buffer_texts))
        if not merged:
            return None
        return ParsedDoc.Block(
            title=buffer_label,
            text=merged,
            section=section,
            provenance_pointer=f"docling://page/{page_no}/item/{ref}",
        )

    try:
        buffer_texts: list = []
        buffer_label = None
        buffer_section = None
        buffer_page_no = None
        buffer_ref = None
        current_heading = None  # tracks the most recent section heading text

        for item, _level in dl_document.iterate_items():
            label = getattr(item, "label", None)
            label_str = str(label.value if hasattr(label, "value") else label)

            prov = getattr(item, "prov", None)
            page_no = getattr(prov[0], "page_no", None) if prov else None
            section = f"page_{page_no}" if page_no is not None else "unknown"

            # --- Tables/pictures/formulas: flush buffer, emit their own block ---
            if label_str in ATOMIC_LABELS:
                b = flush(
                    buffer_texts,
                    buffer_label,
                    buffer_section,
                    buffer_page_no,
                    buffer_ref,
                )
                if b:
                    blocks.append(b)
                buffer_texts, buffer_label = [], None

                if label_str == "table":
                    try:
                        text = item.export_to_markdown(dl_document)
                    except Exception:
                        text = getattr(item, "text", "") or ""
                else:
                    text = (
                        getattr(item, "text", "") or getattr(item, "caption", "") or ""
                    )

                text = clean(text)
                if text:
                    blocks.append(
                        ParsedDoc.Block(
                            title=f"{label_str}"
                            + (f" ({current_heading})" if current_heading else ""),
                            text=text,
                            section=section,
                            provenance_pointer=f"docling://page/{page_no}/item/{item.self_ref}",
                        )
                    )
                continue

            # --- Headings: flush buffer, remember heading as context for the NEXT block ---
            if label_str in HEADING_LABELS:
                b = flush(
                    buffer_texts,
                    buffer_label,
                    buffer_section,
                    buffer_page_no,
                    buffer_ref,
                )
                if b:
                    blocks.append(b)
                buffer_texts, buffer_label = [], None
                current_heading = (
                    clean(getattr(item, "text", "") or "") or current_heading
                )
                continue

            # --- Regular text/list items: accumulate into the running buffer ---
            text = clean(getattr(item, "text", "") or "")
            if not text:
                continue

            buffer_texts.append(text)
            buffer_label = (
                current_heading or label_str
            )  # prefer heading as the block's title
            buffer_section = section
            buffer_page_no = page_no
            buffer_ref = item.self_ref

        # Flush whatever's left at the end
        b = flush(
            buffer_texts, buffer_label, buffer_section, buffer_page_no, buffer_ref
        )
        if b:
            blocks.append(b)

    except Exception as e:
        print("Docling structured item iteration failed: %s", e)
        blocks = []

    # Fallback: unchanged, true last resort
    if not blocks:
        full_text = None
        for method in ("export_to_text", "export_to_markdown"):
            if hasattr(dl_document, method):
                try:
                    full_text = getattr(dl_document, method)()
                    if full_text:
                        break
                except Exception:
                    continue
        if not full_text:
            full_text = getattr(dl_document, "text", None)

        full_text = (full_text or "").strip()
        if not full_text:
            raise HTTPException(
                status_code=400, detail="Docling produced no extractable text"
            )

        print("Falling back to single-block extraction — structured items unavailable")
        blocks = [
            ParsedDoc.Block(
                title=None,
                text=full_text,
                section="full",
                provenance_pointer="docling://document",
            )
        ]

    return ParsedDoc(blocks=blocks)


@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def _embed_chunks(texts: list[str]) -> list[list[float]]:
    return await embed_texts_async(texts)
