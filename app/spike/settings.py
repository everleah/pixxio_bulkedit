"""Konfiguration des API-Spikes aus ``PXTEST_*``-Umgebungsvariablen.

Bewusst getrennt von :class:`app.settings.Settings`: diese Zugangsdaten gehoeren nur
zu den Machbarkeitspruefungen, nicht zur Anwendung.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SpikeSettings(BaseSettings):
    """Zugang zum Testsystem fuer die Phase-1-Pruefungen."""

    model_config = SettingsConfigDict(
        env_prefix="PXTEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    host: str
    api_key: SecretStr
    collection_id: int = Field(gt=0)
    # Nur auf einem Testsystem duerfen Testdaten angelegt und geloescht werden.
    is_dev: bool = False
    ledger_path: Path = Path("data") / "spike" / "ledger.json"

    @field_validator("host")
    @classmethod
    def _strip_host(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("PXTEST_HOST darf nicht leer sein")
        return cleaned

    @field_validator("ledger_path")
    @classmethod
    def _resolve_ledger_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()


def get_spike_settings() -> SpikeSettings:
    # Pyright erkennt die Env-Beladung von pydantic-settings nicht.
    return SpikeSettings()  # pyright: ignore[reportCallIssue]
