"""Laufuebersicht, Feldhistorie und Undo-Vorbereitung.

Das Change-Log ist die Quelle fuer Audit und Undo: nur nachweislich wirksame Aenderungen
(`ChangeStatus.OK`) duerfen zurueckgenommen werden, und ein Undo ist immer eine neue
Aenderung durch dieselbe Review- und Schreibpipeline – kein atomarer Rollback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.i18n import t
from app.models import AppUser, ChangeLog, Profile, Run, Workspace
from app.models.base import utc_now
from app.models.enums import ChangeStatus, RunKind
from app.normalize import display_value, values_equal
from app.schema import ProfileSchema, resolve_columns
from app.workspaces import (
    AssetRow,
    WorkspaceError,
    create_workspace,
    set_change,
    store_snapshot,
)
from app.writer import read_files

HISTORY_RETENTION_DAYS = 90


class UndoError(WorkspaceError):
    """Der Lauf laesst sich nicht zuruecknehmen."""


@dataclass
class RunSummary:
    """Kompakte Zeile der Laufuebersicht."""

    run: Run
    user_name: str | None = None
    profile_name: str | None = None
    workspace_name: str | None = None
    ok: int = 0
    planned: int = 0
    unknown: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.ok + self.planned + self.unknown + self.failed + self.skipped


@dataclass
class UndoReport:
    """Ergebnis der Undo-Vorbereitung."""

    workspace_id: int
    applied: list[tuple[int, str]] = field(default_factory=list)
    skipped_diverged: list[tuple[int, str]] = field(default_factory=list)
    skipped_unchanged: list[tuple[int, str]] = field(default_factory=list)
    skipped_status: list[tuple[int, str]] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return len(self.applied)


def list_runs(
    session: Session, *, limit: int = 50, kind: RunKind | None = None
) -> list[RunSummary]:
    """Laeufe mit Zaehlern je Status, neueste zuerst."""
    statement = select(Run).order_by(Run.started_at.desc()).limit(limit)
    if kind is not None:
        statement = statement.where(Run.kind == kind)
    runs = list(session.scalars(statement))
    if not runs:
        return []
    counts = session.execute(
        select(ChangeLog.run_id, ChangeLog.status, func.count())
        .where(ChangeLog.run_id.in_([run.id for run in runs]))
        .group_by(ChangeLog.run_id, ChangeLog.status)
    ).all()
    per_run: dict[int, dict[ChangeStatus, int]] = {}
    for run_id, status, count in counts:
        per_run.setdefault(int(run_id), {})[status] = int(count)
    users = _names(session, AppUser, {run.user_id for run in runs if run.user_id})
    profiles = _names(session, Profile, {run.profile_id for run in runs if run.profile_id})
    workspaces = _names(session, Workspace, {run.workspace_id for run in runs if run.workspace_id})
    summaries: list[RunSummary] = []
    for run in runs:
        by_status = per_run.get(int(run.id), {})
        summaries.append(
            RunSummary(
                run=run,
                user_name=users.get(run.user_id or 0),
                profile_name=profiles.get(run.profile_id or 0),
                workspace_name=workspaces.get(run.workspace_id or 0),
                ok=by_status.get(ChangeStatus.OK, 0),
                planned=by_status.get(ChangeStatus.PLANNED, 0),
                unknown=by_status.get(ChangeStatus.UNKNOWN, 0),
                failed=by_status.get(ChangeStatus.FAILED, 0),
                skipped=by_status.get(ChangeStatus.SKIPPED, 0)
                + by_status.get(ChangeStatus.SKIPPED_CONFLICT, 0),
            )
        )
    return summaries


def _names(session: Session, model: Any, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = session.execute(
        select(model.id, model.name if model is not AppUser else model.username).where(
            model.id.in_(list(ids))
        )
    ).all()
    return {int(row[0]): str(row[1]) for row in rows if row[1]}


def run_changes(session: Session, run_id: int) -> list[ChangeLog]:
    return list(
        session.scalars(select(ChangeLog).where(ChangeLog.run_id == run_id).order_by(ChangeLog.id))
    )


def undoable_changes(session: Session, run_id: int) -> list[ChangeLog]:
    """Nur nachweislich wirksame Aenderungen duerfen zurueckgenommen werden."""
    return [row for row in run_changes(session, run_id) if row.status is ChangeStatus.OK]


def prepare_undo(
    session: Session,
    run: Run,
    schema: ProfileSchema,
    client: Any,
    *,
    actor: AppUser,
    name: str | None = None,
) -> UndoReport:
    """Legt einen neuen Arbeitsbestand an, der die alten Werte zurueckschreibt."""
    if run.profile_id is None:
        raise UndoError(t("Der Lauf hat kein Profil."))
    profile = session.get(Profile, run.profile_id)
    if profile is None:
        raise UndoError(t("Das Profil des Laufs fehlt."))
    rows = run_changes(session, run.id)
    if not rows:
        raise UndoError(t("Der Lauf enthält keine Feldänderungen."))

    resolved, unknown = resolve_columns(schema, sorted({row.field_key for row in rows}))
    by_key = {column.key: column for column in resolved}
    if unknown:
        raise UndoError(t("Unbekannte Spalten im Lauf: {keys}", keys=", ".join(unknown)))

    file_ids = sorted({int(row.file_id) for row in rows})
    current = read_files(client, resolved, file_ids)
    missing = [file_id for file_id in file_ids if file_id not in current]
    if missing:
        raise UndoError(
            t("Dateien fehlen: {files}", files=", ".join(str(item) for item in missing))
        )

    report = UndoReport(workspace_id=0)
    planned: list[tuple[int, str, Any]] = []
    for row in rows:
        pair = (int(row.file_id), row.field_key)
        if row.status is not ChangeStatus.OK:
            report.skipped_status.append(pair)
            continue
        read_back = current[int(row.file_id)]["values"].get(row.field_key)
        if not values_equal(read_back, _from_text(row.new_value)):
            report.skipped_diverged.append(pair)
            continue
        target = _from_text(row.old_value)
        if values_equal(read_back, target):
            report.skipped_unchanged.append(pair)
            continue
        planned.append((int(row.file_id), row.field_key, target))
    if not planned:
        raise UndoError(
            t(
                "Kein Feld lässt sich zurücknehmen ({diverged} abweichend, {status} nicht wirksam).",
                diverged=len(report.skipped_diverged),
                status=len(report.skipped_status),
            )
        )

    workspace = create_workspace(
        session,
        owner=actor,
        profile=profile,
        name=(name or "") or t("Undo zu Lauf {run}", run=run.id),
    )
    store_snapshot(
        session,
        workspace,
        [
            AssetRow(
                file_id=file_id,
                modify_date=str(item["modifyDate"]),
                values=item["values"],
            )
            for file_id, item in current.items()
        ],
    )
    report.workspace_id = workspace.id
    for file_id, key, target in planned:
        if set_change(session, workspace, file_id=file_id, column=by_key[key], value=target):
            report.applied.append((file_id, key))
        else:
            report.skipped_unchanged.append((file_id, key))
    if not report.applied:
        raise UndoError(
            t(
                "Kein Feld lässt sich zurücknehmen ({diverged} abweichend, {status} nicht wirksam).",
                diverged=len(report.skipped_diverged),
                status=len(report.skipped_status),
            )
        )
    return report


def _from_text(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def purge_change_values(
    session: Session, *, days: int = HISTORY_RETENTION_DAYS, now: datetime | None = None
) -> int:
    """Entfernt Feldwerte alter Laeufe; kompakte Laufdaten bleiben erhalten."""
    moment = now or utc_now()
    threshold = moment - timedelta(days=days)
    rows = list(
        session.scalars(
            select(ChangeLog)
            .join(Run, Run.id == ChangeLog.run_id)
            .where(Run.started_at < threshold)
            .where((ChangeLog.old_value.is_not(None)) | (ChangeLog.new_value.is_not(None)))
        )
    )
    for row in rows:
        row.old_value = None
        row.new_value = None
    session.flush()
    return len(rows)


def describe_change(row: ChangeLog) -> dict[str, str]:
    """Anzeigezeile eines Feldeintrags fuer die Laufseite."""
    return {
        "file_id": str(row.file_id),
        "field": row.field_key,
        "old": display_value(_from_text(row.old_value)),
        "new": display_value(_from_text(row.new_value)),
        "status": str(row.status),
        "error": row.error or "",
    }


__all__ = [
    "HISTORY_RETENTION_DAYS",
    "RunSummary",
    "UndoError",
    "UndoReport",
    "describe_change",
    "list_runs",
    "prepare_undo",
    "purge_change_values",
    "run_changes",
    "undoable_changes",
]
