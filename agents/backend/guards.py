import re
from datetime import date, datetime
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_AU_PHONE_RE = re.compile(r"(?:\+?61|0)[2-478](?:[ -]?\d){8}")
_MEDICARE_RE = re.compile(r"\b\d{4}[ -]?\d{5}[ -]?\d{1}\b")
_NDIS_NUMBER_RE = re.compile(r"\bNDIS\s*#?\s*\d{9}\b", re.IGNORECASE)
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,16}\b")

_PII_PATTERNS = {
    "email": _EMAIL_RE,
    "au_phone": _AU_PHONE_RE,
    "medicare": _MEDICARE_RE,
    "ndis_number": _NDIS_NUMBER_RE,
    "credit_card": _CREDIT_CARD_RE,
}

_INJECTION_PATTERNS = [
    r"ignore (all |the )?(previous|prior|above) (instructions|prompt)",
    r"disregard (all |the )?(previous|prior|above)",
    r"you are now",
    r"new instructions?:",
    r"system prompt",
    r"reveal (your|the) (system )?prompt",
    r"act as (if you|though) (there are|were) no (rules|restrictions)",
    r"jailbreak",
    r"do anything now",
]
_INJECTION_RE = (
    re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)
    if _INJECTION_PATTERNS
    else None
)

_TOXIC_KEYWORDS = [
    "kill yourself",
]
_TOXIC_RE = (
    re.compile("|".join(re.escape(k) for k in _TOXIC_KEYWORDS), re.IGNORECASE)
    if _TOXIC_KEYWORDS
    else None
)


@dataclass
class CheckResults:
    name: str
    status: bool
    severity: str
    msg: str = ""


# Input Validators


def check_if_empty(text: str) -> CheckResults:
    status = bool(text and text.strip())
    msg = "" if status else "Input text is empty or has white spaces."
    return CheckResults("input not empty", status, "block", msg)


def check_length(text: str, min_char: int, max_char: int) -> CheckResults:
    if text is None:
        return CheckResults(
            "length is valid",
            False,
            "block",
            "Cannot check length: input is empty or None.",
        )
    n = len(text)
    status = min_char <= n <= max_char
    msg = "" if status else f"The length {n} is beyond the limit {[min_char, max_char]}"
    return CheckResults("length is valid", status, "block", msg)


def check_prompt_injection(text: str) -> CheckResults:
    if _INJECTION_RE is None:
        return CheckResults("Prompt Injection", True, "block", "")
    match = _INJECTION_RE.search(text or "")
    status = match is None
    msg = (
        ""
        if status
        else f"Possible Prompt Injection pattern detected:'{match.group(0)}'"
    )
    return CheckResults("Prompt Injection", status, "block", msg)


def check_input_toxicity(text: str) -> CheckResults:
    if _TOXIC_RE is None:
        return CheckResults("Toxic Language", True, "warn", "")
    match = _TOXIC_RE.search(text or "")
    status = match is None
    msg = "" if status else "Toxic Language detected in the text."
    return CheckResults("Toxic Language", status, "warn", msg)


def check_input_pii(text: str) -> CheckResults:
    text = text or ""
    found = [name for name, pattern in _PII_PATTERNS.items() if pattern.search(text)]
    status = len(found) == 0
    msg = "" if status else f"Possible PII detected: {', '.join(found)}"
    return CheckResults("PII Detected", status, "warn", msg)


def validate_input(text: str) -> list[CheckResults]:
    results = []
    results.append(check_if_empty(text))
    results.append(check_length(text, 10, 5000))
    results.append(check_prompt_injection(text))
    results.append(check_input_toxicity(text))
    results.append(check_input_pii(text))

    return results


# Output Validators
def check_output_sections_not_empty(note) -> CheckResults:
    if hasattr(note, "model_dump"):
        data = note.model_dump()
    elif isinstance(note, dict):
        data = note
    else:
        data = {k: v for k, v in vars(note).items() if not k.startswith("_")}

    empty_fields = [f for f, v in data.items() if isinstance(v, str) and not v.strip()]
    ok = len(empty_fields) == 0
    msg = "" if ok else f"Empty SOAP section(s): {', '.join(empty_fields)}"
    return CheckResults("output_sections_not_empty", ok, "block", msg)


def _coerce_to_date(value, fallback: date) -> date:
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return fallback


def check_output_no_future_date(note_date: date, session_date: date) -> CheckResults:
    note_date = _coerce_to_date(note_date, fallback=session_date)
    ok = note_date <= session_date
    msg = "" if ok else f"Note date {note_date} is after session date {session_date}"
    return CheckResults("output_no_future_date", ok, "block", msg)


def check_output_toxicity_heuristic(note) -> CheckResults:
    if hasattr(note, "model_dump"):
        data = note.model_dump()
    elif isinstance(note, dict):
        data = note
    else:
        data = {k: v for k, v in vars(note).items() if not k.startswith("_")}

    combined = " ".join(str(v) for v in data.values())
    if _TOXIC_RE is None:
        return CheckResults("output_toxicity_heuristic", True, "block", "")
    match = _TOXIC_RE.search(combined)
    ok = match is None
    msg = "" if ok else "Potentially harmful/toxic language detected in generated note"
    return CheckResults("output_toxicity_heuristic", ok, "block", msg)


def validate_output(note, session_date: date) -> list[CheckResults]:
    note_date = (
        getattr(note, "date", None)
        or (note.get("date") if isinstance(note, dict) else None)
        or session_date
    )
    results = [
        check_output_sections_not_empty(note),
        check_output_no_future_date(note_date, session_date),
        check_output_toxicity_heuristic(note),
    ]
    return results


def has_blocking_failures(results: list[CheckResults]) -> bool:
    status = any((not r.status) and r.severity == "block" for r in results)
    return status
