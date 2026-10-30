"""NiceGUI-Seiten fuer Abfrage-Scripts.

Liste und Editor mit Pruefen, Dry Run, Speichern (neue Version) und Veroeffentlichen.
Ausgefuehrt wird immer in einem Kindprozess; die UI sieht nur Ergebnis und Protokoll.
"""

from __future__ import annotations

import json
from typing import Any

from nicegui import run, ui
from sqlalchemy import select

from app.crypto import SecretBox
from app.db import SessionFactory, session_scope
from app.i18n import describe_error, t
from app.models import AppUser, Profile, QueryScript, QueryScriptVersion, Role
from app.models.enums import RunSource
from app.profiles import ProfileError
from app.scripts.contract import ParamSpec, coerce_params
from app.scripts.errors import ScriptError
from app.scripts.runner import ScriptOutcome, ScriptRunner
from app.scripts.service import (
    can_edit_scripts,
    create_script,
    ensure_templates,
    get_script,
    interface_for,
    latest_version,
    list_scripts,
    publish_version,
    published_version,
    record_run,
    save_version,
)
from app.scripts.templates import TEMPLATES
from app.ui.guard import current_user, redirect_to_login
from app.ui.shell import apply_locale, apply_palette, page_header
from app.ui.widgets import action_button

ROW_CLASSES = "w-full items-center gap-3 border-b py-1 text-sm"
STARTER = '''"""Neue Abfrage."""

PARAMS = {
    "collection": {"type": "str", "label": "Collection (Name oder ID)", "required": True},
}


def query(px, params):
    col = px.collection(params["collection"])
    px.log(f"Collection '{col['name']}' (ID {col['id']})")
    return px.filters.collection(col["id"])
'''


def _profiles_for(session_factory: SessionFactory, user: AppUser) -> dict[int, str]:
    with session_scope(session_factory) as session:
        account = session.get(AppUser, user.id)
        if account is None:
            return {}
        if account.role is Role.SUPERUSER:
            rows = session.scalars(select(Profile).where(Profile.is_active.is_(True)))
            return {profile.id: profile.name for profile in rows}
        return {profile.id: profile.name for profile in account.profiles if profile.is_active}


def _load_profile(session_factory: SessionFactory, profile_id: int) -> tuple[Any, ...]:
    with session_scope(session_factory) as session:
        profile = session.get(Profile, profile_id)
        if profile is None:
            raise ProfileError("Das Profil wurde nicht gefunden.")
        return (
            profile.id,
            profile.host,
            profile.api_key_enc,
            profile.max_retries,
            profile.max_rows,
        )


def _run_summary(outcome: ScriptOutcome, *, max_rows: int) -> str:
    """Kurzfassung eines Laufs für die Statuszeile."""
    if not outcome.ok:
        return t("Fehler: {message}", message=outcome.error or "")
    parts = [t("{ms} ms", ms=outcome.duration_ms)]
    if outcome.result and outcome.result.ids:
        parts.append(t("{count} IDs", count=len(outcome.ids)))
    if outcome.filter:
        parts.append(t("Filter:") + " " + json.dumps(outcome.filter, ensure_ascii=False))
    if outcome.columns:
        parts.append(t("{count} Spalten", count=len(outcome.columns)))
    parts.append(t("Limit {rows} Zeilen", rows=max_rows))
    return " | ".join(parts)


def register_script_pages(
    session_factory: SessionFactory,
    secret_box: SecretBox,
    runner: ScriptRunner,
) -> None:
    @ui.page("/scripts")
    def scripts_page() -> None:  # pyright: ignore[reportUnusedFunction]
        apply_palette()
        apply_locale()
        user = current_user(session_factory)
        if user is None:
            redirect_to_login()
            return
        page_header(t("Scripts"), user)
        editable = can_edit_scripts(user)
        with session_scope(session_factory) as session:
            ensure_templates(session, owner=session.get(AppUser, user.id))
        status = ui.label("").classes("text-sm")

        @ui.refreshable
        def script_rows() -> None:
            with session_scope(session_factory) as session:
                rows = [
                    {
                        "id": script.id,
                        "name": script.name,
                        "description": script.description or "",
                        "published": published_version(session, script),
                        "versions": len(script.versions),
                        "template": script.is_template,
                    }
                    for script in list_scripts(session)
                ]
            if not rows:
                ui.label(t("Noch keine Scripts vorhanden.")).classes("text-sm")
                return
            for row in rows:
                published: QueryScriptVersion | None = row["published"]
                with ui.row().classes(ROW_CLASSES):
                    ui.label(row["name"]).classes("w-44 font-medium")
                    ui.label(row["description"]).classes("w-64 text-xs")
                    version_text = (
                        t("v{version}", version=published.version_no)
                        if published is not None
                        else t("nicht veröffentlicht")
                    )
                    ui.label(version_text).classes("w-32 text-xs")
                    ui.label(t("{count} Versionen", count=row["versions"])).classes("w-24 text-xs")
                    ui.label(t("Vorlage") if row["template"] else "").classes("w-20 text-xs")
                    action_button(
                        "edit",
                        t("Öffnen"),
                        lambda script_id=int(row["id"]): ui.navigate.to(f"/scripts/{script_id}"),
                    )
                    if row["template"] and editable:
                        action_button(
                            "content_copy",
                            t("Vorlage kopieren"),
                            lambda script_id=int(row["id"]): _copy_template(script_id),
                        )

        def _copy_template(script_id: int) -> None:
            with session_scope(session_factory) as session:
                template = session.get(QueryScript, script_id)
                actor = session.get(AppUser, user.id)
                if template is None or actor is None:
                    return
                template_version = published_version(session, template) or latest_version(
                    session, template
                )
                if template_version is None:
                    status.set_text(t("Die Vorlage hat keine Version."))
                    return
                source = template_version.source
                base_name = f"{template.name} (Kopie)"
                name = base_name
                counter = 2
                existing = {row.name for row in list_scripts(session)}
                while name in existing:
                    name = f"{base_name} {counter}"
                    counter += 1
                try:
                    created = create_script(
                        session,
                        name=name,
                        source=source,
                        actor=actor,
                        description=template.description,
                    )
                except ScriptError as exc:
                    status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                    return
                new_id = created.id
            status.set_text(t("Kopie '{name}' angelegt.", name=name))
            ui.navigate.to(f"/scripts/{new_id}")

        with ui.row().classes("w-full items-center gap-2 mt-2"):
            ui.label(t("Verfügbare Scripts")).classes("font-semibold")
            if editable:
                action_button(
                    "add", t("Neues Script"), lambda: ui.navigate.to("/scripts/0")
                ).classes("ml-auto")
        script_rows()

    @ui.page("/scripts/{script_id}")
    def editor_page(script_id: int) -> None:  # pyright: ignore[reportUnusedFunction]
        apply_palette()
        apply_locale()
        user = current_user(session_factory)
        if user is None:
            redirect_to_login()
            return
        editable = can_edit_scripts(user)
        state: dict[str, Any] = {"script": None, "version": None, "template": False}
        if script_id:
            try:
                with session_scope(session_factory) as session:
                    script = get_script(session, script_id)
                    shown = published_version(session, script) or latest_version(session, script)
                    state.update(
                        script=script.name,
                        template=script.is_template,
                        description=script.description,
                    )
                    state["source"] = shown.source if shown is not None else ""
                    state["version"] = shown.version_no if shown is not None else None
                    state["versions"] = [
                        {
                            "id": version.id,
                            "label": t("v{version}", version=version.version_no)
                            + (
                                " " + t("(veröffentlicht)")
                                if version.id == script.current_version_id
                                else ""
                            ),
                            "source": version.source,
                        }
                        for version in script.versions
                    ]
            except ScriptError as exc:
                page_header(t("Scripts"), user)
                ui.label(t("Fehler: {message}", message=describe_error(exc))).classes(
                    "text-negative"
                )
                return
        else:
            state.update(source=STARTER, versions=[], description=None)

        page_header(state["script"] or t("Neues Script"), user)
        if state["version"] is not None:
            ui.label(t("Angezeigt: v{version}", version=state["version"])).classes("text-xs")
        if state["template"]:
            ui.label(t("Vorlagen sind unveränderlich – bitte eine Kopie anlegen.")).classes(
                "text-xs text-warning"
            )
        status = ui.label("").classes("text-sm")
        log_box = ui.code("").classes("w-full")
        log_box.set_visibility(False)
        result_label = ui.label("").classes("text-sm")
        result_label.set_visibility(False)

        profiles = _profiles_for(session_factory, user)
        profile_select = ui.select(profiles, label=t("Profil"), value=next(iter(profiles), None))
        profile_select.props("outlined dense").classes("w-64")
        if not profiles:
            profile_select.set_visibility(False)
            ui.label(
                t("Keinem Profil zugeordnet – ein Superuser muss ein Profil zuweisen.")
            ).classes("text-xs text-warning")

        name_input = ui.input(t("Name"), value=state["script"] or "").props("outlined dense")
        name_input.set_visibility(script_id == 0)
        editor: Any = None
        code_view: Any = None
        if editable:
            editor = (
                ui.codemirror(state["source"], language="Python")
                .classes("w-full")
                .style("min-height: 380px")
            )
        else:
            ui.label(t("Veröffentlichte Fassung (nur lesbar)")).classes("text-xs")
            code_view = ui.code(state["source"], language="python").classes("w-full")

        def current_source() -> str:
            return editor.value if editor is not None else str(state["source"])

        def show_source(text: str) -> None:
            state["source"] = text
            if editor is not None:
                editor.set_value(text)
            elif code_view is not None:
                code_view.set_content(text)

        params_container = ui.column().classes("w-full gap-2")
        param_widgets: dict[str, Any] = {}

        def _load_version(version_id: object) -> None:
            text = _source_of(state["versions"], version_id)
            if text:
                show_source(text)
                build_params()

        def build_params() -> None:
            params_container.clear()
            param_widgets.clear()
            try:
                specs, _columns = interface_for(current_source(), runner)
            except ScriptError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            with params_container:
                if not specs:
                    ui.label(t("Dieses Script hat keine Parameter.")).classes("text-xs")
                    return
                ui.label(t("Parameter")).classes("font-semibold")
                for spec in specs.values():
                    param_widgets[spec.name] = _param_widget(spec)

        def _param_widget(spec: ParamSpec) -> Any:
            if spec.type == "bool":
                return ui.switch(spec.title, value=bool(spec.default))
            if spec.type in {"int", "float"}:
                return ui.number(
                    spec.title, value=spec.default, format="%d" if spec.type == "int" else None
                )
            widget = ui.input(spec.title, value="" if spec.default is None else str(spec.default))
            if spec.help:
                widget.tooltip(spec.help)
            if spec.required:
                widget.props("outlined dense")
            return widget

        def collect_params() -> dict[str, Any]:
            return {name: widget.value for name, widget in param_widgets.items()}

        def check() -> None:
            try:
                interface = runner.inspect(current_source())
            except ScriptError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            build_params()
            columns = ", ".join(interface.columns or []) or t("keine")
            status.set_text(
                t(
                    "Script ist gültig: {params} Parameter, Spalten: {columns}.",
                    params=len(interface.params),
                    columns=columns,
                )
            )

        async def dry_run() -> None:
            if not profiles:
                status.set_text(t("Kein Profil zugewiesen."))
                return
            profile_id = profile_select.value
            if not isinstance(profile_id, int):
                status.set_text(t("Bitte ein Profil auswählen."))
                return
            try:
                interface = runner.inspect(current_source())
                typed = coerce_params(interface.params, collect_params())
            except ScriptError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            try:
                _, host, api_key_enc, max_retries, max_rows = _load_profile(
                    session_factory, profile_id
                )
                api_key = secret_box.decrypt(api_key_enc)
            except ScriptError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            status.set_text(t("Lauf gestartet …"))
            source = current_source()
            outcome = await run.io_bound(
                lambda: runner.run(
                    source,
                    typed,
                    host=host,
                    api_key=api_key,
                    max_rows=max_rows,
                    max_retries=max_retries,
                )
            )
            if outcome is None:  # pragma: no cover - io_bound liefert immer ein Ergebnis
                status.set_text(t("Der Lauf wurde abgebrochen."))
                return
            with session_scope(session_factory) as session:
                record_run(
                    session,
                    user=session.get(AppUser, user.id),
                    profile_id=profile_id,
                    script_version_id=_version_id(session_factory, script_id),
                    source=RunSource.GRID,
                    params=typed,
                    outcome=outcome,
                )
            status.set_text(
                (t("Dry Run: ") if outcome.ok else "") + _run_summary(outcome, max_rows=max_rows)
            )
            log_box.set_content(outcome.log or t("(keine Ausgabe)"))
            log_box.set_visibility(bool(outcome.log))
            result_label.set_text(_result_text(outcome))
            result_label.set_visibility(True)

        def _result_text(outcome: ScriptOutcome) -> str:
            if not outcome.ok:
                return t("Fehler: {message}", message=outcome.error or "")
            if outcome.result and outcome.result.ids:
                preview = ", ".join(str(item) for item in outcome.ids[:10])
                suffix = " …" if len(outcome.ids) > 10 else ""
                return t("IDs: {preview}{suffix}", preview=preview, suffix=suffix)
            note = outcome.result.note if outcome.result and outcome.result.note else ""
            return f"{t('Filter:')} {outcome.filter} {note}".strip()

        def save(publish: bool) -> None:
            try:
                with session_scope(session_factory) as session:
                    actor = session.get(AppUser, user.id)
                    if actor is None:
                        return
                    if script_id == 0:
                        script = create_script(
                            session,
                            name=name_input.value or "",
                            source=current_source(),
                            actor=actor,
                            publish=publish,
                        )
                        new_id = script.id
                        message = t("Script '{name}' angelegt.", name=script.name)
                    else:
                        if state["template"]:
                            raise ScriptError("Vorlagen sind unveraenderlich.")
                        script = session.get(QueryScript, script_id)
                        if script is None:
                            raise ScriptError("Das Script wurde nicht gefunden.")
                        version = save_version(
                            session, script, current_source(), actor=actor, publish=publish
                        )
                        new_id = script.id
                        message = t("Version v{version} gespeichert.", version=version.version_no)
            except ScriptError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            status.set_text(message + (" " + t("(veröffentlicht)") if publish else ""))
            if script_id == 0:
                ui.navigate.to(f"/scripts/{new_id}")

        def publish_current() -> None:
            try:
                with session_scope(session_factory) as session:
                    actor = session.get(AppUser, user.id)
                    script = session.get(QueryScript, script_id) if script_id else None
                    if actor is None or script is None:
                        raise ScriptError(t("Das Script wurde nicht gefunden."))
                    version = latest_version(session, script)
                    if version is None:
                        raise ScriptError(t("Es gibt noch keine Version."))
                    publish_version(session, script, version, actor=actor)
                    number = version.version_no
            except ScriptError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            status.set_text(t("Version v{version} ist jetzt veröffentlicht.", version=number))

        with ui.row().classes("w-full items-center gap-2 mt-2"):
            action_button("rule", t("Prüfen"), check)
            action_button("play_arrow", t("Dry Run"), dry_run)
            if editable:
                action_button("save", t("Speichern (neue Version)"), lambda: save(False))
                action_button("publish", t("Speichern und veröffentlichen"), lambda: save(True))
                if script_id:
                    action_button(
                        "verified", t("Aktuelle Version veröffentlichen"), publish_current
                    )
            if state["versions"]:
                version_select = ui.select(
                    {item["id"]: item["label"] for item in state["versions"]},
                    label=t("Version laden"),
                    value=None,
                ).props("outlined dense")
                version_select.classes("w-56")
                version_select.on_value_change(lambda event: _load_version(event.value))

        build_params()

    def _version_id(_session_factory: SessionFactory, script_id: int) -> int | None:
        if not script_id:
            return None
        with session_scope(_session_factory) as session:
            script = session.get(QueryScript, script_id)
            if script is None:
                return None
            version = published_version(session, script) or latest_version(session, script)
            return version.id if version is not None else None


def _source_of(versions: list[dict[str, Any]], version_id: object) -> str:
    for item in versions:
        if item["id"] == version_id:
            return str(item["source"])
    return ""


__all__ = ["STARTER", "TEMPLATES", "register_script_pages"]
