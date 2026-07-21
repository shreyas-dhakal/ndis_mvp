from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any

_GUARDS_PATH = Path(__file__).resolve().parents[2] / "guards.py"
_SPEC = importlib.util.spec_from_file_location("ndis_root_guards", _GUARDS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load guards module from {_GUARDS_PATH}")

_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

CheckResults = _MODULE.CheckResults
validate_input = _MODULE.validate_input
validate_output = _MODULE.validate_output
has_blocking_failures = _MODULE.has_blocking_failures


class GuardValidationError(ValueError):
    pass


def blocking_failure_messages(results: list[Any]) -> list[str]:
    return [
        result.msg
        for result in results
        if not result.status and result.severity == "block" and result.msg
    ]


def require_valid_input(text: str, *, field_name: str) -> None:
    results = validate_input(text)
    if has_blocking_failures(results):
        failures = "; ".join(blocking_failure_messages(results)) or "Validation failed."
        raise GuardValidationError(f"Invalid {field_name}: {failures}")


def require_valid_output(note: Any, *, session_date: date, label: str) -> None:
    results = validate_output(note, session_date)
    if has_blocking_failures(results):
        failures = "; ".join(blocking_failure_messages(results)) or "Validation failed."
        raise GuardValidationError(f"Invalid {label}: {failures}")
