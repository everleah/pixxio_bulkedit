"""Schreiblauf: Review, Dry Run, Ausführung und Verifikation.

Der Writer schreibt ausschließlich den gespeicherten Plan (Ziel-IDs und Payload aus
``write_plan_step``). Ein Schreiberfolg entsteht aus dem Job-Ergebnis und der
Rücklesung, nicht aus dem Absenden allein: unklare Ergebnisse werden als ``unknown``
ausgewiesen und nie blind wiederholt.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pixxio_client.exceptions import (
    APIQuotaExceededException,
    BadRequestException,
    ConflictException,
    ConnectionException,
    ForbiddenException,
    HTTPException,
    JobAbortedException,
    JobFailedException,
    JobTimeoutException,
    NotFoundException,
    ServerError,
    TimeoutException,
    UnauthorizedException,
    UnprocessableEntityException,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import plain
from app.i18n import t
from app.models import AppUser, ChangeLog, Profile, Run, Workspace, WritePlan
from app.models.base import utc_now
from app.models.enums import (
    ChangeStatus,
    PlanStatus,
    RunKind,
    RunMode,
    RunSource,
    RunStatus,
    StepStatus,
)
from app.normalize import display_value, values_equal
from app.schema import ColumnDef, ProfileSchema
from app.workspaces import WorkspaceError, commit_applied, file_values
from app.writeplan import (
    PlannedChange,
    PlanPreview,
    build_preview,
    current_digest,
    detect_conflicts,
    modify_dates,
    plan_comment,
    plan_is_current,
    plan_steps,
)

READ_CHUNK_SIZE = 100
JOB_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 2.0

# Fehler, bei denen ein weiterer Schritt nicht sinnvoll ist.
PAUSE_ERRORS = (UnauthorizedException, ForbiddenException)
# Fehler mit unklarem Ausgang: der Request kann teilweise gewirkt haben.
AMBIGUOUS_ERRORS = (
    JobTimeoutException,
    JobAbortedException,
    ConnectionException,
    TimeoutException,
    ServerError,
    APIQuotaExceededException,
)
REJECTED_ERRORS = (
    BadRequestException,
    UnprocessableEntityException,
    NotFoundException,
    ConflictException,
)


class WriteError(WorkspaceError):
    """Der Auftrag darf nicht oder nicht weiter ausgeführt werden."""


@dataclass
class StepReport:
    """Ergebnis eines Auftragsschritts."""

    step_no: int
    status: StepStatus
    ids: tuple[int, ...] = ()
    job_id: int | None = None
    error: str | None = None
    checked: int = 0
    mismatched: int = 0
    paused: bool = False


@dataclass
class WriteReport:
    """Ergebnis eines Laufs über alle Schritte."""

    mode: RunMode
    status: RunStatus
    run_id: int | None = None
    steps: list[StepReport] = field(default_factory=list)
    conflicts: list[int] = field(default_factory=list)
    late_conflicts: list[int] = field(default_factory=list)
    paused: bool = False
    committed: int = 0

    @property
    def ok_steps(self) -> int:
        return sum(1 for step in self.steps if step.status is StepStatus.OK)


def _job_id(response: Any) -> int | None:
    body = plain(response)
    if not isinstance(body, dict):
        return None
    for key in ("jobID", "jobId", "job_id"):
        value = body.get(key)
        if isinstance(value, int):
            return value
    return None


def read_files(
    client: Any, columns: Sequence[ColumnDef], file_ids: Iterable[int]
) -> dict[int, dict[str, Any]]:
    """Aktuelle Werte und ``modifyDate`` der Dateien lesen."""
    from pixxio_client.files import File

    files = File(client)
    ids = sorted({int(file_id) for file_id in file_ids})
    result: dict[int, dict[str, Any]] = {}
    for start in range(0, len(ids), READ_CHUNK_SIZE):
        selector = {"filterType": "files", "fileIDs": ids[start : start + READ_CHUNK_SIZE]}
        for item in files.iter_all(filter=selector, page_size=READ_CHUNK_SIZE):
            payload = plain(item)
            file_id = payload.get("id")
            if not isinstance(file_id, int):
                continue
            result[file_id] = {
                "modifyDate": str(payload.get("modifyDate") or ""),
                "values": file_values(payload, columns),
            }
    return result


def overlap_warnings(session: Session, workspace: Workspace) -> list[str]:
    """Laufende Schreibaufträge auf demselben Host (profilübergreifend)."""
    profile = session.get(Profile, workspace.profile_id)
    if profile is None:
        return []
    rows = session.execute(
        select(Run.id, Run.workspace_id)
        .join(Profile, Profile.id == Run.profile_id)
        .where(
            Run.kind == RunKind.WRITE,
            Run.mode == RunMode.LIVE,
            Run.status == RunStatus.RUNNING,
            Run.workspace_id != workspace.id,
            Profile.host == profile.host,
        )
    ).all()
    if not rows:
        return []
    listed = ", ".join(str(int(row.id)) for row in rows)
    return [
        t(
            "Ein weiterer Schreibauftrag läuft auf diesem Host bereits (Läufe: {runs}).",
            runs=listed,
        )
    ]


def review(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    columns: Sequence[ColumnDef],
    client: Any,
    *,
    script_columns: Sequence[str] | None = None,
    comment: str = "",
) -> PlanPreview:
    """ChangeSet prüfen und externe Änderungen sowie Überschneidungen melden."""
    preview = build_preview(session, workspace, schema, script_columns, comment=comment)
    if not preview.changes:
        return preview
    file_ids = {change.file_id for change in preview.changes}
    current = read_files(client, columns, file_ids)
    for file_id in sorted(file_ids - set(current)):
        preview.errors.append(t("Datei {file_id} ist nicht mehr vorhanden.", file_id=file_id))
    detect_conflicts(
        session,
        workspace,
        preview,
        {file_id: str(item["modifyDate"]) for file_id, item in current.items()},
    )
    preview.warnings.extend(overlap_warnings(session, workspace))
    return preview


def execution_blockers(
    session: Session, plan: WritePlan, preview: PlanPreview, *, overwrite_confirmed: bool
) -> list[str]:
    """Gründe, warum der Plan jetzt nicht ausgeführt werden darf."""
    blockers: list[str] = []
    if preview.errors:
        blockers.append(t("Der Plan enthält Fehler und ist nicht ausführbar."))
    if not plan_is_current(preview, plan) or (
        plan.workspace_id is not None
        and current_digest(session, plan.workspace_id, comment=plan_comment(plan))
        != plan.change_digest
    ):
        blockers.append(t("Der Entwurf hat sich geändert. Bitte Review und Dry Run erneuern."))
    if plan.status in {PlanStatus.RUNNING, PlanStatus.COMPLETED}:
        blockers.append(t("Dieser Auftrag wurde bereits ausgeführt."))
    if preview.conflict_files and not (overwrite_confirmed or plan.overwrite_confirmed):
        blockers.append(
            t("Externe Änderungen erkannt. Bitte das Überschreiben ausdrücklich bestätigen.")
        )
    return blockers


def _run_row(
    session: Session,
    workspace: Workspace,
    plan: WritePlan,
    *,
    mode: RunMode,
    actor: AppUser | None,
) -> Run:
    run = Run(
        kind=RunKind.WRITE,
        mode=mode,
        source=RunSource.GRID,
        status=RunStatus.RUNNING,
        user_id=actor.id if actor is not None else None,
        profile_id=workspace.profile_id,
        script_version_id=workspace.script_version_id,
        workspace_id=workspace.id,
        write_plan_id=plan.id,
        plan_json=plan.plan_json,
    )
    session.add(run)
    return run


def _log_rows(
    session: Session, run: Run, changes: Sequence[PlannedChange]
) -> dict[int, list[ChangeLog]]:
    rows: dict[int, list[ChangeLog]] = {}
    for change in changes:
        row = ChangeLog(
            run_id=run.id,
            file_id=change.file_id,
            field_key=change.key,
            old_value=change.old_display,
            new_value=change.new_display,
            status=ChangeStatus.PLANNED,
        )
        session.add(row)
        rows.setdefault(change.file_id, []).append(row)
    return rows


def _expected(preview: PlanPreview, ids: Sequence[int]) -> dict[int, dict[str, Any]]:
    wanted = set(ids)
    expected: dict[int, dict[str, Any]] = {}
    for change in preview.changes:
        if change.file_id in wanted:
            expected.setdefault(change.file_id, {})[change.key] = change.new_value
    return expected


def _compare(
    expected: dict[int, dict[str, Any]], current: dict[int, dict[str, Any]]
) -> dict[tuple[int, str], bool]:
    result: dict[tuple[int, str], bool] = {}
    for file_id, fields in expected.items():
        read_back = current.get(file_id)
        for key, value in fields.items():
            if read_back is None:
                result[(file_id, key)] = False
                continue
            result[(file_id, key)] = values_equal(read_back["values"].get(key), value)
    return result


def dry_run(
    session: Session,
    plan: WritePlan,
    preview: PlanPreview,
    client: Any,
    columns: Sequence[ColumnDef],
    *,
    actor: AppUser | None,
) -> WriteReport:
    """Prüft den Plan ohne zu schreiben und protokolliert die Prüfung."""
    workspace = session.get(Workspace, plan.workspace_id) if plan.workspace_id else None
    if workspace is None:
        raise WriteError(t("Der Arbeitsbestand zum Plan fehlt."))
    if preview.errors:
        raise WriteError("\n".join(preview.errors))
    if (
        current_digest(session, plan.workspace_id or 0, comment=plan_comment(plan))
        != plan.change_digest
    ):
        raise WriteError(t("Der Entwurf hat sich geändert. Bitte Review und Dry Run erneuern."))

    file_ids = sorted({change.file_id for change in preview.changes})
    current = read_files(client, columns, file_ids)
    missing = sorted(set(file_ids) - set(current))
    conflicts = list(preview.conflict_files)

    run = _run_row(session, workspace, plan, mode=RunMode.DRY_RUN, actor=actor)
    session.flush()
    _log_rows(session, run, preview.changes)

    report = WriteReport(
        mode=RunMode.DRY_RUN, status=RunStatus.OK, run_id=run.id, conflicts=conflicts
    )
    for step in plan_steps(session, plan):
        report.steps.append(
            StepReport(
                step_no=step.step_no,
                status=StepStatus.PENDING,
                ids=tuple(json.loads(step.ids_json)),
            )
        )
    if missing or conflicts or preview.warnings:
        report.status = RunStatus.PARTIAL
    run.status = report.status
    run.finished_at = utc_now()
    run.stats_json = json.dumps(_stats(report, missing=missing), ensure_ascii=False)
    session.flush()
    return report


def _stats(report: WriteReport, *, missing: Sequence[int] = ()) -> dict[str, Any]:
    return {
        "mode": str(report.mode),
        "status": str(report.status),
        "steps": len(report.steps),
        "ok_steps": report.ok_steps,
        "unknown_steps": sum(1 for step in report.steps if step.status is StepStatus.UNKNOWN),
        "failed_steps": sum(1 for step in report.steps if step.status is StepStatus.FAILED),
        "skipped_steps": sum(1 for step in report.steps if step.status is StepStatus.SKIPPED),
        "mismatched": sum(step.mismatched for step in report.steps),
        "conflicts": list(report.conflicts),
        "late_conflicts": list(report.late_conflicts),
        "missing": list(missing),
        "paused": report.paused,
        "committed": report.committed,
    }


def execute(
    session: Session,
    plan: WritePlan,
    preview: PlanPreview,
    client: Any,
    columns: Sequence[ColumnDef],
    *,
    actor: AppUser | None,
    overwrite_confirmed: bool = False,
) -> WriteReport:
    """Führt einen bestätigten Plan aus, verifiziert und protokolliert jede Übernahme."""
    from pixxio_client.files import File
    from pixxio_client.jobs import Job

    workspace = session.get(Workspace, plan.workspace_id) if plan.workspace_id else None
    if workspace is None:
        raise WriteError(t("Der Arbeitsbestand zum Plan fehlt."))
    blockers = execution_blockers(session, plan, preview, overwrite_confirmed=overwrite_confirmed)
    if blockers:
        raise WriteError(" ".join(blockers))

    run = _run_row(session, workspace, plan, mode=RunMode.LIVE, actor=actor)
    plan.status = PlanStatus.RUNNING
    plan.mode = RunMode.LIVE
    plan.approved_by_id = actor.id if actor is not None else None
    plan.approved_at = utc_now()
    plan.overwrite_confirmed = bool(overwrite_confirmed or plan.overwrite_confirmed)
    session.flush()
    rows = _log_rows(session, run, preview.changes)
    session.flush()

    files = File(client)
    jobs = Job(client)
    report = WriteReport(
        mode=RunMode.LIVE,
        status=RunStatus.RUNNING,
        run_id=run.id,
        conflicts=list(preview.conflict_files),
    )
    stored_dates = modify_dates(
        session, workspace.id, sorted({change.file_id for change in preview.changes})
    )
    current = read_files(client, columns, stored_dates)
    report.late_conflicts = sorted(
        file_id
        for file_id, item in current.items()
        if stored_dates.get(file_id, "") not in {"", str(item["modifyDate"])}
    )
    if report.late_conflicts:
        report.conflicts = sorted(set(report.conflicts) | set(report.late_conflicts))
    paused = False
    for step in plan_steps(session, plan):
        ids = tuple(int(value) for value in json.loads(step.ids_json))
        if paused:
            step.status = StepStatus.SKIPPED
            step.finished_at = utc_now()
            for row in _step_rows(rows, ids):
                row.status = ChangeStatus.SKIPPED
            report.steps.append(
                StepReport(step_no=step.step_no, status=StepStatus.SKIPPED, ids=ids)
            )
            continue
        step.status = StepStatus.RUNNING
        step.attempts = int(step.attempts or 0) + 1
        step.started_at = utc_now()
        report_step = StepReport(step_no=step.step_no, status=StepStatus.RUNNING, ids=ids)
        report.steps.append(report_step)
        payload = json.loads(step.payload_json)
        hard_error: str | None = None
        ambiguous = False
        try:
            response = files.update(ids=list(ids), **payload)
            job_id = _job_id(response)
            if job_id is not None:
                step.job_id = job_id
                report_step.job_id = job_id
                outcome = jobs.wait_for_completion(
                    job_id=job_id,
                    timeout=JOB_TIMEOUT_SECONDS,
                    poll_interval=POLL_INTERVAL_SECONDS,
                )
                body = plain(outcome)
                if isinstance(body, dict) and body.get("success") is False:
                    hard_error = str(
                        body.get("error") or t("Der Hintergrundauftrag ist fehlgeschlagen.")
                    )
            else:
                body = plain(response)
                if isinstance(body, dict) and body.get("success") is False:
                    hard_error = t("Die API hat den Schreibvorgang abgelehnt.")
        except PAUSE_ERRORS as exc:
            hard_error = str(exc)
            report_step.paused = True
        except REJECTED_ERRORS as exc:
            hard_error = str(exc)
        except JobFailedException as exc:
            hard_error = str(exc)
        except AMBIGUOUS_ERRORS as exc:
            hard_error = t("Ausgang unklar: {message}", message=str(exc))
            ambiguous = True
        except HTTPException as exc:
            hard_error = t("Ausgang unklar: {message}", message=str(exc))
            ambiguous = True
        except Exception as exc:  # noqa: BLE001 - jeder Fehler wird protokolliert
            hard_error = t("Ausgang unklar: {message}", message=str(exc))
            ambiguous = True

        checked = _compare(_expected(preview, ids), read_files(client, columns, ids))
        report_step.checked = len(checked)
        report_step.mismatched = sum(1 for ok in checked.values() if not ok)
        applied = [key for key, ok in checked.items() if ok]

        if hard_error is None:
            status = StepStatus.OK if report_step.mismatched == 0 else StepStatus.PARTIAL
            error = (
                None
                if report_step.mismatched == 0
                else t("Rücklesung weicht bei {count} Feld(ern) ab.", count=report_step.mismatched)
            )
        elif ambiguous and applied and report_step.mismatched == 0:
            status = StepStatus.OK
            error = t("Über Rücklesung bestätigt: {message}", message=hard_error)
        elif ambiguous and applied:
            status = StepStatus.PARTIAL
            error = hard_error
        elif ambiguous:
            status = StepStatus.UNKNOWN
            error = hard_error
        else:
            status = StepStatus.FAILED
            error = hard_error

        report_step.status = status
        report_step.error = error
        step.status = status
        step.error = error
        step.finished_at = utc_now()
        step.verification_json = json.dumps(
            {
                "checked": report_step.checked,
                "mismatched": report_step.mismatched,
                "applied": sorted(f"{file_id}:{key}" for file_id, key in applied),
            },
            ensure_ascii=False,
        )
        for row in _step_rows(rows, ids):
            field_ok = checked.get((row.file_id, row.field_key))
            row.status = (
                _change_status(status)
                if field_ok is None
                else (ChangeStatus.OK if field_ok else _change_status(status))
            )
            row.job_id = report_step.job_id
            row.error = error
        if report_step.paused:
            paused = True
            report.paused = True

    report.status = _final_status(report)
    plan.status = _plan_status(report.status)
    run.status = report.status
    run.finished_at = utc_now()

    if report.status is RunStatus.OK:
        applied_pairs = [
            (row.file_id, row.field_key)
            for file_rows in rows.values()
            for row in file_rows
            if row.status is ChangeStatus.OK
        ]
        if applied_pairs:
            current = read_files(client, columns, {file_id for file_id, _key in applied_pairs})
            report.committed = commit_applied(
                session,
                workspace,
                applied_pairs,
                values={file_id: item["values"] for file_id, item in current.items()},
                modify_dates={file_id: item["modifyDate"] for file_id, item in current.items()},
            )
    run.stats_json = json.dumps(_stats(report), ensure_ascii=False)
    session.flush()
    return report


def _step_rows(rows: dict[int, list[ChangeLog]], ids: Iterable[int]) -> list[ChangeLog]:
    wanted = set(ids)
    return [row for file_id, file_rows in rows.items() if file_id in wanted for row in file_rows]


def _change_status(status: StepStatus) -> ChangeStatus:
    """Schrittstatus auf den Feldeintrag im Change-Log abbilden."""
    return {
        StepStatus.OK: ChangeStatus.OK,
        StepStatus.PARTIAL: ChangeStatus.UNKNOWN,
        StepStatus.SKIPPED: ChangeStatus.SKIPPED,
        StepStatus.PENDING: ChangeStatus.PLANNED,
    }.get(status, ChangeStatus.FAILED)


def _final_status(report: WriteReport) -> RunStatus:
    statuses = [step.status for step in report.steps]
    if not statuses:
        return RunStatus.FAILED
    if all(status is StepStatus.OK for status in statuses):
        return RunStatus.OK
    if any(status is StepStatus.OK for status in statuses):
        return RunStatus.PARTIAL
    return RunStatus.FAILED


def _plan_status(status: RunStatus) -> PlanStatus:
    return {
        RunStatus.OK: PlanStatus.COMPLETED,
        RunStatus.PARTIAL: PlanStatus.PARTIAL,
    }.get(status, PlanStatus.FAILED)


def reconcile(
    session: Session,
    plan: WritePlan,
    client: Any,
    columns: Sequence[ColumnDef],
    *,
    preview: PlanPreview | None = None,
) -> WriteReport:
    """Nach einem Neustart bekannte Schritte pruefen, ohne erneut zu senden."""
    workspace = session.get(Workspace, plan.workspace_id) if plan.workspace_id else None
    if workspace is None:
        raise WriteError(t("Der Arbeitsbestand zum Plan fehlt."))
    changes = preview.changes if preview is not None else []
    expected_preview = _preview_from_plan(plan, changes)
    rows = _plan_log_rows(session, plan)
    run = _plan_run(session, plan)
    mode = run.mode if run is not None else plan.mode
    report = WriteReport(mode=mode, status=RunStatus.RUNNING, conflicts=[])
    for step in plan_steps(session, plan):
        ids = tuple(int(value) for value in json.loads(step.ids_json))
        item = StepReport(step_no=step.step_no, status=step.status, ids=ids, job_id=step.job_id)
        checked = _compare(_expected(expected_preview, ids), read_files(client, columns, ids))
        item.checked = len(checked)
        item.mismatched = sum(1 for ok in checked.values() if not ok)
        if checked and item.mismatched == 0:
            item.status = StepStatus.OK
        elif any(checked.values()):
            item.status = StepStatus.PARTIAL
        else:
            item.status = StepStatus.UNKNOWN
            item.error = t("Ausgang nach Neustart unklar. Bitte Werte prüfen.")
        step.status = item.status
        step.error = item.error
        step.finished_at = utc_now()
        step.verification_json = json.dumps(
            {
                "checked": item.checked,
                "mismatched": item.mismatched,
                "applied": sorted(
                    f"{file_id}:{key}" for (file_id, key), ok in checked.items() if ok
                ),
                "reconciled": True,
            },
            ensure_ascii=False,
        )
        for row in _step_rows(rows, ids):
            field_ok = checked.get((row.file_id, row.field_key))
            row.status = (
                _change_status(item.status)
                if field_ok is None
                else ChangeStatus.OK
                if field_ok
                else _change_status(item.status)
            )
            row.error = item.error
        report.steps.append(item)

    report.status = _final_status(report)
    plan.status = _plan_status(report.status)
    if run is not None and run.status is RunStatus.RUNNING:
        run.status = report.status
        run.finished_at = utc_now()
        report.run_id = run.id
    if report.status is RunStatus.OK:
        applied = [
            (row.file_id, row.field_key)
            for file_rows in rows.values()
            for row in file_rows
            if row.status is ChangeStatus.OK
        ]
        if applied:
            current = read_files(client, columns, {file_id for file_id, _key in applied})
            report.committed = commit_applied(
                session,
                workspace,
                applied,
                values={file_id: item["values"] for file_id, item in current.items()},
                modify_dates={file_id: item["modifyDate"] for file_id, item in current.items()},
            )
    if run is not None:
        run.stats_json = json.dumps(_stats(report), ensure_ascii=False)
    session.flush()
    return report


def _plan_run(session: Session, plan: WritePlan) -> Run | None:
    """Der Live-Lauf zu einem Plan (auch ein abgebrochener)."""
    return session.scalars(
        select(Run)
        .where(Run.write_plan_id == plan.id, Run.mode == RunMode.LIVE)
        .order_by(Run.id.desc())
        .limit(1)
    ).first()


def _plan_log_rows(session: Session, plan: WritePlan) -> dict[int, list[ChangeLog]]:
    """Change-Log-Eintraege aller Laeufe eines Plans, nach Datei gruppiert."""
    rows: dict[int, list[ChangeLog]] = {}
    statements = (
        select(ChangeLog).join(Run, Run.id == ChangeLog.run_id).where(Run.write_plan_id == plan.id)
    )
    for row in session.scalars(statements):
        rows.setdefault(int(row.file_id), []).append(row)
    return rows


def _preview_from_plan(plan: WritePlan, changes: Sequence[PlannedChange]) -> PlanPreview:
    if changes:
        return PlanPreview(changes=list(changes))
    stored = json.loads(plan.plan_json or "{}")
    restored = [
        PlannedChange(
            file_id=int(item["file_id"]),
            key=str(item["key"]),
            label=str(item.get("label") or item["key"]),
            old_value=item.get("old_value", item.get("old")),
            new_value=item.get("new_value", item.get("new")),
        )
        for item in stored.get("changes", [])
    ]
    return PlanPreview(changes=restored)


def display_pairs(preview: PlanPreview) -> list[dict[str, Any]]:
    """Änderungen als Zeilen für die Review-Tabelle."""
    return [
        {
            "file_id": change.file_id,
            "key": change.key,
            "label": change.label,
            "old": display_value(change.old_value),
            "new": display_value(change.new_value),
        }
        for change in preview.changes
    ]


__all__ = [
    "JOB_TIMEOUT_SECONDS",
    "POLL_INTERVAL_SECONDS",
    "READ_CHUNK_SIZE",
    "StepReport",
    "WriteError",
    "WriteReport",
    "display_pairs",
    "dry_run",
    "execute",
    "execution_blockers",
    "overlap_warnings",
    "read_files",
    "reconcile",
    "review",
]
