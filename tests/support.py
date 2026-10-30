"""Hilfsfunktionen der Offline-Tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.settings import Settings


def make_settings(
    db_path: Path,
    master_key: str,
    storage_secret: str,
    **overrides: Any,
) -> Settings:
    """Baut Settings fuer Tests; Secrets werden als ``SecretStr`` uebergeben."""
    return Settings(
        db_path=db_path,
        master_key=SecretStr(master_key),
        storage_secret=SecretStr(storage_secret),
        **overrides,
    )
