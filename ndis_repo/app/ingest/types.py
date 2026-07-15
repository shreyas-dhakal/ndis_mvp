from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedChunk:
    chunk_text: str
    section: str | None
    offset_start: int
    offset_end: int
    chunk_index: int
    global_index: int  # used for mapping embeddings back to chunks
    chunk_metadata: dict


@dataclass
class ParsedRecord:
    record_type: str
    title: str | None
    content: str
    provenance_pointer: str | None
    section: str | None
    chunks: list[ParsedChunk]


@dataclass
class ParsedDoc:
    @dataclass
    class Block:
        title: str | None
        text: str
        section: str | None
        provenance_pointer: str | None

    blocks: list[Block]
