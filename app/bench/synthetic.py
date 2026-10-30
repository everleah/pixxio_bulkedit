"""Deterministische synthetische Assets fuer den Lastnachweis."""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from typing import Any

FIELD_TYPES: tuple[str, ...] = (
    "text",
    "number",
    "date",
    "boolean",
    "selection",
    "multiselection",
)

SELECTION_OPTIONS: tuple[str, ...] = (
    "Kabel",
    "Dichtung",
    "Verpackung",
    "Sensoren",
    "Werkzeug",
)
DATE_START = datetime(2026, 1, 1, 12, 0, 0)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def field_keys(count: int) -> list[str]:
    return [f"custom:{index}" for index in range(1, count + 1)]


def field_type(index: int) -> str:
    return FIELD_TYPES[index % len(FIELD_TYPES)]


def json_path(field_key: str) -> str:
    """JSON-Pfad fuer SQLite ``json_extract`` inklusive Schluessel mit ``:``."""
    return f'$."{field_key}"'


def generate_values(
    file_id: int,
    keys: Sequence[str],
    rng: random.Random,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for index, key in enumerate(keys):
        kind = field_type(index)
        if kind == "text":
            values[key] = f"Asset {file_id} Text {rng.randrange(1000)}"
        elif kind == "number":
            values[key] = rng.randrange(0, 10_000)
        elif kind == "date":
            moment = DATE_START + timedelta(days=rng.randrange(0, 365))
            values[key] = moment.strftime(DATE_FORMAT)
        elif kind == "boolean":
            values[key] = bool(rng.getrandbits(1))
        elif kind == "selection":
            values[key] = SELECTION_OPTIONS[rng.randrange(len(SELECTION_OPTIONS))]
        else:
            start = rng.randrange(len(SELECTION_OPTIONS))
            values[key] = [
                SELECTION_OPTIONS[(start + offset) % len(SELECTION_OPTIONS)] for offset in range(2)
            ]
    return values


def generate_assets(
    count: int,
    keys: Sequence[str],
    seed: int = 20261030,
) -> Iterator[tuple[int, dict[str, Any]]]:
    rng = random.Random(seed)
    for number in range(1, count + 1):
        yield number, generate_values(number, keys, rng)
