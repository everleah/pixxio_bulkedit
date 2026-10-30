"""Tests der Laufzeitkonfiguration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.settings import Settings, clear_settings_cache, get_settings
from tests.support import make_settings

DEFAULT_DB_PATH = Path("data") / "bulkedit.sqlite3"


def test_alle_pflichtwerte_fehlen_verhindern_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("BULKEDIT_DB_PATH", "BULKEDIT_MASTER_KEY", "BULKEDIT_STORAGE_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    settings_class: Any = Settings
    with pytest.raises(ValidationError) as excinfo:
        settings_class()
    missing = {str(error["loc"][0]) for error in excinfo.value.errors()}
    assert {"db_path", "master_key", "storage_secret"} <= missing


def test_ungueltiger_master_key_wird_abgelehnt(storage_secret: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            db_path=DEFAULT_DB_PATH,
            master_key="kein-gueltiger-fernet-key",
            storage_secret=storage_secret,
        )


def test_kurzes_storage_secret_wird_abgelehnt(master_key: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(db_path=DEFAULT_DB_PATH, master_key=master_key, storage_secret="zu-kurz")


def test_db_pfad_wird_absolut_aufgeloest(master_key: str, storage_secret: str) -> None:
    settings = make_settings(
        db_path=DEFAULT_DB_PATH, master_key=master_key, storage_secret=storage_secret
    )
    assert settings.db_path.is_absolute()
    assert settings.database_url == f"sqlite:///{settings.db_path.as_posix()}"


def test_secrets_erscheinen_nicht_im_repr(master_key: str, storage_secret: str) -> None:
    settings = make_settings(
        db_path=DEFAULT_DB_PATH, master_key=master_key, storage_secret=storage_secret
    )
    assert master_key not in repr(settings)
    assert storage_secret not in repr(settings)


def test_get_settings_liest_umgebung_und_cached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    master_key: str,
    storage_secret: str,
) -> None:
    monkeypatch.setenv("BULKEDIT_DB_PATH", str(tmp_path / "env.sqlite3"))
    monkeypatch.setenv("BULKEDIT_MASTER_KEY", master_key)
    monkeypatch.setenv("BULKEDIT_STORAGE_SECRET", storage_secret)
    clear_settings_cache()
    try:
        first = get_settings()
        assert first.db_path == (tmp_path / "env.sqlite3").resolve()
        assert get_settings() is first
    finally:
        clear_settings_cache()


def test_grenzen_werden_validiert(master_key: str, storage_secret: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            db_path=DEFAULT_DB_PATH,
            master_key=master_key,
            storage_secret=storage_secret,
            session_timeout_minutes=1,
        )
