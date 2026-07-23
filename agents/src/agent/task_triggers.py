import re
from typing import Optional


SYMPTOM_KEYWORDS = re.compile(
    r"\b(headache|migraine|dizz(?:y|iness)|nausea|vomit(?:ing)?|faint(?:ed|ing)?|"
    r"seizure|chest pain|shortness of breath|breathing difficulty|pain|unwell)\b"
)
SUPPORTED_ACTIVITY_CONTEXT = re.compile(
    r"\b(during|while|on the outing|on community access|at the program|during support|"
    r"during the support|during the walk|while shopping|during transport)\b"
)
SYMPTOM_EVENT_CONTEXT = re.compile(
    r"\b(reported|complained of|experienced|developed|started|became|felt|"
    r"suffer(?:ed|ing)?(?: from)?)\b"
)
PRE_SUPPORT_CONTEXT = re.compile(
    r"\b(before support|before the shift|before we arrived|prior to support|"
    r"earlier (?:today|that day)|history of|known history of|usual migraine)\b"
)


def _flatten_note_text(note: Optional[dict]) -> str:
    if not isinstance(note, dict):
        return ""

    parts: list[str] = []
    for value in note.values():
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned and cleaned.lower() != "not documented":
                parts.append(cleaned)
        elif isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
    return "\n".join(parts)


def detect_rule_based_trigger(note: Optional[dict]) -> Optional[tuple[str, str]]:
    lowered = _flatten_note_text(note).lower()
    if not lowered:
        return None

    if PRE_SUPPORT_CONTEXT.search(lowered):
        return None

    if not SYMPTOM_KEYWORDS.search(lowered):
        return None

    if not (
        SUPPORTED_ACTIVITY_CONTEXT.search(lowered)
        or SYMPTOM_EVENT_CONTEXT.search(lowered)
    ):
        return None

    return (
        "reportable_incident_injury",
        "Rule-based trigger matched: the note describes an acute physical symptom "
        "or injury arising during supported activity.",
    )
