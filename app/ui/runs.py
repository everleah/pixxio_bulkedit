"""Laufuebersicht, Feldhistorie und Undo.

Die Uebersicht zeigt Laeufe mit ihren Zaehlern je Status; die Detailseite listet jede
Feldübernahme mit Alt-/Neu-Wert. Ein Undo bereitet einen neuen Arbeitsbestand mit den
alten Werten vor und fuehrt ihn durch dieselbe Review- und Schreibpipeline.
"""

from __future__ import annotations

from nicegui import run, ui

from app.clients import ClientFactory
from app.db import SessionFactory, session_scope
from app.i18n import describe_error, t
from app.models import AppUser, Profile, Run
from app.models.enums import RunStatus
from app.runs import (
    RunSummary,
    describe_change,
    list_runs,
    prepare_undo,
    purge_change_values,
    run_changes,
)
from app.schema import SchemaCache
from app.ui.guard import current_user, redirect_to_login
from app.ui.shell import apply_locale, apply_palette, page_header
from app.ui.widgets import action_button

LIST_ROUTE = "/runs"


def _status_color(status: RunStatus) -> str:
    if status is RunStatus.OK:
        return "text-positive"
    if status is RunStatus.FAILED:
        return "text-negative"
    return "text-warning"


def _counts(summary: RunSummary) -> str:
    return t(
        "ok {ok} | geplant {planned} | unklar {unknown} | fehlgeschlagen {failed} | "
        "übersprungen {skipped}",
        ok=summary.ok,
        planned=summary.planned,
        unknown=summary.unknown,
        failed=summary.failed,
        skipped=summary.skipped,
    )


def register_run_pages(
    session_factory: SessionFactory,
    schema_cache: SchemaCache,
    client_factory: ClientFactory,
) -> None:
    """Registriert Laufuebersicht und Laufdetail."""

    @ui.page(LIST_ROUTE)
    def runs_page() -> None:  # pyright: ignore[reportUnusedFunction]
        apply_palette()
        apply_locale()
        user = current_user(session_factory)
        if user is None:
            redirect_to_login()
            return
        page_header(t("Läufe"), user)
        ui.label(t("Nur nachweislich wirksame Änderungen lassen sich zurücknehmen.")).classes(
            "text-sm"
        )

        with session_scope(session_factory) as session:
            summaries = list_runs(session, limit=100)

        if not summaries:
            ui.label(t("Es gibt noch keine Läufe.")).classes("text-sm")
        for summary in summaries:
            with ui.row().classes("w-full items-center gap-3 border-b py-1 text-sm"):
                ui.label(str(summary.run.id)).classes("w-14 text-grey")
                ui.label(f"{summary.run.kind.value}/{summary.run.mode.value}").classes("w-32")
                ui.label(str(summary.run.status.value)).classes(
                    "w-24 " + _status_color(summary.run.status)
                )
                ui.label(summary.workspace_name or "–").classes("w-40")
                ui.label(summary.user_name or "–").classes("w-32")
                ui.label(_counts(summary)).classes("flex-1 text-grey")
                action_button(
                    "visibility",
                    t("Lauf öffnen"),
                    lambda run_id=int(summary.run.id): ui.navigate.to(f"{LIST_ROUTE}/{run_id}"),
                )

        def purge_job() -> int:
            with session_scope(session_factory) as session:
                return purge_change_values(session)

        async def purge() -> None:
            try:
                removed = await run.io_bound(purge_job)
            except Exception as exc:  # noqa: BLE001 - Meldung in der Seite
                ui.notify(describe_error(exc), color="negative")
                return
            ui.notify(t("{count} Feldwerte entfernt.", count=removed))

        with ui.row().classes("w-full items-center gap-1"):
            action_button("cleaning_services", t("Alte Feldwerte entfernen"), purge)

    @ui.page(LIST_ROUTE + "/{run_id}")
    def run_page(run_id: int) -> None:  # pyright: ignore[reportUnusedFunction]
        apply_palette()
        apply_locale()
        user = current_user(session_factory)
        if user is None:
            redirect_to_login()
            return

        with session_scope(session_factory) as session:
            stored = session.get(Run, run_id)
            if stored is None:
                page_header(t("Läufe"), user)
                ui.label(t("Der Lauf wurde nicht gefunden.")).classes("text-negative")
                return
            rows = [describe_change(row) for row in run_changes(session, stored.id)]
            header = (
                f"{stored.kind.value}/{stored.mode.value} · {stored.status.value} · "
                f"{stored.started_at:%d.%m.%Y %H:%M}"
            )
            status = stored.status

        page_header(t("Lauf {run}", run=run_id), user)
        ui.label(header).classes("text-sm")
        if status is not RunStatus.OK:
            ui.label(
                t("Nur wirksame Felder werden zurückgenommen; der Rest bleibt unberührt.")
            ).classes("text-warning text-sm")

        if not rows:
            ui.label(t("Dieser Lauf hat keine Feldänderungen.")).classes("text-sm")
        for row in rows:
            with ui.row().classes("w-full items-center gap-3 border-b py-1 text-sm"):
                ui.label(row["file_id"]).classes("w-28 text-grey")
                ui.label(row["field"]).classes("w-56 font-medium")
                ui.label(row["old"] or "–").classes("flex-1 text-grey")
                ui.label("→").classes("text-grey")
                ui.label(row["new"] or "–").classes("flex-1")
                ui.label(row["status"]).classes(
                    "w-24 " + ("text-positive" if row["status"] == "ok" else "text-warning")
                )
                if row["error"]:
                    ui.label(row["error"]).classes("text-negative")

        ok_count = sum(1 for row in rows if row["status"] == "ok")

        def undo_job() -> tuple[int, int, int, int]:
            with session_scope(session_factory) as session:
                stored_run = session.get(Run, run_id)
                actor = session.get(AppUser, user.id)
                if stored_run is None or actor is None or stored_run.profile_id is None:
                    raise ValueError(t("Der Lauf wurde nicht gefunden."))
                profile = session.get(Profile, stored_run.profile_id)
                if profile is None:
                    raise ValueError(t("Das Profil des Laufs fehlt."))
                report = prepare_undo(
                    session,
                    stored_run,
                    schema_cache.get(profile),
                    client_factory.client_for(profile),
                    actor=actor,
                )
                return (
                    report.workspace_id,
                    report.changed,
                    len(report.skipped_diverged),
                    len(report.skipped_status),
                )

        async def undo() -> None:
            try:
                outcome = await run.io_bound(undo_job)
            except Exception as exc:  # noqa: BLE001 - Meldung in der Seite
                ui.notify(describe_error(exc), color="negative")
                return
            if outcome is None:
                return
            workspace_id, changed, diverged, skipped = outcome
            ui.notify(
                t(
                    "{count} Felder für das Undo vorbereitet ({diverged} abweichend, "
                    "{status} nicht wirksam).",
                    count=changed,
                    diverged=diverged,
                    status=skipped,
                )
            )
            ui.navigate.to(f"/workspaces/{workspace_id}/review")

        with ui.row().classes("w-full items-center gap-1"):
            if ok_count:
                action_button("undo", t("Undo vorbereiten"), undo)
            action_button(
                "arrow_back", t("Zurück zu den Läufen"), lambda: ui.navigate.to(LIST_ROUTE)
            )


__all__ = ["LIST_ROUTE", "register_run_pages"]
