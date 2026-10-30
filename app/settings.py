"""Laufzeitkonfiguration aus ``BULKEDIT_*``-Umgebungsvariablen.

Alle Pflichtwerte haben bewusst keinen Default, damit weder ein Standardpasswort
noch ein Standardsecret entsteht (Umsetzungsplan Abschnitt 7).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.crypto import assert_valid_master_key

STORAGE_SECRET_MIN_CHARS = 16


class Settings(BaseSettings):
    """Unveraenderliche Laufzeitkonfiguration der Anwendung."""

    model_config = SettingsConfigDict(
        env_prefix="BULKEDIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        validate_default=True,
    )

    db_path: Path
    master_key: SecretStr
    storage_secret: SecretStr

    session_timeout_minutes: int = Field(default=60, ge=5, le=1440)
    login_max_attempts: int = Field(default=5, ge=1, le=100)
    login_window_seconds: int = Field(default=300, ge=1, le=86_400)
    script_timeout_seconds: int = Field(default=60, ge=1, le=600)
    script_max_output_chars: int = Field(default=20_000, ge=1_000, le=1_000_000)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080, ge=1, le=65_535)

    @field_validator("db_path")
    @classmethod
    def _resolve_db_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("master_key")
    @classmethod
    def _check_master_key(cls, value: SecretStr) -> SecretStr:
        assert_valid_master_key(value.get_secret_value())
        return value

    @field_validator("storage_secret")
    @classmethod
    def _check_storage_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < STORAGE_SECRET_MIN_CHARS:
            raise ValueError(
                f"BULKEDIT_STORAGE_SECRET muss mindestens {STORAGE_SECRET_MIN_CHARS} Zeichen haben"
            )
        return value

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Liest die Konfiguration einmalig aus der Umgebung."""
    # Pyright erkennt die Env-Beladung von pydantic-settings nicht.
    return Settings()  # pyright: ignore[reportCallIssue]


def clear_settings_cache() -> None:
    """Verwirft die zwischengespeicherte Konfiguration (Tests, CLI)."""
    get_settings.cache_clear()
