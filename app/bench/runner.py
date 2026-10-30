"""Datenbank-Lastnachweis fuer Phase 1.6.3.

Misst Snapshot-Aufbau, effektive Abfragen, Nebenlaeufigkeit und Wachstum auf einer
echten SQLite-Datei mit den Produktionsmodellen.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, insert, select
from sqlalchemy.sql.elements import TextClause

from app.bench.queries import (
    equality_count_query,
    json_parameters,
    page_query,
    range_sorted_query,
)
from app.bench.synthetic import field_keys, generate_assets
from app.db import SessionFactory, create_session_factory, create_sqlite_engine, session_scope
from app.models import (
    AppUser,
    Base,
    ChangeLog,
    ChangeStatus,
    Profile,
    Role,
    Run,
    RunKind,
    RunMode,
    RunStatus,
    Workspace,
    WorkspaceAsset,
    WorkspaceChange,
    WorkspaceStatus,
)

FIRST_PAGE_TARGET_SECONDS = 5.0
QUERY_TARGET_SECONDS = 5.0
CONCURRENT_TARGET_SECONDS = 5.0
CHUNK_SIZE = 5_000
CONCURRENCY_SECONDS = 2.0
AUDIT_ROWS = 50_000
CONCURRENT_FIELD = "probe:concurrent"
CHANGE_EVERY = 50


@dataclass(frozen=True)
class Metric:
    """Ein Messwert mit optionalem Zielwert."""

    name: str
    value: float
    unit: str
    target: float | None = None

    @property
    def ok(self) -> bool | None:
        return None if self.target is None else self.value <= self.target


@dataclass
class BenchmarkReport:
    assets: int
    fields: int
    db_path: str
    metrics: list[Metric] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def metric(self, name: str) -> Metric | None:
        return next((item for item in self.metrics if item.name == name), None)

    @property
    def failures(self) -> list[Metric]:
        return [item for item in self.metrics if item.ok is False]


def percentile(values: Sequence[float], fraction: float) -> float:
    """Einfaches Perzentil ohne Zusatzabhaengigkeit."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, round(fraction * len(ordered)) - 1))
    return ordered[position]


def existing_workspace_id(db_path: Path) -> int | None:
    if not db_path.exists():
        return None
    engine = create_sqlite_engine(db_path)
    try:
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            return session.scalar(select(Workspace.id).order_by(Workspace.id).limit(1))
    finally:
        engine.dispose()


def seed_database(
    db_path: Path,
    *,
    assets: int,
    fields: int,
    seed: int = 20261030,
) -> tuple[int, list[str]]:
    """Legt eine Benchmark-Datenbank mit Snapshot an und liefert Workspace und Felder."""
    engine = create_sqlite_engine(db_path)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    keys = field_keys(fields)
    try:
        workspace_id = _create_workspace(factory, assets)
        _load_snapshot(engine, workspace_id, keys, assets, seed)
    finally:
        engine.dispose()
    return workspace_id, keys


def _create_workspace(factory: SessionFactory, assets: int) -> int:
    with session_scope(factory) as session:
        user = AppUser(username="bench", password_hash="x", role=Role.SUPERUSER)
        profile = Profile(
            name="bench",
            host="bench.invalid",
            api_key_enc=b"x",
            api_key_hint="x",
        )
        session.add_all([user, profile])
        session.flush()
        workspace = Workspace(
            name="bench",
            owner_id=user.id,
            profile_id=profile.id,
            status=WorkspaceStatus.READY,
            row_count=assets,
        )
        session.add(workspace)
        session.flush()
        return workspace.id


def _load_snapshot(
    engine: Engine,
    workspace_id: int,
    keys: Sequence[str],
    assets: int,
    seed: int,
) -> int:
    statement = insert(WorkspaceAsset)
    rows: list[dict[str, Any]] = []
    total = 0
    for position, (file_id, values) in enumerate(generate_assets(assets, keys, seed=seed), start=1):
        rows.append(
            {
                "workspace_id": workspace_id,
                "file_id": file_id,
                "modify_date": "2026-10-30 12:00:00",
                "values_json": json.dumps(values, ensure_ascii=False),
                "position": position,
            }
        )
        if len(rows) >= CHUNK_SIZE:
            with engine.begin() as connection:
                connection.execute(statement, rows)
            total += len(rows)
            rows.clear()
    if rows:
        with engine.begin() as connection:
            connection.execute(statement, rows)
        total += len(rows)
    return total


def _apply_changes(engine: Engine, workspace_id: int, assets: int, keys: Sequence[str]) -> int:
    """Setzt ausstehende Aenderungen auf jede 50. Datei."""
    statement = insert(WorkspaceChange)
    rows: list[dict[str, Any]] = []
    for file_id in range(1, assets + 1, CHANGE_EVERY):
        field_key = keys[0] if (file_id // CHANGE_EVERY) % 2 else keys[1]
        value = f"geaendert-{file_id}" if field_key == keys[0] else "4711"
        rows.append(
            {
                "workspace_id": workspace_id,
                "file_id": file_id,
                "field_key": field_key,
                "old_value": None,
                "new_value": value,
            }
        )
    with engine.begin() as connection:
        connection.execute(statement, rows)
    return len(rows)


def _page(factory: SessionFactory, workspace_id: int, limit: int, offset: int) -> list[Any]:
    with factory() as session:
        result = session.execute(
            page_query(),
            {"workspace_id": workspace_id, "limit": limit, "offset": offset},
        )
        return list(result.mappings())


def _timed_rows(
    factory: SessionFactory, statement: TextClause, params: dict[str, Any]
) -> tuple[float, list[Any]]:
    with factory() as session:
        started = time.perf_counter()
        rows = list(session.execute(statement, params).mappings())
        return time.perf_counter() - started, rows


def _timed_scalar(
    factory: SessionFactory, statement: TextClause, params: dict[str, Any]
) -> tuple[float, Any]:
    with factory() as session:
        started = time.perf_counter()
        value = session.execute(statement, params).scalar()
        return time.perf_counter() - started, value


def _concurrent_reads(
    db_path: Path,
    workspace_id: int,
    keys: Sequence[str],
    assets: int,
    duration: float,
) -> tuple[list[float], int, list[str]]:
    """Liest waehrend ein zweiter Prozessschritt Aenderungen schreibt."""
    reader_engine = create_sqlite_engine(db_path)
    writer_engine = create_sqlite_engine(db_path)
    reader_factory = create_session_factory(reader_engine)
    writer_factory = create_session_factory(writer_engine)
    stop = threading.Event()
    written = 0
    errors: list[str] = []
    params = {
        "workspace_id": workspace_id,
        "value": "nicht-vorhanden",
        **json_parameters(keys[0]),
    }

    def writer() -> None:
        nonlocal written
        file_id = 1
        while not stop.is_set() and file_id <= assets:
            try:
                with session_scope(writer_factory) as session:
                    session.add(
                        WorkspaceChange(
                            workspace_id=workspace_id,
                            file_id=file_id,
                            field_key=CONCURRENT_FIELD,
                            new_value=f"x{file_id}",
                        )
                    )
                written += 1
            except Exception as exc:  # noqa: BLE001 - Diagnose im Lastnachweis
                errors.append(f"{type(exc).__name__}: {exc}")
                return
            file_id += 1

    thread = threading.Thread(target=writer, name="bench-writer", daemon=True)
    latencies: list[float] = []
    thread.start()
    deadline = time.perf_counter() + duration
    try:
        while time.perf_counter() < deadline:
            duration_read, _ = _timed_scalar(reader_factory, equality_count_query(), params)
            latencies.append(duration_read)
    finally:
        stop.set()
        thread.join(timeout=10)
        reader_engine.dispose()
        writer_engine.dispose()
    return latencies, written, errors


def _audit_inserts(
    engine: Engine,
    factory: SessionFactory,
    workspace_id: int,
    keys: Sequence[str],
    rows_count: int,
) -> float:
    with session_scope(factory) as session:
        run = Run(
            kind=RunKind.WRITE,
            mode=RunMode.DRY_RUN,
            status=RunStatus.RUNNING,
            workspace_id=workspace_id,
        )
        session.add(run)
        session.flush()
        run_id = run.id

    rows = [
        {
            "run_id": run_id,
            "file_id": index,
            "field_key": keys[0],
            "status": ChangeStatus.PLANNED,
        }
        for index in range(1, rows_count + 1)
    ]
    started = time.perf_counter()
    with engine.begin() as connection:
        connection.execute(insert(ChangeLog), rows)
    return time.perf_counter() - started


def _database_size(db_path: Path) -> int:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{db_path}{suffix}")
        if candidate.exists():
            total += candidate.stat().st_size
    return total


def run_benchmark(
    *,
    db_path: Path,
    assets: int = 50_000,
    fields: int = 30,
    seed: int = 20261030,
    audit_rows: int = AUDIT_ROWS,
    concurrency_seconds: float = CONCURRENCY_SECONDS,
) -> BenchmarkReport:
    """Fuehrt alle Messungen aus und liefert den Bericht."""
    if db_path.exists():
        db_path.unlink()
    engine = create_sqlite_engine(db_path)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    keys = field_keys(fields)
    report = BenchmarkReport(assets=assets, fields=fields, db_path=str(db_path))

    try:
        workspace_id = _create_workspace(factory, assets)

        started = time.perf_counter()
        written = _load_snapshot(engine, workspace_id, keys, assets, seed)
        duration = time.perf_counter() - started
        report.metrics.append(Metric("snapshot_insert", duration, "s"))
        report.metrics.append(
            Metric("snapshot_rows_per_second", written / max(duration, 1e-9), "rows/s")
        )
        report.notes.append(f"Snapshot-Zeilen: {written}")

        started = time.perf_counter()
        first_page = _page(factory, workspace_id, limit=100, offset=0)
        report.metrics.append(
            Metric(
                "first_page_100",
                time.perf_counter() - started,
                "s",
                FIRST_PAGE_TARGET_SECONDS,
            )
        )
        report.notes.append(f"erste Seite: {len(first_page)} Zeilen")

        started = time.perf_counter()
        middle = _page(factory, workspace_id, limit=1000, offset=assets // 2)
        report.metrics.append(
            Metric(
                "page_1000_mid",
                time.perf_counter() - started,
                "s",
                QUERY_TARGET_SECONDS,
            )
        )
        report.notes.append(f"mittlerer Block: {len(middle)} Zeilen")

        changed = _apply_changes(engine, workspace_id, assets, keys)
        report.metrics.append(Metric("changeset_cells", float(changed), "cells"))

        sample = json.loads(first_page[0]["values_json"])
        text_key, number_key = keys[0], keys[1]
        text_value = str(sample[text_key])

        duration, count = _timed_scalar(
            factory,
            equality_count_query(),
            {
                "workspace_id": workspace_id,
                "value": text_value,
                **json_parameters(text_key),
            },
        )
        report.metrics.append(Metric("filter_equality_text", duration, "s", QUERY_TARGET_SECONDS))
        report.notes.append(f"Treffer Textfilter: {count}")

        duration, rows = _timed_rows(
            factory,
            range_sorted_query(),
            {
                "workspace_id": workspace_id,
                "minimum": 5000,
                "limit": 100,
                **json_parameters(number_key),
            },
        )
        report.metrics.append(Metric("filter_range_sorted", duration, "s", QUERY_TARGET_SECONDS))
        report.notes.append(f"Treffer Bereichsfilter: {len(rows)}")

        latencies, concurrent_writes, errors = _concurrent_reads(
            db_path, workspace_id, keys, assets, concurrency_seconds
        )
        report.metrics.append(
            Metric(
                "concurrent_read_p95",
                percentile(latencies, 0.95),
                "s",
                CONCURRENT_TARGET_SECONDS,
            )
        )
        report.metrics.append(Metric("concurrent_writes", float(concurrent_writes), "commits"))
        report.notes.append(
            f"Nebenlaeufige Lesezugriffe: {len(latencies)}, Pausen durch Sperren: {len(errors)}"
        )
        report.notes.extend(errors[:3])

        duration = _audit_inserts(engine, factory, workspace_id, keys, audit_rows)
        report.metrics.append(Metric("audit_insert", duration, "s"))
        report.metrics.append(
            Metric(
                "audit_rows_per_second",
                audit_rows / max(duration, 1e-9),
                "rows/s",
            )
        )

        size = _database_size(db_path)
        report.metrics.append(Metric("db_size_mb", size / 1024 / 1024, "MB"))
        report.metrics.append(Metric("storage_bytes_per_asset", size / max(assets, 1), "bytes"))
    finally:
        engine.dispose()

    report.notes.append(f"Datenbank: {db_path}")
    return report
