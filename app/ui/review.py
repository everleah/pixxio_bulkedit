"""Review- und Schreibseite eines Arbeitsbestands.

Die Seite prüft das ChangeSet, zeigt jede geplante Feldänderung und schreibt erst nach
Dry Run und ausdrücklicher Bestätigung. Der gespeicherte Plan bleibt an den Digest des
Entwurfs gebunden; ändert sich der Entwurf, muss der Review erneuert werden.
"""

from __future__ import annotations

from typing import Any

from nicegui import run, ui

from app.clients import ClientFactory
from app.db import SessionFactory, session_scope
from app.i18n import describe_error, t
from app.models import AppUser, Profile, Workspace
from app.models.enums import RunMode, RunStatus, StepStatus
from app.schema import SchemaCache
from app.ui.guard import current_user, redirect_to_login
from app.ui.shell import apply_locale, apply_palette, page_header
from app.ui.widgets import action_button
from app.ui.workspaces import owned_workspace, script_column_keys, workspace_columns
from app.writeplan import PlanPreview, latest_plan, plan_is_current, save_plan
from app.writer import WriteReport, dry_run, execute, execution_blockers, review

REVIEW_SUFFIX = "/review"
MAX_PREVIEW_ROWS = 500


def review_route(workspace_id: int) -> str:
    return f"/workspaces/{workspace_id}{REVIEW_SUFFIX}"


def _status_text(report: WriteReport) -> str:
    if report.mode is RunMode.DRY_RUN:
        return t(
            "Dry Run {run}: geprüft ({steps} Anfrage(n), {conflicts} Konflikt(e)).",
            run=report.run_id,
            steps=len(report.steps),
            conflicts=len(report.conflicts),
        )
    return t(
        "Schreiblauf {run}: {status} ({ok} erfolgreich, {unknown} unklar, {failed} fehlgeschlagen, "
        "{skipped} übersprungen).",
        run=report.run_id,
        status=report.status.value,
        ok=report.ok_steps,
        unknown=sum(1 for step in report.steps if step.status is StepStatus.UNKNOWN),
        failed=sum(1 for step in report.steps if step.status is StepStatus.FAILED),
        skipped=sum(1 for step in report.steps if step.status is StepStatus.SKIPPED),
    )


def register_review_pages(
    session_factory: SessionFactory,
    schema_cache: SchemaCache,
    client_factory: ClientFactory,
) -> None:
    """Registriert die Review-Seite."""

    @ui.page("/workspaces/{workspace_id}" + REVIEW_SUFFIX)
    def review_page(workspace_id: int) -> None:  # pyright: ignore[reportUnusedFunction]
        apply_palette()
        apply_locale()
        user = current_user(session_factory)
        if user is None:
            redirect_to_login()
            return

        with session_scope(session_factory) as session:
            workspace = owned_workspace(session, workspace_id, user)
            if workspace is None:
                page_header(t("Arbeitsbestände"), user)
                ui.label(t("Der Arbeitsbestand wurde nicht gefunden.")).classes("text-negative")
                return
            profile = session.get(Profile, workspace.profile_id)
            if profile is None:
                page_header(t("Arbeitsbestände"), user)
                ui.label(t("Das Profil fehlt.")).classes("text-negative")
                return
            name = workspace.name or t("Arbeitsbestand {id}", id=workspace.id)
            profile_id = profile.id
            script_keys = script_column_keys(session, workspace)
            schema = schema_cache.get(profile)
            columns = workspace_columns(schema, script_keys)

        page_header(name, user)
        ui.label(
            t("Nur geänderte Felder werden geschrieben; jedes Ergebnis wird zurückgelesen.")
        ).classes("text-sm")
        message = ui.label("").classes("text-sm")
        problems = ui.column().classes("w-full gap-0")
        overwrite = ui.checkbox(t("Externe Änderungen überschreiben"), value=False)
        comment = (
            ui.input(t("Kommentar zum Statuswechsel")).props("outlined dense").classes("w-full")
        )
        table = ui.column().classes("w-full gap-0")

        def load(session: Any) -> tuple[Workspace | None, Profile | None, AppUser | None]:
            return (
                session.get(Workspace, workspace_id),
                session.get(Profile, profile_id),
                session.get(AppUser, user.id),
            )

        def build_preview(session: Any) -> PlanPreview:
            workspace_row, profile, _actor = load(session)
            if workspace_row is None or profile is None:
                raise ValueError(t("Der Arbeitsbestand wurde nicht gefunden."))
            client = client_factory.client_for(profile)
            return review(
                session,
                workspace_row,
                schema,
                columns,
                client,
                script_columns=script_keys,
                comment=str(comment.value or ""),
            )

        def plan_for(session: Any, preview: PlanPreview) -> Any:
            workspace_row, _profile, actor = load(session)
            if workspace_row is None:
                raise ValueError(t("Der Arbeitsbestand wurde nicht gefunden."))
            plan = latest_plan(session, workspace_id)
            if plan is None or not plan_is_current(preview, plan):
                plan = save_plan(session, workspace_row, preview, actor=actor, mode=RunMode.DRY_RUN)
                session.flush()
            return plan

        def show(preview: PlanPreview) -> None:
            if preview.requires_comment and not preview.comment:
                comment.classes(add="text-negative")
            else:
                comment.classes(remove="text-negative")
            message.set_text(
                t(
                    "Feldänderungen: {changes} | Dateien: {files} | Anfragen: {steps}",
                    changes=preview.changed_cells,
                    files=preview.affected_files,
                    steps=len(preview.steps),
                )
            )
            problems.clear()
            with problems:
                hidden = {
                    t("Es gibt keine Änderungen."),
                    t("Die Änderungen ergeben keinen Schreibvorgang."),
                }
                for item in preview.errors:
                    if item in hidden:
                        continue
                    ui.label(t("Fehler: {message}", message=item)).classes("text-negative text-sm")
                for item in preview.warnings:
                    ui.label(t("Hinweis: {message}", message=item)).classes("text-warning text-sm")
            table.clear()
            with table:
                if not preview.changes:
                    ui.label(t("Es gibt keine Änderungen.")).classes("text-sm")
                    return
                for change in preview.changes[:MAX_PREVIEW_ROWS]:
                    with ui.row().classes("w-full items-center gap-3 border-b py-1 text-sm"):
                        ui.label(str(change.file_id)).classes("w-24 text-grey")
                        ui.label(change.label).classes("w-48 font-medium")
                        ui.label(change.old_display or "–").classes("flex-1 text-grey")
                        ui.label("→").classes("text-grey")
                        ui.label(change.new_display or "–").classes("flex-1")

        def refresh_job() -> PlanPreview:
            with session_scope(session_factory) as session:
                return build_preview(session)

        def dry_run_job() -> tuple[PlanPreview, WriteReport]:
            with session_scope(session_factory) as session:
                preview = build_preview(session)
                if preview.errors:
                    raise ValueError(t("Der Plan enthält Fehler und ist nicht ausführbar."))
                _workspace_row, profile, actor = load(session)
                if profile is None:
                    raise ValueError(t("Der Arbeitsbestand wurde nicht gefunden."))
                plan = plan_for(session, preview)
                client = client_factory.client_for(profile)
                return preview, dry_run(session, plan, preview, client, columns, actor=actor)

        def write_job(confirmed: bool) -> tuple[PlanPreview, WriteReport]:
            with session_scope(session_factory) as session:
                preview = build_preview(session)
                _workspace_row, profile, actor = load(session)
                if profile is None:
                    raise ValueError(t("Der Arbeitsbestand wurde nicht gefunden."))
                plan = plan_for(session, preview)
                blockers = execution_blockers(session, plan, preview, overwrite_confirmed=confirmed)
                if blockers:
                    raise ValueError(" ".join(blockers))
                client = client_factory.writer_client_for(profile)
                report = execute(
                    session,
                    plan,
                    preview,
                    client,
                    columns,
                    actor=actor,
                    overwrite_confirmed=confirmed,
                )
                return build_preview(session), report

        async def refresh_now() -> None:
            try:
                preview = await run.io_bound(refresh_job)
            except Exception as exc:  # noqa: BLE001 - Meldung in der Seite
                ui.notify(describe_error(exc), color="negative")
                return
            if preview is None:
                return
            show(preview)
            ui.notify(t("Review aktualisiert."))

        async def start_dry_run() -> None:
            try:
                outcome = await run.io_bound(dry_run_job)
            except Exception as exc:  # noqa: BLE001 - Meldung in der Seite
                ui.notify(describe_error(exc), color="negative")
                return
            if outcome is None:
                return
            preview, report = outcome
            show(preview)
            ui.notify(
                _status_text(report),
                color="positive" if report.status is RunStatus.OK else "warning",
            )

        async def start_write() -> None:
            try:
                outcome = await run.io_bound(write_job, bool(overwrite.value))
            except Exception as exc:  # noqa: BLE001 - Meldung in der Seite
                ui.notify(describe_error(exc), color="negative")
                return
            if outcome is None:
                return
            preview, report = outcome
            show(preview)
            ui.notify(
                _status_text(report),
                color="positive" if report.status is RunStatus.OK else "warning",
            )
            if report.committed:
                ui.notify(
                    t(
                        "Aus dem Entwurf entfernte Änderungen: {count}",
                        count=report.committed,
                    )
                )

        try:
            show(refresh_job())
        except Exception as exc:  # noqa: BLE001 - Seite bleibt bedienbar
            ui.label(describe_error(exc)).classes("text-negative")

        with ui.row().classes("w-full items-center gap-1"):
            action_button("refresh", t("Review aktualisieren"), refresh_now)
            action_button("science", t("Dry Run prüfen"), start_dry_run)
            action_button("save", t("Jetzt schreiben"), start_write)
            action_button(
                "arrow_back",
                t("Zum Grid"),
                lambda: ui.navigate.to(f"/workspaces/{workspace_id}"),
            )


__all__ = ["register_review_pages", "review_route"]
