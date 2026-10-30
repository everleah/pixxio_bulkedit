"""Werte in Anzeige- und Schreibnormalform bringen.

Texte bleiben exakt erhalten (kein Trimmen). Normalisiert werden nur Typen, Formate
und Mehrfachauswahlen, damit der Vergleich Snapshot gegen Aenderung stabil ist.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.scripts.errors import ScriptContractError

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_INPUT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)
TRUE_WORDS = frozenset({"true", "ja", "yes", "1", "x"})
FALSE_WORDS = frozenset({"false", "nein", "no", "0"})
NUMBER_PATTERN = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
MULTI_SEPARATOR = re.compile(r"\s*[,;]\s*")

EMPTY_VALUES: tuple[object, ...] = (None, "", [], {})


def is_empty(value: Any) -> bool:
    if isinstance(value, str):
        return value == ""
    return any(value == empty for empty in EMPTY_VALUES)


def canonical(edit_type: str, value: Any, *, options: Sequence[str] = ()) -> Any:
    """Liefert den Wert in Anzeigenormalform oder ``None`` fuer leer."""
    if is_empty(value):
        return None
    kind = (edit_type or "text").lower()
    if kind in {"multiselection", "language"}:
        return canonical_list(value)
    if kind == "date":
        return canonical_date(value)
    if kind == "number":
        return canonical_number(value)
    if kind == "boolean":
        return canonical_boolean(value)
    if kind == "selection":
        return canonical_selection(value, options)
    if kind in {"map", "focalpoint", "orientation"}:
        return value if isinstance(value, str) else str(value)
    return value if isinstance(value, str) else str(value)


def canonical_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        items = [str(item) for item in value]
    else:
        items = MULTI_SEPARATOR.split(str(value))
    cleaned = [item for item in (part for part in items) if item != ""]
    unique: list[str] = []
    for item in cleaned:
        if item not in unique:
            unique.append(item)
    return unique


def canonical_selection(value: Any, options: Sequence[str] = ()) -> str:
    text = value if isinstance(value, str) else str(value)
    if options and text not in options:
        raise ScriptContractError(
            f"'{text}' ist keine bekannte Auswahl (erlaubt: {', '.join(sorted(options))})."
        )
    return text


def canonical_date(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        for pattern in DATE_INPUT_FORMATS:
            try:
                parsed = _parse(text, pattern)
            except ValueError:
                continue
            return parsed.strftime(DATE_FORMAT)
        raise ScriptContractError(
            f"'{value}' ist kein gueltiges Datum. Erwartet wird JJJJ-MM-TT oder "
            "JJJJ-MM-TT HH:MM:SS."
        )
    raise ScriptContractError("Datumswerte muessen als Text angegeben werden.")


def _parse(text: str, pattern: str) -> Any:
    from datetime import datetime

    return datetime.strptime(text, pattern)


def canonical_number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise ScriptContractError("Wahrheitswerte sind keine Zahlen.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    text = str(value).strip()
    if not NUMBER_PATTERN.match(text):
        raise ScriptContractError(f"'{value}' ist keine Zahl.")
    normalized = text.replace(",", ".")
    number = float(normalized)
    return int(number) if number.is_integer() else number


def canonical_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    raise ScriptContractError(f"'{value}' ist kein Wahrheitswert (ja/nein).")


def values_equal(left: Any, right: Any) -> bool:
    """Vergleicht zwei Anzeigenormalformen typunabhaengig genug fuer den Diff."""
    if is_empty(left) and is_empty(right):
        return True
    if isinstance(left, list) and isinstance(right, list):
        return sorted(map(str, left)) == sorted(map(str, right))
    if isinstance(left, int | float) and isinstance(right, int | float):
        return float(left) == float(right)
    return left == right


def display_value(value: Any) -> str:
    """Darstellung fuer Grid und Diff-Anzeige."""
    if is_empty(value):
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "ja" if value else "nein"
    return str(value)


__all__ = [
    "DATE_FORMAT",
    "canonical",
    "canonical_boolean",
    "canonical_date",
    "canonical_list",
    "canonical_number",
    "canonical_selection",
    "display_value",
    "is_empty",
    "values_equal",
]
