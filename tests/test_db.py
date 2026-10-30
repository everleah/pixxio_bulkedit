"""Tests der Datenbankschicht und der Migrationen."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import create_engine_for, create_session_factory, run_migrations, session_scope
from app.models import AppUser, Base, WorkspaceAsset
from tests.support import make_settings


class BoomError(Exception):
    pass


def test_sqlite_pragmas_sind_aktiv(session: Session) -> None:
    assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1
    journal_mode = session.execute(text("PRAGMA journal_mode")).scalar()
    assert str(journal_mode).lower() == "wal"


def test_fremdschluessel_werden_erzwungen(session: Session) -> None:
    session.add(WorkspaceAsset(workspace_id=999, file_id=1, values_json="{}"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_session_scope_rollt_bei_fehler_zurueck(engine: Engine) -> None:
    factory = create_session_factory(engine)
    with pytest.raises(BoomError):
        with session_scope(factory) as session:
            session.add(AppUser(username="abgebrochen", password_hash="hash"))
            raise BoomError

    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 0


def test_migrationen_passen_zu_modellen(
    tmp_path: Path, master_key: str, storage_secret: str
) -> None:
    settings = make_settings(
        db_path=tmp_path / "migriert.sqlite3",
        master_key=master_key,
        storage_secret=storage_secret,
    )
    run_migrations(settings)
    engine = create_engine_for(settings)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
