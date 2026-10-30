"""Lokales Ledger der selbst angelegten Test-Assets.

Nur Assets aus diesem Ledger duerfen beschrieben werden. Ein unlesbares Ledger
wird bewusst nicht stillschweigend zurueckgesetzt: das wuerde die Schutzgrenze
aushebeln.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.spike.errors import LedgerError

LEDGER_VERSION = 1


@dataclass(frozen=True)
class LedgerEntry:
    asset_id: int
    file_name: str
    created_at: str


class Ledger:
    """Dauerhafte Liste der vom Spike erzeugten Assets."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"Ledger {self.path} ist nicht lesbar: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("version") != LEDGER_VERSION:
            raise LedgerError(
                f"Ledger {self.path} hat ein unbekanntes Format; bitte manuell pruefen."
            )
        raw_entries = payload.get("assets")
        if not isinstance(raw_entries, list):
            raise LedgerError(f"Ledger {self.path} enthaelt keine Liste 'assets'.")
        entries: list[LedgerEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict) or "asset_id" not in raw:
                raise LedgerError(f"Ledger {self.path} enthaelt einen ungueltigen Eintrag.")
            entries.append(
                LedgerEntry(
                    asset_id=int(raw["asset_id"]),
                    file_name=str(raw.get("file_name", "")),
                    created_at=str(raw.get("created_at", "")),
                )
            )
        return entries

    def ids(self) -> set[int]:
        return {entry.asset_id for entry in self.load()}

    def add(self, entry: LedgerEntry) -> None:
        entries = self.load()
        if any(existing.asset_id == entry.asset_id for existing in entries):
            return
        entries.append(entry)
        self._write(entries)

    def remove(self, asset_id: int) -> None:
        entries = [entry for entry in self.load() if entry.asset_id != asset_id]
        self._write(entries)

    def _write(self, entries: list[LedgerEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": LEDGER_VERSION,
            "assets": [asdict(entry) for entry in entries],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
