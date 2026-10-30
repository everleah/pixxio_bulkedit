"""Tests der Deployment-Artefakte (Docker, Compose, Sicherung, Healthcheck)."""

from __future__ import annotations

from pathlib import Path

from app import __version__
from app.settings import Settings
from tests.support import make_settings

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("deploy-vps.sh", "backup.sh", "restore.sh")


def test_shell_skripte_haben_lf() -> None:
    for name in SCRIPTS:
        data = (ROOT / name).read_bytes()
        assert data, name
        assert b"\r\n" not in data, f"{name} enthaelt CRLF"
        assert data.startswith(b"#!/bin/bash"), name


def test_gitattributes_pinnt_zeilenenden() -> None:
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in text


def test_dockerfile_baut_und_startet_die_anwendung() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.14-slim" in text
    assert "pip install --no-cache-dir -r requirements.txt" in text
    for copy in ("alembic.ini", "migrations/", "app/"):
        assert f"COPY {copy}" in text
    assert "HEALTHCHECK" in text and "/health" in text
    assert 'CMD ["python", "-m", "app", "serve"]' in text
    assert "EXPOSE 8080" in text


def test_dockerignore_haelt_secrets_und_daten_heraus() -> None:
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for entry in (".venv/", "data/", ".env", "tests/", "backups/"):
        assert entry in text


def test_compose_nutzt_registry_traefik_und_grenzen() -> None:
    text = (ROOT / "docker-compose.vps.yml").read_text(encoding="utf-8")
    assert "git.claudiapps.de/hoerl-im/pixxio_bulkedit:${BULKEDIT_TAG:-latest}" in text
    assert "BULKEDIT_DB_PATH: /data/bulkedit.sqlite3" in text
    assert "BULKEDIT_MASTER_KEY" in text and "BULKEDIT_STORAGE_SECRET" in text
    assert "restart: unless-stopped" in text
    assert "stop_grace_period" in text
    assert 'max-size: "10m"' in text
    assert (
        "traefik.http.routers.bulkedit.rule=Host(`${BULKEDIT_HOST:-bulkedit.vcs1.him-tools.de}`)"
        in text
    )
    assert "traefik.http.services.bulkedit.loadbalancer.server.port=8080" in text
    assert "bulkedit_data:/data" in text
    assert "external: true" in text


def test_env_vorlage_enthaelt_pflichtwerte() -> None:
    text = (ROOT / ".env.vps.example").read_text(encoding="utf-8")
    for key in ("BULKEDIT_TAG", "BULKEDIT_HOST", "TRAEFIK_NETWORK", "BULKEDIT_MASTER_KEY"):
        assert key in text
    assert "change-me" in text
    assert "BULKEDIT_HOST=bulkedit.vcs1.him-tools.de" in text
    assert "TRAEFIK_NETWORK=him-net" in text


def test_sicherung_und_wiederherstellung_nutzen_konsistente_mittel() -> None:
    backup = (ROOT / "backup.sh").read_text(encoding="utf-8")
    assert "source.backup(target)" in backup
    assert "integrity_check" in backup
    assert "openssl enc -aes-256-cbc -pbkdf2" in backup
    assert "BACKUP_KEY_FILE" in backup

    restore = (ROOT / "restore.sh").read_text(encoding="utf-8")
    assert "openssl enc -d -aes-256-cbc -pbkdf2" in restore
    assert "PRAGMA integrity_check" in restore
    assert "--check" in restore
    assert "docker inspect --format '{{.State.Health.Status}}'" in restore


def test_deploy_skript_prueft_healthcheck_und_erinnert_an_abgleich() -> None:
    text = (ROOT / "deploy-vps.sh").read_text(encoding="utf-8")
    assert "docker login git.claudiapps.de" in text
    assert 'compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config' in text
    assert "--backup" in text
    assert "Status abgleichen" in text


def test_host_und_port_sind_konfigurierbar(tmp_path: Path, master_key: str) -> None:
    settings = make_settings(tmp_path / "db.sqlite3", master_key, "x" * 32)
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    custom = Settings(
        db_path=tmp_path / "db.sqlite3",
        master_key=settings.master_key,
        storage_secret=settings.storage_secret,
        host="127.0.0.1",
        port=9000,
    )
    assert custom.host == "127.0.0.1"
    assert custom.port == 9000


def test_healthcheck_und_version_sind_verdrahtet() -> None:
    text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/health")' in text
    assert "host=settings.host" in text and "port=settings.port" in text
    assert "on_shutdown" in text
    assert __version__
