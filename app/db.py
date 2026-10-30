"""Engine, Session-Factory und Migrationen der SQLite-Datenbank."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"

SessionFactory = sessionmaker[Session]


def _apply_sqlite_pragmas(dbapi_connection: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA busy_timeout = 15000")
    finally:
        cursor.close()


def create_sqlite_engine(db_path: Path) -> Engine:
    """SQLite-Engine mit Fremdschluesseln, WAL-Journal und Wartezeit."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15.0},
        future=True,
    )
    event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def create_engine_for(settings: Settings) -> Engine:
    """Erzeugt eine Engine fuer den konfigurierten Datenbankpfad."""
    return create_sqlite_engine(settings.db_path)


def create_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: SessionFactory) -> Iterator[Session]:
    """Session mit Commit bei Erfolg und Rollback bei Fehlern."""
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations(settings: Settings) -> None:
    """Bringt die Datenbank auf den neuesten Alembic-Stand."""
    command.upgrade(alembic_config(settings), "head")
