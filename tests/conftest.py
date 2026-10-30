"""Gemeinsame Fixtures der Offline-Tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import create_engine_for, create_session_factory, session_scope
from app.models import Base
from app.settings import Settings
from tests.support import make_settings

TEST_STORAGE_SECRET = "test-storage-secret-0123456789"


@pytest.fixture(scope="session")
def master_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture(scope="session")
def storage_secret() -> str:
    return TEST_STORAGE_SECRET


@pytest.fixture
def settings(tmp_path: Path, master_key: str) -> Settings:
    return make_settings(
        db_path=tmp_path / "bulkedit.sqlite3",
        master_key=master_key,
        storage_secret=TEST_STORAGE_SECRET,
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    engine = create_engine_for(settings)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with session_scope(create_session_factory(engine)) as session:
        yield session
