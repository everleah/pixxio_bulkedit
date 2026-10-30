"""Kommandozeile fuer Einrichtung, Superuser und Serverstart."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Sequence

from dotenv import dotenv_values
from pydantic import ValidationError
from sqlalchemy import select

from app.auth import (
    AuthError,
    create_user,
    normalize_username,
    reset_password,
    set_active,
    set_role,
)
from app.crypto import SecretBox, generate_master_key
from app.db import create_engine_for, create_session_factory, run_migrations, session_scope
from app.models import AppUser, Profile, Role
from app.profiles import ProfileData, ProfileError, create_profile, update_profile
from app.runs import HISTORY_RETENTION_DAYS
from app.scripts.service import ensure_templates
from app.settings import Settings, get_settings

EXIT_CONFIG_ERROR = 2
EXIT_FAILURE = 1


class CliError(Exception):
    """Fachlicher Abbruch eines Kommandos."""


def _require_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        details = "; ".join(str(error["msg"]) for error in exc.errors())
        raise CliError(
            "Konfiguration unvollstaendig. BULKEDIT_DB_PATH, BULKEDIT_MASTER_KEY und "
            f"BULKEDIT_STORAGE_SECRET muessen gesetzt sein ({details})."
        ) from exc


def _open_session_factory(settings: Settings):
    engine = create_engine_for(settings)
    run_migrations(settings)
    return create_session_factory(engine)


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        if not password:
            raise CliError("Auf stdin wurde kein Passwort uebergeben.")
        return password
    password = getpass.getpass("Passwort: ")
    repeated = getpass.getpass("Passwort wiederholen: ")
    if password != repeated:
        raise CliError("Die Passwoerter stimmen nicht ueberein.")
    return password


def command_init_db(_args: argparse.Namespace) -> int:
    settings = _require_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(settings)
    factory = create_session_factory(create_engine_for(settings))
    with session_scope(factory) as session:
        created = ensure_templates(session)
    print(f"Datenbank bereit: {settings.db_path}")
    if created:
        print(f"{created} Script-Vorlagen angelegt.")
    return 0


def command_generate_master_key(_args: argparse.Namespace) -> int:
    print(generate_master_key())
    return 0


def command_create_superuser(args: argparse.Namespace) -> int:
    settings = _require_settings()
    factory = _open_session_factory(settings)
    password = _read_password(args.password_stdin)
    username = normalize_username(args.username)
    with session_scope(factory) as session:
        existing = session.scalar(select(AppUser).where(AppUser.username == username))
        try:
            if existing is None:
                create_user(
                    session,
                    username=username,
                    password=password,
                    role=Role.SUPERUSER,
                )
                print(f"Superuser {username!r} angelegt.")
            else:
                reset_password(session, existing, password)
                if existing.role is not Role.SUPERUSER:
                    set_role(session, existing, Role.SUPERUSER)
                if not existing.is_active:
                    set_active(session, existing, True)
                print(f"Superuser {username!r} aktualisiert.")
        except AuthError as exc:
            raise CliError(str(exc)) from exc
    return 0


def _read_api_key(env_name: str) -> str:
    """Liest den API-Key aus der Umgebung oder aus ``.env``.

    Der Key wird nie als Argument uebergeben, damit er nicht in der Shell-Historie
    oder in Protokollen landet.
    """
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    env_file = dotenv_values(".env")
    fallback = env_file.get(env_name) or ""
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    raise CliError(f"Umgebungsvariable {env_name} ist nicht gesetzt und steht auch nicht in .env.")


def command_create_profile(args: argparse.Namespace) -> int:
    settings = _require_settings()
    factory = _open_session_factory(settings)
    api_key = _read_api_key(args.api_key_env)
    data = ProfileData(
        name=args.name,
        host=args.host,
        api_key=api_key,
        max_retries=args.max_retries,
        max_rows=args.max_rows,
        allow_write=not args.read_only,
        is_active=not args.inactive,
    )
    secret_box = SecretBox.from_master_key(settings.master_key)
    with session_scope(factory) as session:
        existing = session.scalar(select(Profile).where(Profile.name == data.name.strip()))
        try:
            if existing is None:
                create_profile(session, secret_box, data, actor=None)
                print(f"Profil {data.name!r} angelegt.")
            else:
                update_profile(session, secret_box, existing, data, actor=None)
                print(f"Profil {data.name!r} aktualisiert.")
        except ProfileError as exc:
            raise CliError(str(exc)) from exc
    return 0


def command_purge_history(args: argparse.Namespace) -> int:
    from app.runs import purge_change_values
    from app.xlsx import purge_exports

    settings = _require_settings()
    factory = _open_session_factory(settings)
    with session_scope(factory) as session:
        removed = purge_change_values(session, days=args.days)
        exports = purge_exports(session)
    print(f"{removed} Feldwerte aus Laeufen aelter als {args.days} Tage entfernt.")
    print(f"{exports} Export-Snapshots aelter als die Aufbewahrungsfrist entfernt.")
    return 0


def command_serve(_args: argparse.Namespace) -> int:
    from app.main import main as run_server

    run_server()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app", description="pixx.io Bulk-Editor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Datenbank anlegen und migrieren")
    init_db.set_defaults(handler=command_init_db)

    generate_key = subparsers.add_parser(
        "generate-master-key", help="Neuen Fernet-Master-Key ausgeben"
    )
    generate_key.set_defaults(handler=command_generate_master_key)

    create_superuser = subparsers.add_parser(
        "create-superuser", help="Superuser anlegen oder Passwort zuruecksetzen"
    )
    create_superuser.add_argument("--username", required=True)
    create_superuser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Passwort aus der ersten stdin-Zeile lesen statt interaktiv abzufragen",
    )
    create_superuser.set_defaults(handler=command_create_superuser)

    create_profile = subparsers.add_parser(
        "create-profile", help="pixx.io-Profil anlegen oder aktualisieren"
    )
    create_profile.add_argument("--name", required=True, help="Profilname, z. B. 'test'")
    create_profile.add_argument(
        "--host", required=True, help="Host ohne Protokoll, z. B. 'firma.px.media'"
    )
    create_profile.add_argument(
        "--api-key-env",
        required=True,
        help="Name der Umgebungsvariablen mit dem API-Key (Key nie als Argument uebergeben)",
    )
    create_profile.add_argument("--max-retries", type=int, default=3)
    create_profile.add_argument("--max-rows", type=int, default=5_000)
    create_profile.add_argument(
        "--read-only", action="store_true", help="Schreibzugriff fuer dieses Profil sperren"
    )
    create_profile.add_argument("--inactive", action="store_true", help="Profil deaktivieren")
    create_profile.set_defaults(handler=command_create_profile)

    serve = subparsers.add_parser("serve", help="Weboberflaeche starten")
    serve.set_defaults(handler=command_serve)

    purge = subparsers.add_parser(
        "purge-history", help="Feldwerte alter Laeufe entfernen (Laufuebersicht bleibt)"
    )
    purge.add_argument(
        "--days",
        type=int,
        default=HISTORY_RETENTION_DAYS,
        help="Aufbewahrung in Tagen (Standard: %(default)s)",
    )
    purge.set_defaults(handler=command_purge_history)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except CliError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except ValidationError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
