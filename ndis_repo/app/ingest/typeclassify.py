import re


def classify_record_type(text: str) -> str:
    t = (text or "").lower()

    # Lightweight, deterministic heuristic. Replace with an LLM classifier later.
    if re.search(r"\b(incident|reported|injury|damage)\b", t):
        return "incident"
    if re.search(r"\b(consent|i agree|permission|authoriz)\b", t):
        return "consent"
    if re.search(r"\b(goal|aim|target|objective)\b", t):
        return "goal"
    if re.search(r"\b(plan|strategy|steps|intervention|schedule)\b", t):
        return "plan"
    if re.search(r"\b(note|meeting|progress|update|journal)\b", t):
        return "note"
    return "generic"
