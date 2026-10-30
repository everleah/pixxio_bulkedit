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
from app.crypto import SecretBox, api_key_hint, assert_valid_master_key
from app.db import create_engine_for, create_session_factory, session_scope
from app.models import AppUser, Profile, Role
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


def test_create_profile_legt_an_und_rotiert_key(
    env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PROFILE_KEY", "erster-api-key-mit-32-zeichen-laenge")
    args = [
        "create-profile",
        "--name",
        "test",
        "--host",
        "Demo.PX.Media",
        "--api-key-env",
        "PROFILE_KEY",
    ]
    assert main(args) == 0
    assert "angelegt" in capsys.readouterr().out

    monkeypatch.setenv("PROFILE_KEY", "zweiter-api-key-mit-32-zeichen-laenge")
    assert main(args) == 0
    assert "aktualisiert" in capsys.readouterr().out

    settings = get_settings()
    box = SecretBox.from_master_key(settings.master_key)
    engine = create_engine_for(settings)
    try:
        with session_scope(create_session_factory(engine)) as session:
            profile = session.scalar(select(Profile).where(Profile.name == "test"))
            assert profile is not None
            assert profile.host == "demo.px.media"
            assert profile.allow_write is True
            assert profile.is_active is True
            assert (
                profile.api_key_hint == f"{api_key_hint('zweiter-api-key-mit-32-zeichen-laenge')}"
            )
            assert box.decrypt(profile.api_key_enc) == "zweiter-api-key-mit-32-zeichen-laenge"
    finally:
        engine.dispose()


def test_create_profile_read_only_flag(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PROFILE_KEY", "api-key-mit-mindestens-32-zeichen-laenge")
    args = [
        "create-profile",
        "--name",
        "lesend",
        "--host",
        "demo.px.media",
        "--api-key-env",
        "PROFILE_KEY",
        "--read-only",
        "--inactive",
    ]
    assert main(args) == 0
    capsys.readouterr()

    settings = get_settings()
    engine = create_engine_for(settings)
    try:
        with session_scope(create_session_factory(engine)) as session:
            profile = session.scalar(select(Profile).where(Profile.name == "lesend"))
            assert profile is not None
            assert profile.allow_write is False
            assert profile.is_active is False
    finally:
        engine.dispose()


def test_create_profile_ohne_key_env_bricht_ab(
    env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PROFILE_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    args = [
        "create-profile",
        "--name",
        "x",
        "--host",
        "demo.px.media",
        "--api-key-env",
        "PROFILE_KEY",
    ]
    assert main(args) == 1
    assert "PROFILE_KEY" in capsys.readouterr().err


def test_fehlende_konfiguration_bricht_ab(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # In ein leeres Verzeichnis wechseln, damit ein vorhandene Projekt-.env nicht greift.
    monkeypatch.chdir(tmp_path)
    for name in ("BULKEDIT_DB_PATH", "BULKEDIT_MASTER_KEY", "BULKEDIT_STORAGE_SECRET"):
        monkeypatch.delenv(name, raising=False)
    clear_settings_cache()
    try:
        assert main(["init-db"]) == 1
        assert "Konfiguration unvollstaendig" in capsys.readouterr().err
    finally:
        clear_settings_cache()
