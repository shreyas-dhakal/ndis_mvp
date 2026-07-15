from __future__ import annotations

import re

from app.ingest.types import ParsedChunk


_TOKEN_RE = re.compile(r"\S+")


def _count_tokens(text: str) -> int:
    # Token-aware chunking without requiring a specific tokenizer.
    # Approximate tokens as whitespace-delimited units.
    return len(_TOKEN_RE.findall(text or ""))


def _looks_like_heading(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if len(s) > 120:
        return False
    if s.startswith("#"):
        return True
    if s.endswith(":"):
        return True
    if re.match(r"^\d+(?:\.\d+)*\s+\S+", s):
        return True
    # All-caps-ish short lines
    if 6 <= len(s) <= 60:
        letters = re.sub(r"[^A-Za-z]", "", s)
        if letters and len(letters) / max(len(s), 1) > 0.7 and s.upper() == s:
            return True
    return False


def _split_into_paragraph_units(text: str) -> list[tuple[int, int, str]]:
    """Split by blank lines.

    Returns: (start_char, end_char, unit_text)
    """

    text = text or ""
    sep_iter = list(re.finditer(r"(?:\r?\n){2,}", text))
    units: list[tuple[int, int, str]] = []
    start = 0
    for sep in sep_iter:
        end = sep.start()
        chunk = text[start:end].strip()
        if chunk:
            units.append((start, end, chunk))
        start = sep.end()

    tail = text[start:].strip()
    if tail:
        units.append((start, len(text), tail))
    return units


def _split_unit_by_headings(unit_text: str, unit_start: int) -> list[tuple[int, int, str]]:
    """Further split a paragraph unit based on heading-like lines."""

    lines = unit_text.splitlines(keepends=True)
    if len(lines) <= 1:
        return [(unit_start, unit_start + len(unit_text), unit_text)]

    subunits: list[tuple[int, int, str]] = []
    cur_start_local = 0
    local_pos = 0

    def flush(end_local: int) -> None:
        nonlocal cur_start_local
        part = unit_text[cur_start_local:end_local].strip()
        if part:
            subunits.append((unit_start + cur_start_local, unit_start + end_local, part))
        cur_start_local = end_local

    for line in lines:
        line_end_local = local_pos + len(line)
        if _looks_like_heading(line):
            if local_pos > cur_start_local:
                flush(local_pos)
        local_pos = line_end_local

    flush(len(unit_text))
    return subunits


def _split_into_structural_units(text: str) -> list[tuple[int, int, str]]:
    units = _split_into_paragraph_units(text)
    out: list[tuple[int, int, str]] = []
    for start, _end, utext in units:
        out.extend(_split_unit_by_headings(utext, start))
    return out


def _make_chunks_token_aware(
    *,
    full_text: str,
    section: str | None,
    record_type: str,
    chunk_metadata: dict,
    max_tokens: int,
    overlap_tokens: int,
) -> list[ParsedChunk]:
    units = _split_into_structural_units(full_text)
    if not units:
        return []

    unit_tokens: list[int] = [_count_tokens(u[2]) for u in units]

    chunks: list[ParsedChunk] = []
    chunk_index = 0
    global_index = 0

    i = 0
    while i < len(units):
        chunk_start = units[i][0]
        chunk_end = units[i][1]
        tokens = 0

        j = i
        while j < len(units):
            # Stop before we exceed the budget.
            # If the first unit alone exceeds max_tokens, this will make `j == i`
            # and trigger the hard-split path below.
            if tokens + unit_tokens[j] > max_tokens:
                break
            tokens += unit_tokens[j]
            chunk_end = units[j][1]
            j += 1

        if j == i:
            # Extremely large single unit: hard split by word tokens.
            hard_tokens = _TOKEN_RE.findall(units[i][2])
            step = max(1, max_tokens - 1)
            for k in range(0, len(hard_tokens), step):
                part_tokens = hard_tokens[k : k + max_tokens]
                part_text = " ".join(part_tokens).strip()
                if not part_text:
                    continue

                approx_start = full_text.lower().find(part_text.lower(), units[i][0])
                approx_end = (
                    approx_start + len(part_text) if approx_start != -1 else units[i][1]
                )

                chunks.append(
                    ParsedChunk(
                        chunk_text=part_text,
                        section=section,
                        offset_start=approx_start if approx_start != -1 else units[i][0],
                        offset_end=approx_end,
                        chunk_index=chunk_index,
                        global_index=global_index,
                        chunk_metadata=chunk_metadata,
                    )
                )
                chunk_index += 1
                global_index += 1

            i += 1
            continue

        chunk_text = full_text[chunk_start:chunk_end].strip()
        if chunk_text:
            chunks.append(
                ParsedChunk(
                    chunk_text=chunk_text,
                    section=section,
                    offset_start=chunk_start,
                    offset_end=chunk_end,
                    chunk_index=chunk_index,
                    global_index=global_index,
                    chunk_metadata=chunk_metadata,
                )
            )
            chunk_index += 1
            global_index += 1

        # Advance with token overlap.
        next_i = j
        if overlap_tokens > 0:
            covered = 0
            next_i = j
            k = j - 1
            while k >= i and covered < overlap_tokens:
                covered += unit_tokens[k]
                next_i = k
                k -= 1

        if next_i <= i:
            next_i = j
        i = next_i

    return chunks


def chunk_for_record_type(
    record_type: str,
    text: str,
    *,
    section: str | None = None,
    provenance_pointer: str | None = None,
    title: str | None = None,
) -> list[ParsedChunk]:
    # Adaptive chunking:
    # - split on paragraph boundaries
    # - further split on heading-like lines
    # - assemble chunks using estimated token counts
    # - keep token overlap between adjacent chunks

    if record_type in {"goal", "plan"}:
        max_tokens = 320
        overlap_tokens = 60
    else:
        max_tokens = 520
        overlap_tokens = 90

    return _make_chunks_token_aware(
        full_text=text or "",
        section=section,
        record_type=record_type,
        chunk_metadata={
            "record_type": record_type,
            "source": "docling",
            "block_section": section,
            "block_title": title,
            "provenance_pointer": provenance_pointer,
        },
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
