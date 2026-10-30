"""Tests der Kommandozeile."""

from __future__ import annotations

import io
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.cli import main
from app.crypto import assert_valid_master_key
from app.db import create_engine_for, create_session_factory, session_scope
from app.models import AppUser, Role
from app.settings import clear_settings_cache, get_settings

PASSWORD = "ein-sehr-langes-passwort"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    db_path = tmp_path / "cli.sqlite3"
    monkeypatch.setenv("BULKEDIT_DB_PATH", str(db_path))
    monkeypatch.setenv("BULKEDIT_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("BULKEDIT_STORAGE_SECRET", "cli-storage-secret-0123456789")
    clear_settings_cache()
    yield db_path
    clear_settings_cache()


def test_generate_master_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate-master-key"]) == 0
    assert_valid_master_key(capsys.readouterr().out.strip())


def test_init_db_legt_datenbank_an(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init-db"]) == 0
    assert env.exists()
    assert "Datenbank bereit" in capsys.readouterr().out


def test_create_superuser_ist_wiederholbar(
    env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{PASSWORD}\n"))
    assert main(["create-superuser", "--username", " Admin ", "--password-stdin"]) == 0
    assert "angelegt" in capsys.readouterr().out

    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{PASSWORD}\n"))
    assert main(["create-superuser", "--username", "admin", "--password-stdin"]) == 0
    assert "aktualisiert" in capsys.readouterr().out

    settings = get_settings()
    engine = create_engine_for(settings)
    try:
        with session_scope(create_session_factory(engine)) as session:
            user = session.scalar(select(AppUser).where(AppUser.username == "admin"))
    finally:
        engine.dispose()
    assert user is not None
    assert user.role is Role.SUPERUSER
    assert user.is_active


def test_fehlende_konfiguration_bricht_ab(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("BULKEDIT_DB_PATH", "BULKEDIT_MASTER_KEY", "BULKEDIT_STORAGE_SECRET"):
        monkeypatch.delenv(name, raising=False)
    clear_settings_cache()
    try:
        assert main(["init-db"]) == 1
        assert "Konfiguration unvollstaendig" in capsys.readouterr().err
    finally:
        clear_settings_cache()
