"""Tests des Datenbank-Lastnachweises (offline, kleine Datenmengen)."""

from __future__ import annotations

import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.bench.grid import fetch_rows
from app.bench.queries import equality_count_query, json_parameters, page_query
from app.bench.runner import Metric, percentile, run_benchmark, seed_database
from app.bench.synthetic import (
    FIELD_TYPES,
    field_keys,
    field_type,
    generate_assets,
    generate_values,
    json_path,
)
from app.db import create_session_factory, create_sqlite_engine, session_scope
from app.models import (
    AppUser,
    Base,
    Profile,
    Role,
    Workspace,
    WorkspaceAsset,
    WorkspaceChange,
)

FIELD_KEY = "custom:1"


def test_feldschluessel_und_typwechsel() -> None:
    keys = field_keys(4)
    assert keys == ["custom:1", "custom:2", "custom:3", "custom:4"]
    assert [field_type(index) for index in range(len(FIELD_TYPES))] == list(FIELD_TYPES)
    assert json_path(FIELD_KEY) == '$."custom:1"'


def test_generierte_assets_sind_deterministisch() -> None:
    keys = field_keys(6)
    first = list(generate_assets(3, keys, seed=7))
    second = list(generate_assets(3, keys, seed=7))
    assert first == second
    assert [file_id for file_id, _ in first] == [1, 2, 3]
    assert set(first[0][1]) == set(keys)


def test_werte_passen_zum_feldtyp() -> None:
    keys = field_keys(len(FIELD_TYPES))
    values = generate_values(1, keys, random.Random(1))
    assert isinstance(values["custom:1"], str)
    assert isinstance(values["custom:2"], int)
    assert isinstance(values["custom:4"], bool)
    assert isinstance(values["custom:6"], list)


def test_perzentil() -> None:
    assert percentile([], 0.95) == 0.0
    assert percentile([1.0], 0.95) == 1.0
    values = [float(number) for number in range(1, 101)]
    assert percentile(values, 0.95) == 95.0


def test_metrik_ziel() -> None:
    assert Metric("x", 1.0, "s").ok is None
    assert Metric("x", 1.0, "s", 2.0).ok is True
    assert Metric("x", 3.0, "s", 2.0).ok is False


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_sqlite_engine(tmp_path / "queries.sqlite3")
    Base.metadata.create_all(engine)
    try:
        with session_scope(create_session_factory(engine)) as session:
            yield session
    finally:
        engine.dispose()


def test_effektiver_wert_gewinnt_gegen_snapshot(session: Session) -> None:
    user = AppUser(username="u", password_hash="h", role=Role.SUPERUSER)
    profile = Profile(name="p", host="h", api_key_enc=b"x", api_key_hint="x")
    session.add_all([user, profile])
    session.flush()
    workspace = Workspace(owner_id=user.id, profile_id=profile.id, row_count=3)
    session.add(workspace)
    session.flush()
    workspace_id = workspace.id
    session.add_all(
        [
            WorkspaceAsset(
                workspace_id=workspace_id,
                file_id=1,
                values_json='{"custom:1": "alt-1"}',
                position=1,
            ),
            WorkspaceAsset(
                workspace_id=workspace_id,
                file_id=2,
                values_json='{"custom:1": "alt-2"}',
                position=2,
            ),
            WorkspaceAsset(
                workspace_id=workspace_id,
                file_id=3,
                values_json='{"custom:1": "alt-3"}',
                position=3,
            ),
        ]
    )
    session.add_all(
        [
            WorkspaceChange(
                workspace_id=workspace_id, file_id=1, field_key=FIELD_KEY, new_value="neu"
            ),
            WorkspaceChange(
                workspace_id=workspace_id, file_id=2, field_key=FIELD_KEY, new_value=None
            ),
        ]
    )
    session.flush()

    def count(value: str) -> int:
        return session.execute(
            equality_count_query(),
            {
                "workspace_id": workspace_id,
                "value": value,
                **json_parameters(FIELD_KEY),
            },
        ).scalar_one()

    assert count("neu") == 1
    assert count("alt-1") == 0  # ueberschrieben
    assert count("alt-2") == 0  # geleert, kein Rueckfall auf den Snapshot
    assert count("alt-3") == 1  # unveraendert


def test_seitenabruf_haelt_position(session: Session) -> None:
    user = AppUser(username="u", password_hash="h", role=Role.SUPERUSER)
    profile = Profile(name="p", host="h", api_key_enc=b"x", api_key_hint="x")
    session.add_all([user, profile])
    session.flush()
    workspace = Workspace(owner_id=user.id, profile_id=profile.id, row_count=3)
    session.add(workspace)
    session.flush()
    for position in (3, 1, 2):
        session.add(
            WorkspaceAsset(
                workspace_id=workspace.id,
                file_id=position,
                values_json="{}",
                position=position,
            )
        )
    session.flush()

    rows = list(
        session.execute(
            page_query(), {"workspace_id": workspace.id, "limit": 2, "offset": 0}
        ).mappings()
    )
    assert [row["file_id"] for row in rows] == [1, 2]


def test_blockabruf_filtert_und_sortiert(tmp_path: Path) -> None:
    db_path = tmp_path / "grid.sqlite3"
    workspace_id, keys = seed_database(db_path, assets=30, fields=4)
    engine = create_sqlite_engine(db_path)
    factory = create_session_factory(engine)
    try:
        rows, total = fetch_rows(factory, workspace_id, 0, 10, keys[1], False, "")
        assert total == 30
        assert len(rows) == 10
        numbers = [row[keys[1]] for row in rows]
        assert numbers == sorted(numbers)

        matched, count = fetch_rows(factory, workspace_id, 0, 10, keys[0], False, "Asset 7")
        assert count >= 1
        assert all("Asset 7" in str(row[keys[0]]) for row in matched)

        descending, _ = fetch_rows(factory, workspace_id, 0, 5, keys[1], True, "")
        values = [row[keys[1]] for row in descending]
        assert values == sorted(values, reverse=True)

        later, _ = fetch_rows(factory, workspace_id, 20, 10, keys[1], False, "")
        assert len(later) == 10
        assert {row["fileId"] for row in later}.isdisjoint({row["fileId"] for row in rows})
    finally:
        engine.dispose()


def test_kleiner_lastnachweis(tmp_path: Path) -> None:
    report = run_benchmark(
        db_path=tmp_path / "bench.sqlite3",
        assets=120,
        fields=4,
        audit_rows=50,
        concurrency_seconds=0.2,
    )
    assert report.assets == 120
    assert report.metric("snapshot_insert") is not None
    assert report.metric("first_page_100") is not None
    assert report.metric("filter_equality_text") is not None
    assert report.metric("concurrent_read_p95") is not None
    size_metric = report.metric("db_size_mb")
    assert size_metric is not None
    assert size_metric.value > 0
    assert report.failures == []
    assert Path(report.db_path).exists()
