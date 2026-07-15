from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"\S+")


@dataclass
class ParsedChunk:
    chunk_text: str
    section: str | None
    offset_start: int
    offset_end: int
    chunk_index: int
    chunk_metadata: dict


@dataclass
class ParsedRecord:
    record_type: str
    title: str | None
    content: str
    provenance_pointer: str | None
    section: str | None
    chunks: list[ParsedChunk]


def classify_record_type(text: str) -> str:
    lowered = (text or "").lower()
    if re.search(r"\b(incident|reported|injury|damage|fall|medication)\b", lowered):
        return "incident"
    if re.search(r"\b(consent|permission|authoriz|agreed)\b", lowered):
        return "consent"
    if re.search(r"\b(goal|aim|target|objective)\b", lowered):
        return "goal"
    if re.search(r"\b(plan|strategy|steps|intervention|schedule)\b", lowered):
        return "plan"
    return "note"


def _count_tokens(text: str) -> int:
    return len(_TOKEN_RE.findall(text or ""))


def _looks_like_heading(line: str) -> bool:
    value = (line or "").strip()
    if not value or len(value) > 120:
        return False
    if value.startswith("#") or value.endswith(":"):
        return True
    if re.match(r"^\d+(?:\.\d+)*\s+\S+", value):
        return True
    letters = re.sub(r"[^A-Za-z]", "", value)
    return bool(letters) and 6 <= len(value) <= 60 and value.upper() == value


def _split_into_paragraph_units(text: str) -> list[tuple[int, int, str]]:
    text = text or ""
    separators = list(re.finditer(r"(?:\r?\n){2,}", text))
    units: list[tuple[int, int, str]] = []
    start = 0
    for separator in separators:
        end = separator.start()
        value = text[start:end].strip()
        if value:
            units.append((start, end, value))
        start = separator.end()
    tail = text[start:].strip()
    if tail:
        units.append((start, len(text), tail))
    return units


def _split_unit_by_headings(unit_text: str, unit_start: int) -> list[tuple[int, int, str]]:
    lines = unit_text.splitlines(keepends=True)
    if len(lines) <= 1:
        return [(unit_start, unit_start + len(unit_text), unit_text)]

    out: list[tuple[int, int, str]] = []
    current_start = 0
    position = 0

    def flush(end_local: int) -> None:
        nonlocal current_start
        value = unit_text[current_start:end_local].strip()
        if value:
            out.append((unit_start + current_start, unit_start + end_local, value))
        current_start = end_local

    for line in lines:
        line_end = position + len(line)
        if _looks_like_heading(line) and position > current_start:
            flush(position)
        position = line_end

    flush(len(unit_text))
    return out


def _split_units(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for start, _end, value in _split_into_paragraph_units(text):
        out.extend(_split_unit_by_headings(value, start))
    return out


def chunk_text(
    text: str,
    *,
    record_type: str,
    section: str | None,
    provenance_pointer: str | None,
    title: str | None,
) -> list[ParsedChunk]:
    max_tokens = 320 if record_type in {"goal", "plan"} else 520
    overlap_tokens = 60 if record_type in {"goal", "plan"} else 90
    units = _split_units(text)
    if not units:
        return []

    token_counts = [_count_tokens(unit_text) for _, _, unit_text in units]
    chunks: list[ParsedChunk] = []
    chunk_index = 0
    unit_index = 0

    while unit_index < len(units):
        start_char = units[unit_index][0]
        end_char = units[unit_index][1]
        tokens = 0
        end_index = unit_index
        while end_index < len(units):
            if tokens + token_counts[end_index] > max_tokens:
                break
            tokens += token_counts[end_index]
            end_char = units[end_index][1]
            end_index += 1

        if end_index == unit_index:
            words = _TOKEN_RE.findall(units[unit_index][2])
            step = max(1, max_tokens - 1)
            for word_index in range(0, len(words), step):
                value = " ".join(words[word_index : word_index + max_tokens]).strip()
                if not value:
                    continue
                start_guess = max(text.lower().find(value.lower(), units[unit_index][0]), units[unit_index][0])
                chunks.append(
                    ParsedChunk(
                        chunk_text=value,
                        section=section,
                        offset_start=start_guess,
                        offset_end=start_guess + len(value),
                        chunk_index=chunk_index,
                        chunk_metadata={
                            "record_type": record_type,
                            "block_section": section,
                            "block_title": title,
                            "provenance_pointer": provenance_pointer,
                        },
                    )
                )
                chunk_index += 1
            unit_index += 1
            continue

        value = text[start_char:end_char].strip()
        if value:
            chunks.append(
                ParsedChunk(
                    chunk_text=value,
                    section=section,
                    offset_start=start_char,
                    offset_end=end_char,
                    chunk_index=chunk_index,
                    chunk_metadata={
                        "record_type": record_type,
                        "block_section": section,
                        "block_title": title,
                        "provenance_pointer": provenance_pointer,
                    },
                )
            )
            chunk_index += 1

        next_index = end_index
        covered = 0
        while overlap_tokens > 0 and next_index > unit_index and covered < overlap_tokens:
            next_index -= 1
            covered += token_counts[next_index]
        unit_index = next_index if next_index > unit_index else end_index

    return chunks
