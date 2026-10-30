"""Kommandozeile fuer Einrichtung, Superuser und Serverstart."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence

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
from app.crypto import generate_master_key
from app.db import create_engine_for, create_session_factory, run_migrations, session_scope
from app.models import AppUser, Role
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
    print(f"Datenbank bereit: {settings.db_path}")
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

    serve = subparsers.add_parser("serve", help="Weboberflaeche starten")
    serve.set_defaults(handler=command_serve)
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
