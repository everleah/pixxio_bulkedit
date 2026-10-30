"""NiceGUI-Seiten für Arbeitsbestände und das Grid.

`/workspaces` listet offene Entwürfe und legt neue an; `/workspaces/{id}` zeigt das
Grid. Die Zeilen liefert ein FastAPI-Endpunkt im effektiven Stand; Zelländerungen
schreibt die Seite direkt in den ChangeSet.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from nicegui import app as nicegui_app
from nicegui import run, ui
from sqlalchemy import select

from app.clients import ClientFactory
from app.colors import PALETTE, TEXT_STYLE
from app.crypto import SecretBox
from app.db import SessionFactory, session_scope
from app.i18n import describe_error, get_locale, t
from app.models import (
    AppUser,
    Profile,
    QueryScript,
    QueryScriptVersion,
    Role,
    Workspace,
    WorkspaceAsset,
)
from app.models.enums import RunSource, WorkspaceStatus
from app.schema import ColumnDef, ProfileSchema, SchemaCache, resolve_columns
from app.scripts.contract import coerce_params
from app.scripts.errors import ScriptError
from app.scripts.runner import ScriptRunner
from app.scripts.service import (
    interface_for,
    list_scripts,
    published_version,
    record_run,
)
from app.ui.guard import current_user, redirect_to_login
from app.ui.shell import apply_locale, apply_palette, page_header
from app.ui.widgets import action_button
from app.workspaces import (
    EXPIRY_WARNING_DAYS,
    MAX_SELECTED_COLUMNS,
    WorkspaceConflictError,
    WorkspaceError,
    bulk_set,
    changed_changes,
    changed_count,
    clear_changes,
    clear_columns,
    close_workspace,
    create_workspace,
    delete_workspace,
    effective_page,
    expiry_warning_days,
    list_workspaces,
    load_assets,
    merge_snapshot_values,
    missing_columns,
    reopen_workspace,
    resolve_targets,
    set_change,
    store_columns,
    store_snapshot,
    stored_columns,
)
from app.xlsx import (
    MAX_FILE_BYTES,
    XlsxError,
    build_error_workbook,
    document_summary,
    export_workbook,
    has_snapshot,
    import_workbook,
    parse_workbook,
)

ROWS_ROUTE = "/workspace/rows"
CHANGES_ROUTE = "/workspace/changes"
LIST_ROUTE = "/workspaces"
BLOCK_SIZE = 100
MAX_BLOCK_SIZE = 500
DEFAULT_COLUMNS = ("std:fileName", "std:subject", "std:description")
DEFAULT_CUSTOM_COLUMNS = 12
# Gruppen der Spaltenauswahl: Quelle und deutscher Quelltext des Gruppentitels.
COLUMN_GROUPS: tuple[tuple[str, str], ...] = (
    ("file_attr", "Standardattribute"),
    ("custom", "Eigene Metadatenfelder"),
    ("standard", "Standard-Metadatenfelder"),
)
ROW_CLASSES = "w-full items-center gap-3 border-b py-1 text-sm"
MIN_COLUMN_WIDTH = 80
EDITABLE_EDIT_TYPES = frozenset(
    {"text", "none", "number", "date", "boolean", "selection", "multiselection", "language"}
)
# Merker fuer die Spalte, die nach dem Uebernehmen der Auswahl sichtbar geschoben wird.
SCROLL_HINT_KEY = "grid_scroll_hint"

GRID_HEAD = f"""
<style>
  body .q-page {{
    padding: 0;
  }}
  body .nicegui-content {{
    height: 100vh;
    padding: 0.5rem;
    box-sizing: border-box;
    gap: 0.5rem;
  }}
  body .ws-grid {{
    flex: 1 1 0;
    min-height: 320px;
    --ag-foreground-color: {PALETTE.text};
    --ag-background-color: #ffffff;
    --ag-header-background-color: {PALETTE.page_background};
    --ag-header-foreground-color: {PALETTE.text};
    --ag-odd-row-background-color: #f8fafc;
    --ag-row-hover-color: #e6f6ec;
    --ag-selected-row-background-color: {PALETTE.surface_success};
    --ag-border-color: #cbd5e1;
    --ag-checkbox-checked-color: {PALETTE.primary};
    --ag-input-focus-border-color: {PALETTE.primary};
  }}
  body .ws-cell-changed {{
    background: {PALETTE.surface_success} !important;
    font-weight: 600;
  }}
  body .ws-row-changed {{
    box-shadow: inset 3px 0 0 {PALETTE.primary};
  }}
  .ws-conflict {{
    display: none;
    background: {PALETTE.warning};
    color: #1f2937;
    padding: 0.35rem 0.6rem;
    border-radius: 0.25rem;
    font-size: 0.85rem;
  }}
</style>
"""

GRID_SCRIPT = """
<script>
window.__ws = window.__ws || {};
Object.assign(window.__ws, {
  workspaceId: %(workspace_id)s,
  revision: %(revision)s,
  cells: {},
  filter: '',
  filterKey: '',
  onlyChanged: false,
  hasChanged: (fileId, key) => (window.__ws.cells[String(fileId)] || []).includes(key),
  setFilter: (filter, key, onlyChanged) => {
    window.__ws.filter = filter;
    window.__ws.filterKey = key;
    window.__ws.onlyChanged = onlyChanged;
  },
  currentRevision: () => window.__ws.revision,
  loadChanges: () => fetch('%(changes_route)s?workspaceId=' + String(window.__ws.workspaceId))
    .then((response) => response.json())
    .then((data) => {
      window.__ws.cells = data.cells || {};
      window.__ws.revision = data.revision;
    }),
  datasource: {
    getRows: (params) => {
      const sort = (params.sortModel && params.sortModel[0]) || {};
      const state = window.__ws;
      const query = new URLSearchParams({
        workspaceId: String(state.workspaceId),
        start: String(params.startRow),
        count: String(params.endRow - params.startRow),
        sortKey: sort.colId || '',
        sortDir: sort.sort || '',
        filterKey: state.filterKey || '',
        filter: state.filter || '',
        onlyChanged: state.onlyChanged ? '1' : '0',
      });
      fetch('%(rows_route)s?' + query.toString())
        .then((response) => response.json())
        .then((data) => {
          params.successCallback(data.rows, data.rowCount);
          if (data.revision !== state.revision) {
            const banner = document.getElementById('ws-conflict');
            if (banner) { banner.style.display = 'block'; }
          }
        })
        .catch(() => params.failCallback());
    },
  },
});
</script>
"""


GRID_LOCALE_DE: dict[str, str] = {
    "loadingOoo": "Lädt …",
    "noRowsToShow": "Keine Zeilen",
    "selectAll": "Alle auswählen",
    "blanks": "Leer",
    "filterOoo": "Filter …",
    "applyFilter": "Anwenden",
    "resetFilter": "Zurücksetzen",
    "clearFilter": "Löschen",
    "contains": "enthält",
    "notContains": "enthält nicht",
    "equals": "gleich",
    "notEqual": "ungleich",
    "lessThan": "kleiner als",
    "greaterThan": "größer als",
    "page": "Seite",
    "ariaRowToggleSelection": "Leertaste drücken, um die Zeilenauswahl umzuschalten",
    "ariaRowSelect": "Zeile auswählen",
    "ariaRowDeselect": "Zeilenauswahl aufheben",
}


def _api_user(session_factory: SessionFactory) -> AppUser | None:
    try:
        payload = nicegui_app.storage.user
    except RuntimeError:  # pragma: no cover - kein Session-Kontext
        return None
    if not payload:
        return None
    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        return None
    with session_scope(session_factory) as session:
        user = session.get(AppUser, user_id)
        if user is None or not user.is_active:
            return None
        return user


def owned_workspace(session: Any, workspace_id: int, user: AppUser) -> Workspace | None:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        return None
    if workspace.owner_id != user.id and user.role is not Role.SUPERUSER:
        return None
    return workspace


def _column_for(columns: Sequence[ColumnDef], key: object) -> ColumnDef | None:
    if not isinstance(key, str):
        return None
    return next((column for column in columns if column.key == key), None)


def column_sort_key(column: ColumnDef) -> tuple[str, str]:
    """Sortierschluessel fuer Anzeigenamen; Umlaute zaehlen wie ihr Grundbuchstabe."""
    plain = unicodedata.normalize("NFKD", column.label).encode("ascii", "ignore").decode("ascii")
    return plain.casefold(), column.label.casefold()


def grouped_columns(columns: Sequence[ColumnDef]) -> dict[str, list[ColumnDef]]:
    """Spalten je Gruppe, innerhalb der Gruppe nach Anzeigename sortiert."""
    return {
        source: sorted(
            (column for column in columns if column.source == source), key=column_sort_key
        )
        for source, _title in COLUMN_GROUPS
    }


def ordered_keys(
    current: Sequence[str], chosen: set[str], dialog_order: Sequence[str]
) -> list[str]:
    """Auswahlreihenfolge: bestehende Spalten bleiben, neue kommen in Dialogreihenfolge dazu."""
    ordered = [key for key in current if key in chosen]
    ordered.extend(key for key in dialog_order if key in chosen and key not in ordered)
    return ordered


def workspace_columns(
    schema: ProfileSchema,
    script_columns: Sequence[str] | None,
    selected: Sequence[str] | None = None,
) -> list[ColumnDef]:
    """Spalten des Arbeitsbestands.

    Reihenfolge der Quellen: gespeicherte Auswahl, ``COLUMNS`` des Scripts, Standardspalten.
    """
    if selected:
        resolved_selected, _unknown = resolve_columns(schema, list(selected))
        if resolved_selected:
            return resolved_selected
    if script_columns:
        resolved, _unknown = resolve_columns(schema, list(script_columns))
        if resolved:
            return resolved
    resolved_default, _ = resolve_columns(schema, list(DEFAULT_COLUMNS))
    seen = {column.key for column in resolved_default}
    custom = [column for column in schema.custom[:DEFAULT_CUSTOM_COLUMNS]]
    resolved_custom, _ = resolve_columns(schema, [f"custom:{field.id}" for field in custom])
    return resolved_default + [column for column in resolved_custom if column.key not in seen]


def view_columns(session: Any, workspace: Workspace, schema: ProfileSchema) -> list[ColumnDef]:
    """Spalten eines Arbeitsbestands inklusive gespeicherter Auswahl."""
    return workspace_columns(
        schema,
        script_column_keys(session, workspace),
        stored_columns(workspace),
    )


def column_def(column: ColumnDef) -> dict[str, Any]:
    """AG-Grid-Spaltendefinition mit Editor je Feldtyp."""
    definition: dict[str, Any] = {
        "field": column.key,
        "headerName": column.label,
        "width": 190,
        "editable": bool(column.writable and column.edit_type in EDITABLE_EDIT_TYPES),
        "cellClassRules": {
            "ws-cell-changed": "!!data && window.__ws.hasChanged(data.fileId, colDef.field)",
        },
    }
    if column.edit_type == "number":
        definition["cellEditor"] = "agTextCellEditor"
        definition["headerTooltip"] = t("Zahl, Dezimaltrennzeichen Komma oder Punkt")
    elif column.edit_type == "date":
        definition["cellEditor"] = "agTextCellEditor"
        definition["headerTooltip"] = t("Datum als JJJJ-MM-TT oder TT.MM.JJJJ, Uhrzeit HH:MM:SS")
    elif column.edit_type == "boolean":
        definition["cellEditor"] = "agCheckboxCellEditor"
    elif column.edit_type == "selection":
        definition["cellEditor"] = "agSelectCellEditor"
        definition["cellEditorParams"] = {"values": list(column.options)}
    elif column.edit_type in {"multiselection", "language"}:
        definition["cellEditor"] = "agTextCellEditor"
        definition["headerTooltip"] = t("Mehrere Werte mit Komma trennen")
    else:
        definition["cellEditor"] = "agTextCellEditor"
    return definition


def script_column_keys(session: Any, workspace: Workspace) -> list[str] | None:
    if workspace.script_version_id is None:
        return None
    version = session.get(QueryScriptVersion, workspace.script_version_id)
    if version is None:
        return None
    try:
        _params, columns = interface_for(version.source)
    except ScriptError:
        return None
    return columns


def script_label(session: Any, workspace: Workspace) -> str:
    """Name des Scripts zu einem Arbeitsbestand (für Dateinamen und Export-Info)."""
    if workspace.script_version_id is None:
        return ""
    version = session.get(QueryScriptVersion, workspace.script_version_id)
    if version is None:
        return ""
    script = session.get(QueryScript, version.script_id)
    return script.name if script is not None else ""


def _take_scroll_hint() -> dict[str, Any] | None:
    """Holt den Merker fuer die neu hinzugefuegte Spalte und loescht ihn."""
    try:
        storage = nicegui_app.storage.user
        hint = storage.get(SCROLL_HINT_KEY)
        if hint is None:
            return None
        del storage[SCROLL_HINT_KEY]
    except RuntimeError, KeyError:  # pragma: no cover - kein Session-Kontext
        return None
    return hint if isinstance(hint, dict) else None


def _store_scroll_hint(workspace_id: int, key: str) -> None:
    """Merkt sich die neu uebernommene Spalte, damit sie nach dem Neuladen sichtbar wird."""
    try:
        nicegui_app.storage.user[SCROLL_HINT_KEY] = {"workspace": workspace_id, "key": key}
    except RuntimeError:  # pragma: no cover - kein Session-Kontext
        return


def _profiles_for(session_factory: SessionFactory, user: AppUser) -> dict[int, str]:
    with session_scope(session_factory) as session:
        account = session.get(AppUser, user.id)
        if account is None:
            return {}
        if account.role is Role.SUPERUSER:
            rows = session.scalars(select(Profile).where(Profile.is_active.is_(True)))
            return {profile.id: profile.name for profile in rows}
        return {profile.id: profile.name for profile in account.profiles if profile.is_active}


def register_workspace_pages(
    session_factory: SessionFactory,
    secret_box: SecretBox,
    schema_cache: SchemaCache,
    client_factory: ClientFactory,
    runner: ScriptRunner,
) -> None:
    @nicegui_app.get(ROWS_ROUTE)
    async def rows(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        user = _api_user(session_factory)
        if user is None:
            return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
        params = request.query_params
        try:
            workspace_id = int(params.get("workspaceId", "0"))
            start = max(0, int(params.get("start", "0") or 0))
            count = min(
                MAX_BLOCK_SIZE, max(1, int(params.get("count", str(BLOCK_SIZE)) or BLOCK_SIZE))
            )
        except ValueError:
            return JSONResponse({"error": "ungueltige Anfrage"}, status_code=400)
        with session_scope(session_factory) as session:
            workspace = owned_workspace(session, workspace_id, user)
            if workspace is None:
                return JSONResponse({"error": "nicht gefunden"}, status_code=404)
            profile = session.get(Profile, workspace.profile_id)
            if profile is None:
                return JSONResponse({"error": "Profil fehlt"}, status_code=409)
            schema = schema_cache.get(profile)
            columns = view_columns(session, workspace, schema)
            if not columns:
                return JSONResponse({"error": "keine Spalten"}, status_code=409)
            sort_column = _column_for(columns, params.get("sortKey")) or columns[0]
            filter_column = _column_for(columns, params.get("filterKey")) or sort_column
            page = effective_page(
                session,
                workspace,
                start=start,
                count=count,
                sort_column=sort_column,
                descending=(params.get("sortDir") or "") == "desc",
                filter_column=filter_column,
                filter_value=params.get("filter") or "",
                only_changed=(params.get("onlyChanged") or "0") == "1",
                columns=columns,
            )
        return JSONResponse({"rows": page.rows, "rowCount": page.total, "revision": page.revision})

    @nicegui_app.get(CHANGES_ROUTE)
    async def changes(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        user = _api_user(session_factory)
        if user is None:
            return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
        try:
            workspace_id = int(request.query_params.get("workspaceId", "0"))
        except ValueError:
            return JSONResponse({"error": "ungueltige Anfrage"}, status_code=400)
        with session_scope(session_factory) as session:
            workspace = owned_workspace(session, workspace_id, user)
            if workspace is None:
                return JSONResponse({"error": "nicht gefunden"}, status_code=404)
            cells: dict[str, list[str]] = {}
            for entry in changed_changes(session, workspace.id):
                cells.setdefault(str(entry.file_id), []).append(entry.key)
            payload = {
                "cells": cells,
                "revision": int(workspace.edit_revision),
                "count": changed_count(session, workspace.id),
            }
        return JSONResponse(payload)

    @ui.page(LIST_ROUTE)
    def workspaces_page() -> None:  # pyright: ignore[reportUnusedFunction]
        apply_palette()
        apply_locale()
        user = current_user(session_factory)
        if user is None:
            redirect_to_login()
            return
        page_header(t("Arbeitsbestände"), user)
        status = ui.label("").classes("text-sm")
        profiles = _profiles_for(session_factory, user)
        with session_scope(session_factory) as session:
            script_options = {
                script.id: script.name
                for script in list_scripts(session)
                if published_version(session, script) is not None
            }

        with ui.row().classes("w-full items-end gap-2 mt-2"):
            script_select = (
                ui.select(script_options, label=t("Script"), value=next(iter(script_options), None))
                .props("outlined dense")
                .classes("w-56")
            )
            profile_select = (
                ui.select(profiles, label=t("Profil"), value=next(iter(profiles), None))
                .props("outlined dense")
                .classes("w-48")
            )
            name_input = ui.input(t("Name (optional)")).props("outlined dense").classes("w-56")
            load_button = action_button("download", t("Arbeitsbestand laden"))
            import_button = action_button("upload_file", t("Excel importieren"))
        params_container = ui.column().classes("w-full gap-2")
        param_widgets: dict[str, Any] = {}

        def build_params() -> None:
            params_container.clear()
            param_widgets.clear()
            script_id = script_select.value
            if not isinstance(script_id, int):
                return
            with session_scope(session_factory) as session:
                script = session.get(QueryScript, script_id)
                version = published_version(session, script) if script is not None else None
                source = version.source if version is not None else ""
            try:
                specs, _columns = interface_for(source, runner)
            except ScriptError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            with params_container:
                if not specs:
                    ui.label(t("Dieses Script hat keine Parameter.")).classes("text-xs")
                    return
                for spec in specs.values():
                    if spec.type == "bool":
                        param_widgets[spec.name] = ui.switch(spec.title, value=bool(spec.default))
                    elif spec.type in {"int", "float"}:
                        param_widgets[spec.name] = ui.number(spec.title, value=spec.default)
                    else:
                        param_widgets[spec.name] = (
                            ui.input(
                                spec.title, value="" if spec.default is None else str(spec.default)
                            )
                            .props("outlined dense")
                            .classes("w-80")
                        )

        script_select.on_value_change(lambda _: build_params())
        build_params()

        async def load_workspace() -> None:
            script_id = script_select.value
            profile_id = profile_select.value
            if not isinstance(script_id, int) or not isinstance(profile_id, int):
                status.set_text(t("Bitte Script und Profil auswählen."))
                return
            with session_scope(session_factory) as session:
                script = session.get(QueryScript, script_id)
                version = published_version(session, script) if script is not None else None
                if script is None or version is None:
                    status.set_text(t("Das Script ist nicht veröffentlicht."))
                    return
                source = version.source
                profile = session.get(Profile, profile_id)
                if profile is None:
                    status.set_text(t("Profil nicht gefunden."))
                    return
                host = profile.host
                api_key_enc = profile.api_key_enc
                max_retries = profile.max_retries
                max_rows = profile.max_rows
                script_name = script.name
                specs, script_columns = interface_for(source, runner)
                try:
                    typed = coerce_params(
                        specs, {name: widget.value for name, widget in param_widgets.items()}
                    )
                except ScriptError as exc:
                    status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                    return
            api_key = secret_box.decrypt(api_key_enc)
            status.set_text(t("Script läuft …"))
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
            if outcome is None or not outcome.ok:
                status.set_text(
                    t("Fehler: {message}", message=outcome.error if outcome else t("abgebrochen"))
                )
                return
            status.set_text(t("Assets werden geladen …"))
            try:
                with session_scope(session_factory) as session:
                    actor = session.get(AppUser, user.id)
                    profile = session.get(Profile, profile_id)
                    if actor is None or profile is None:
                        status.set_text(t("Benutzer oder Profil fehlt."))
                        return
                    client = client_factory.client_for(profile)
                    schema = schema_cache.get(profile)
                    columns = workspace_columns(schema, script_columns)
                    workspace = create_workspace(
                        session,
                        owner=actor,
                        profile=profile,
                        name=name_input.value or script_name,
                        script_version=version,
                        params=typed,
                    )
                    assets = await run.io_bound(
                        lambda: load_assets(client, columns, outcome, max_rows=profile.max_rows)
                    )
                    store_snapshot(session, workspace, assets or [])
                    record_run(
                        session,
                        user=actor,
                        profile_id=profile.id,
                        script_version_id=version.id,
                        source=RunSource.GRID,
                        params=typed,
                        outcome=outcome,
                    )
                    workspace_id = workspace.id
                    rows_loaded = workspace.row_count
            except (ScriptError, WorkspaceError) as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            status.set_text(t("{count} Assets geladen.", count=rows_loaded))
            ui.navigate.to(f"/workspaces/{workspace_id}")

        load_button.on_click(load_workspace)

        import_state: dict[str, Any] = {"data": b"", "name": "", "workspace": None}

        with ui.dialog() as import_dialog, ui.card().classes("w-[680px] gap-2"):
            ui.label(t("Excel-Import")).classes("font-semibold text-base")
            ui.label(
                t(
                    "Die Arbeitsmappe stammt aus dem Excel-Export des Bulk-Editors. "
                    "Übernommen werden nur Zellen, die sich gegenüber dem Export geändert haben."
                )
            ).classes("text-xs")
            import_profile = (
                ui.select(profiles, label=t("Profil"), value=next(iter(profiles), None))
                .props("outlined dense")
                .classes("w-64")
            )
            import_upload = (
                ui.upload(
                    label=t("Arbeitsmappe (.xlsx)"),
                    auto_upload=True,
                    max_file_size=MAX_FILE_BYTES,
                )
                .props('accept=".xlsx"')
                .classes("w-full")
            )
            import_summary = ui.column().classes("w-full gap-1 text-sm")
            import_issues = ui.column().classes("w-full gap-0 text-xs")
            import_confirm = ui.checkbox(
                t("Ohne Exportbasis importieren (nur Zwei-Wege-Vergleich)")
            )
            import_confirm.set_visibility(False)
            with ui.row().classes("w-full justify-end gap-2"):
                import_error_file = ui.button(t("Fehlerdatei herunterladen")).props("flat")
                import_error_file.set_visibility(False)
                ui.button(t("Abbrechen"), on_click=import_dialog.close).props("flat")
                import_open = ui.button(
                    t("Zum Arbeitsbestand"),
                    on_click=lambda: ui.navigate.to(f"/workspaces/{import_state['workspace']}"),
                )
                import_open.set_visibility(False)
                import_start = ui.button(t("Importieren")).props("unelevated")
            import_start.disable()

        def _reset_import() -> None:
            import_summary.clear()
            import_issues.clear()
            import_confirm.set_visibility(False)
            import_confirm.value = False
            import_open.set_visibility(False)
            import_error_file.set_visibility(False)
            import_start.disable()
            import_state.update({"data": b"", "name": "", "workspace": None, "issues": []})

        async def uploaded(event: Any) -> None:
            _reset_import()
            data = await event.file.read()
            name = str(getattr(event.file, "name", "") or "")
            profile_id = import_profile.value
            if not name.lower().endswith(".xlsx"):
                with import_summary:
                    ui.label(t("Nur .xlsx-Dateien werden unterstützt.")).style(TEXT_STYLE["error"])
                return
            if not isinstance(profile_id, int):
                with import_summary:
                    ui.label(t("Bitte ein Profil auswählen.")).style(TEXT_STYLE["warning"])
                return

            def parse() -> tuple[Any, bool]:
                with session_scope(session_factory) as session:
                    profile_row = session.get(Profile, profile_id)
                    if profile_row is None:
                        raise WorkspaceError(t("Das Profil fehlt."))
                    schema = schema_cache.get(profile_row)
                    parsed = parse_workbook(data, schema.columns(), max_rows=profile_row.max_rows)
                    return parsed, has_snapshot(session, parsed)

            try:
                outcome = await run.io_bound(parse)
            except (XlsxError, ScriptError, WorkspaceError) as exc:
                with import_summary:
                    ui.label(describe_error(exc)).style(TEXT_STYLE["error"])
                return
            if outcome is None:
                return
            parsed, snapshot = outcome
            import_state.update({"data": data, "name": name, "issues": list(parsed.issues)})
            with import_summary:
                for line in document_summary(parsed):
                    ui.label(line).classes("text-xs")
                if not snapshot:
                    ui.label(
                        t(
                            "Keine Exportbasis gefunden: externe Änderungen können nicht "
                            "erkannt werden, leere Zellen bleiben unberücksichtigt."
                        )
                    ).style(TEXT_STYLE["warning"])
            if parsed.issues:
                with import_issues:
                    ui.label(t("{count} Befunde:", count=len(parsed.issues))).classes(
                        "font-semibold"
                    )
                    for issue in parsed.issues[:50]:
                        ui.label(issue.as_text())
                import_error_file.set_visibility(True)
            if snapshot:
                import_start.enable()
            else:
                import_confirm.set_visibility(True)

        def confirm_changed() -> None:
            if import_confirm.value and import_state["data"]:
                import_start.enable()
            else:
                import_start.disable()

        async def start_import_now() -> None:
            data = import_state["data"]
            profile_id = import_profile.value
            if not data or not isinstance(profile_id, int):
                ui.notify(t("Bitte Profil und Datei auswählen."), color="warning")
                return
            if user.role is Role.VIEWER:
                ui.notify(
                    t("Nur Editor- und Superuser-Rollen dürfen importieren."), color="negative"
                )
                return

            def job() -> Any:
                with session_scope(session_factory) as session:
                    actor = session.get(AppUser, user.id)
                    profile_row = session.get(Profile, profile_id)
                    if actor is None or profile_row is None:
                        raise WorkspaceError(t("Benutzer oder Profil fehlt."))
                    if not profile_row.allow_write:
                        raise WorkspaceError(
                            t("Das Profil ist nur lesbar; ein Import ist nicht möglich.")
                        )
                    client = client_factory.client_for(profile_row)
                    schema = schema_cache.get(profile_row)
                    return import_workbook(
                        session,
                        owner=actor,
                        profile=profile_row,
                        schema=schema,
                        client=client,
                        data=data,
                        filename=import_state["name"],
                    )

            try:
                imported = await run.io_bound(job)
            except (XlsxError, ScriptError, WorkspaceError) as exc:
                ui.notify(describe_error(exc), color="negative")
                return
            if imported is None:
                return
            import_summary.clear()
            import_open.set_visibility(False)
            import_start.disable()
            import_confirm.set_visibility(False)
            with import_summary:
                if imported.workspace_id is None:
                    ui.label(t("Die Arbeitsmappe enthält keine wirksamen Änderungen.")).style(
                        TEXT_STYLE["warning"]
                    )
                else:
                    ui.label(
                        t(
                            "{changed} Änderungen aus {rows} Zeilen übernommen.",
                            changed=imported.changed,
                            rows=imported.row_count,
                        )
                    ).style(TEXT_STYLE["success"])
                    if not imported.three_way:
                        ui.label(t("Ohne Exportbasis geprüft (Zwei-Wege-Vergleich).")).style(
                            TEXT_STYLE["warning"]
                        )
                    for warning in imported.warnings:
                        ui.label(warning)
            import_state["workspace"] = imported.workspace_id
            import_state["issues"] = list(imported.issues)
            if imported.issues:
                import_error_file.set_visibility(True)
            if imported.workspace_id is not None:
                import_open.set_visibility(True)

        async def download_error_file() -> None:
            data = import_state["data"]
            issues = import_state["issues"]
            if not data or not issues:
                ui.notify(t("Keine Befunde zum Markieren vorhanden."), color="warning")
                return

            def job() -> Any:
                return build_error_workbook(data, issues=issues, filename=import_state["name"])

            try:
                made = await run.io_bound(job)
            except XlsxError as exc:
                ui.notify(describe_error(exc), color="negative")
                return
            if made is None:
                return
            payload, name = made
            ui.download(payload, name)
            ui.notify(t("Fehlerdatei erstellt: {count} markierte Zellen.", count=len(issues)))

        import_button.on_click(import_dialog.open)
        import_upload.on_upload(uploaded)
        import_confirm.on_value_change(lambda _: confirm_changed())
        import_start.on_click(start_import_now)
        import_error_file.on_click(download_error_file)

        def _remove(workspace_id: int) -> None:
            with session_scope(session_factory) as session:
                workspace = session.get(Workspace, workspace_id)
                if workspace is None:
                    return
                delete_workspace(session, workspace)
            status.set_text(t("Arbeitsbestand gelöscht."))
            workspace_rows.refresh()

        def reopen(workspace_id: int) -> None:
            with session_scope(session_factory) as session:
                workspace = session.get(Workspace, workspace_id)
                if workspace is None:
                    return
                reopen_workspace(session, workspace)
            status.set_text(t("Arbeitsbestand wieder geöffnet."))
            workspace_rows.refresh()

        list_state: dict[str, Any] = {"include_closed": False, "delete": None}

        with ui.dialog() as delete_dialog, ui.card().classes("w-[460px] gap-2"):
            delete_text = ui.label("").classes("text-sm")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("Abbrechen"), on_click=delete_dialog.close).props("flat dense")
                delete_confirm = ui.button(t("Endgültig löschen")).props(
                    "unelevated dense color=negative"
                )

        def _ask_delete(workspace_id: int, name: str, changed: int) -> None:
            list_state["delete"] = workspace_id
            if changed:
                text = t(
                    "Arbeitsbestand '{name}' endgültig löschen? {changes} nicht geschriebene "
                    "Änderungen gehen dabei verloren.",
                    name=name,
                    changes=changed,
                )
            else:
                text = t(
                    "Arbeitsbestand '{name}' endgültig löschen? Der Entwurf und seine Zeilen "
                    "werden entfernt.",
                    name=name,
                )
            delete_text.set_text(text)
            delete_dialog.open()

        def _confirm_delete() -> None:
            workspace_id = list_state["delete"]
            if not isinstance(workspace_id, int):
                return
            list_state["delete"] = None
            delete_dialog.close()
            _remove(workspace_id)

        delete_confirm.on_click(_confirm_delete)

        @ui.refreshable
        def workspace_rows() -> None:
            with session_scope(session_factory) as session:
                items = [
                    {
                        "id": workspace.id,
                        "name": workspace.name or t("Arbeitsbestand {id}", id=workspace.id),
                        "status": workspace.status.value,
                        "closed": workspace.status is WorkspaceStatus.CLOSED,
                        "rows": workspace.row_count,
                        "changed": changed_count(session, workspace.id),
                        "updated": workspace.updated_at.strftime("%d.%m.%Y %H:%M"),
                        "expiry": _expiry_text(workspace),
                    }
                    for workspace in list_workspaces(
                        session, user.id, include_closed=list_state["include_closed"]
                    )
                ]
            if not items:
                ui.label(t("Keine offenen Arbeitsbestände.")).classes("text-sm")
                return
            for item in items:
                with ui.row().classes(ROW_CLASSES):
                    ui.label(item["name"]).classes("w-56 font-medium")
                    ui.label(item["status"]).classes("w-20 text-xs")
                    ui.label(t("{count} Zeilen", count=item["rows"])).classes("w-24 text-xs")
                    ui.label(t("{count} Änderungen", count=item["changed"])).classes("w-28 text-xs")
                    ui.label(item["updated"]).classes("w-32 text-xs")
                    ui.label(item["expiry"]).classes("w-44 text-xs").style(TEXT_STYLE["warning"])
                    if item["closed"]:
                        action_button(
                            "restart_alt",
                            t("Wieder öffnen"),
                            lambda workspace_id=int(item["id"]): reopen(workspace_id),
                        )
                    else:
                        action_button(
                            "grid_on",
                            t("Öffnen"),
                            lambda workspace_id=int(item["id"]): ui.navigate.to(
                                f"/workspaces/{workspace_id}"
                            ),
                        )
                    action_button(
                        "delete",
                        t("Arbeitsbestand löschen"),
                        lambda workspace_id=int(item["id"]), name=str(item["name"]), changed=int(item["changed"]): (
                            _ask_delete(workspace_id, name, changed)
                        ),
                    )

        with ui.row().classes("w-full items-center gap-2 mt-4"):
            ui.label(t("Offene Arbeitsbestände")).classes("font-semibold")
            closed_switch = ui.switch(
                t("geschlossene anzeigen"), value=list_state["include_closed"]
            )
            action_button("refresh", t("Liste aktualisieren"), workspace_rows.refresh)

        def _toggle_closed() -> None:
            list_state["include_closed"] = bool(closed_switch.value)
            workspace_rows.refresh()

        closed_switch.on_value_change(lambda _: _toggle_closed())
        workspace_rows()

    @ui.page("/workspaces/{workspace_id}")
    def grid_page(workspace_id: int) -> None:  # pyright: ignore[reportUnusedFunction]
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
                ui.label(t("Der Arbeitsbestand wurde nicht gefunden.")).style(TEXT_STYLE["error"])
                return
            profile = session.get(Profile, workspace.profile_id)
            if profile is None:
                page_header(t("Arbeitsbestände"), user)
                ui.label(t("Das Profil fehlt.")).style(TEXT_STYLE["error"])
                return
            name = workspace.name or t("Arbeitsbestand {id}", id=workspace.id)
            workspace_status = workspace.status
            row_count = workspace.row_count
            revision = int(workspace.edit_revision)
            changed = changed_count(session, workspace.id)
            warning = expiry_warning_days(workspace)
            expiry_date = workspace.expires_at.strftime("%d.%m.%Y") if workspace.expires_at else ""
            schema = schema_cache.get(profile)
            columns = view_columns(session, workspace, schema)
            missing = missing_columns(session, workspace, columns)

        scroll_hint = _take_scroll_hint()
        focus_key = (
            str(scroll_hint.get("key") or "")
            if scroll_hint is not None and scroll_hint.get("workspace") == workspace_id
            else ""
        )
        page_header(name, user)
        ui.add_head_html(GRID_HEAD)
        ui.add_head_html(
            GRID_SCRIPT
            % {
                "workspace_id": workspace_id,
                "revision": revision,
                "rows_route": ROWS_ROUTE,
                "changes_route": CHANGES_ROUTE,
            }
        )
        status = ui.label(
            t(
                "{rows} Zeilen | {changes} Änderungen | Revision {revision}",
                rows=row_count,
                changes=changed,
                revision=revision,
            )
        ).classes("text-sm")
        if workspace_status is not WorkspaceStatus.READY:
            ui.label(t("Status: {status}", status=workspace_status.value)).classes("text-sm").style(
                TEXT_STYLE["warning"]
            )
        if expiry_date:
            ui.label(
                t(
                    "Der Entwurf bleibt bis {date} erhalten; jede Aktivität verlängert die Frist.",
                    date=expiry_date,
                )
            ).classes("text-xs")
        if warning is not None:
            ui.label(
                t(
                    "Der Entwurf läuft in {days} Tagen ab (Warnung ab {threshold} Tagen).",
                    days=warning,
                    threshold=EXPIRY_WARNING_DAYS,
                )
            ).classes("text-sm").style(TEXT_STYLE["error"])
        ui.label(
            t("Der Entwurf wurde in einem anderen Tab geändert. Bitte die Seite neu laden.")
        ).classes("ws-conflict").props('id="ws-conflict"')
        load_hint = ui.label(t("Werte der neuen Spalten werden geladen …")).classes("text-xs")
        load_hint.set_visibility(bool(missing))

        column_options = {column.key: column.label for column in columns}
        writable = [column for column in columns if column.writable]
        state: dict[str, Any] = {"filter": "", "filterKey": "", "onlyChanged": False}

        all_columns = schema.columns()
        groups = grouped_columns(all_columns)
        dialog_columns = [column for source, _title in COLUMN_GROUPS for column in groups[source]]
        selected_keys = {column.key for column in columns}
        checked: dict[str, Any] = {}
        visible_keys: set[str] = set()
        built = {"done": False, "bulk": False}

        with ui.dialog() as column_dialog, ui.card().classes("w-[560px] gap-2"):
            ui.label(t("Spalten auswählen")).classes("font-semibold text-base")
            ui.label(
                t(
                    "Die Auswahl gilt nur für diesen Arbeitsbestand und wird gespeichert. "
                    "Höchstens {limit} Spalten.",
                    limit=MAX_SELECTED_COLUMNS,
                )
            ).classes("text-xs")
            column_filter = (
                ui.input(t("Felder filtern")).props("outlined dense clearable").classes("w-full")
            )
            column_list = ui.column().classes("w-full gap-1 max-h-96 overflow-auto")
            counter = ui.label("").classes("text-xs")
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("gap-2"):
                    all_button = ui.button(t("Alle")).props("flat dense")
                    none_button = ui.button(t("Keine")).props("flat dense")
                    ui.button(t("Zurücksetzen"), on_click=lambda: _reset_columns()).props(
                        "flat dense"
                    )
                with ui.row().classes("gap-2"):
                    ui.button(t("Abbrechen"), on_click=column_dialog.close).props("flat dense")
                    apply_button = ui.button(t("Übernehmen")).props("unelevated dense")

        def _build_column_list() -> None:
            if built["done"]:
                return
            built["done"] = True
            with column_list:
                for source, title in COLUMN_GROUPS:
                    group = groups[source]
                    if not group:
                        continue
                    ui.label(t(title)).classes("text-xs font-semibold mt-1")
                    for column in group:
                        label = column.label
                        if not column.writable:
                            label = f"{label} ({t('nur lesen')})"
                        widget = ui.checkbox(label, value=column.key in selected_keys)
                        widget.classes("text-sm")
                        widget.on_value_change(lambda _: _refresh_counter())
                        checked[column.key] = widget

        def _chosen_keys() -> list[str]:
            chosen = {
                column.key
                for column in dialog_columns
                if column.key in checked and checked[column.key].value
            }
            return ordered_keys(
                [column.key for column in columns],
                chosen,
                [column.key for column in dialog_columns],
            )

        def _refresh_counter() -> None:
            if built["bulk"] or not built["done"]:
                return
            chosen = len(_chosen_keys())
            counter.set_text(
                t(
                    "{count} von {limit} Spalten ausgewählt",
                    count=chosen,
                    limit=MAX_SELECTED_COLUMNS,
                )
            )
            apply_button.set_enabled(0 < chosen <= MAX_SELECTED_COLUMNS)

        def _apply_filter() -> None:
            if not built["done"]:
                return
            term = str(column_filter.value or "").strip().lower()
            visible_keys.clear()
            for column in dialog_columns:
                hit = not term or term in column.label.lower() or term in column.key.lower()
                checked[column.key].set_visibility(hit)
                if hit:
                    visible_keys.add(column.key)

        def _set_all(value: bool) -> None:
            built["bulk"] = True
            try:
                if not value:
                    for widget in checked.values():
                        widget.value = False
                    return
                chosen = len(_chosen_keys())
                skipped = 0
                for column in dialog_columns:
                    widget = checked.get(column.key)
                    if widget is None or column.key not in visible_keys or widget.value:
                        continue
                    if chosen >= MAX_SELECTED_COLUMNS:
                        skipped += 1
                        continue
                    widget.value = True
                    chosen += 1
                if skipped:
                    ui.notify(
                        t(
                            "Höchstens {limit} Spalten; {skipped} Felder wurden nicht ausgewählt.",
                            limit=MAX_SELECTED_COLUMNS,
                            skipped=skipped,
                        ),
                        color="warning",
                    )
            finally:
                built["bulk"] = False
            _refresh_counter()

        async def _load_missing(wanted: Sequence[ColumnDef]) -> int:
            """Laedt Werte nach, die fuer die aktuelle Auswahl noch im Snapshot fehlen."""
            from app.writer import read_files

            def job() -> int:
                with session_scope(session_factory) as session:
                    current = session.get(Workspace, workspace_id)
                    if current is None:
                        return 0
                    profile_row = session.get(Profile, current.profile_id)
                    if profile_row is None:
                        return 0
                    missing = missing_columns(session, current, wanted)
                    if not missing:
                        return 0
                    client = client_factory.client_for(profile_row)
                    ids = [
                        int(value)
                        for value in session.scalars(
                            select(WorkspaceAsset.file_id).where(
                                WorkspaceAsset.workspace_id == current.id
                            )
                        )
                    ]
                    data = read_files(client, missing, ids)
                    values = {file_id: item["values"] for file_id, item in data.items()}
                    return merge_snapshot_values(
                        session, current, values, [column.key for column in missing]
                    )

            try:
                return await run.io_bound(job) or 0
            except Exception as exc:  # noqa: BLE001 - Nachladen ist eine Zugabe
                ui.notify(describe_error(exc), color="warning")
                return 0

        async def _apply_columns() -> None:
            keys = _chosen_keys()
            known_visible = {column.key for column in columns}
            added = [key for key in keys if key not in known_visible]
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is None:
                    return
                try:
                    stored = store_columns(session, current, keys)
                except WorkspaceError as exc:
                    ui.notify(describe_error(exc), color="negative")
                    return
            column_dialog.close()
            ui.notify(t("{count} Spalten übernommen.", count=len(stored)))
            if added:
                _store_scroll_hint(workspace_id, added[0])
            ui.navigate.reload()

        def _reset_columns() -> None:
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is None:
                    return
                clear_columns(session, current)
            column_dialog.close()
            ui.navigate.reload()

        def _open_columns() -> None:
            _build_column_list()
            column_filter.value = ""
            _apply_filter()
            _refresh_counter()
            column_dialog.open()

        with ui.dialog() as close_dialog, ui.card().classes("w-[480px] gap-2"):
            close_text = ui.label("").classes("text-sm")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("Abbrechen"), on_click=close_dialog.close).props("flat dense")
                ui.button(t("Schließen"), on_click=lambda: _confirm_close()).props(
                    "unelevated dense"
                )

        all_button.on_click(lambda: _set_all(True))
        none_button.on_click(lambda: _set_all(False))
        apply_button.on_click(_apply_columns)
        column_filter.on_value_change(lambda _: _apply_filter())

        with ui.row().classes("w-full flex-wrap items-end gap-2") as filter_row:
            filter_column_select = (
                ui.select(column_options, value=columns[0].key, label=t("Spalte"))
                .props("outlined dense")
                .classes("w-44")
            )
            filter_input = ui.input(t("Filter (enthält)")).props("outlined dense").classes("w-48")
            only_changed_switch = ui.switch(t("nur geänderte Zeilen"), value=False)
        with ui.row().classes("w-full flex-wrap items-end gap-2") as bulk_row:
            target_column_select = (
                ui.select(
                    {column.key: column.label for column in writable},
                    value=writable[0].key if writable else None,
                    label=t("Zielspalte"),
                )
                .props("outlined dense")
                .classes("w-44")
            )
            value_slot = ui.element("div").classes("w-44")
            value_state: dict[str, Any] = {"widget": None}
            target_scope_select = (
                ui.select(
                    {
                        "selection": t("markierte Zeilen"),
                        "filtered": t("gefilterte"),
                        "all": t("alle"),
                    },
                    value="selection",
                    label=t("Ziel"),
                )
                .props("outlined dense")
                .classes("w-40")
            )

        def _value_widget(column: ColumnDef | None) -> Any:
            """Eingabe passend zum Feldtyp der Zielspalte."""
            value_slot.clear()
            with value_slot:
                if column is not None and column.edit_type == "selection" and column.options:
                    return (
                        ui.select({name: name for name in column.options}, label=t("Wert"))
                        .props("outlined dense clearable")
                        .classes("w-full")
                    )
                if column is not None and column.edit_type == "boolean":
                    return (
                        ui.select({"ja": t("ja"), "nein": t("nein")}, label=t("Wert"))
                        .props("outlined dense clearable")
                        .classes("w-full")
                    )
                if column is not None and column.edit_type == "date":
                    widget = (
                        ui.input(t("Wert"))
                        .props("outlined dense")
                        .props('placeholder="JJJJ-MM-TT"')
                        .classes("w-full")
                    )
                    with ui.menu().props("no-parent-event") as menu:
                        with ui.date().bind_value(widget):
                            with ui.row().classes("w-full justify-end"):
                                ui.button(t("Fertig"), on_click=menu.close).props("flat dense")
                    with widget.add_slot("append"):
                        ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
                    return widget
                return ui.input(t("Wert")).props("outlined dense").classes("w-full")

        def _render_value_input() -> None:
            value_state["widget"] = _value_widget(_column_for(columns, target_column_select.value))

        _render_value_input()
        target_column_select.on_value_change(lambda _: _render_value_input())
        grid_options: dict[str, Any] = {
            "columnDefs": [
                {
                    "field": "fileId",
                    "headerName": "ID",
                    "width": 110,
                    "pinned": "left",
                    "editable": False,
                },
                *[column_def(column) for column in columns],
            ],
            "defaultColDef": {"resizable": True, "sortable": True},
            "rowModelType": "infinite",
            "cacheBlockSize": BLOCK_SIZE,
            "maxBlocksInCache": 3,
            "rowBuffer": 5,
            "animateRows": False,
            "rowSelection": {"mode": "multiRow", "headerCheckbox": False},
            "rowClassRules": {"ws-row-changed": "!!data && data.__changed === true"},
            ":datasource": "window.__ws.datasource",
        }
        if get_locale() == "de":
            grid_options["localeText"] = GRID_LOCALE_DE
        grid = ui.aggrid(grid_options, auto_size_columns=False).classes("ws-grid w-full")

        async def refresh_status() -> None:
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is None:
                    return
                text = t(
                    "{rows} Zeilen | {changes} Änderungen | Revision {revision}",
                    rows=current.row_count,
                    changes=changed_count(session, workspace.id),
                    revision=int(current.edit_revision),
                )
            status.set_text(text)

        async def reload_changes_and_grid() -> None:
            await ui.run_javascript("window.__ws && window.__ws.loadChanges()", timeout=10)
            await grid.run_grid_method("purgeInfiniteCache")
            await refresh_status()

        async def fill_missing_values() -> None:
            """Werte nachladen, die fuer die aktuelle Spaltenauswahl noch fehlen."""
            nonlocal missing
            wanted, missing = missing, []
            if not wanted:
                return
            load_hint.set_visibility(True)
            try:
                filled = await _load_missing(wanted)
            finally:
                load_hint.set_visibility(False)
            if filled:
                await grid.run_grid_method("purgeInfiniteCache")

        def apply_filter() -> None:
            state["filter"] = filter_input.value or ""
            state["filterKey"] = filter_column_select.value or ""
            state["onlyChanged"] = bool(only_changed_switch.value)

        async def apply_filter_now() -> None:
            apply_filter()
            await ui.run_javascript(
                "window.__ws.setFilter("
                f"{json.dumps(state['filter'])}, {json.dumps(state['filterKey'])}, "
                f"{'true' if state['onlyChanged'] else 'false'});"
            )
            await grid.run_grid_method("purgeInfiniteCache")

        async def reset_filter() -> None:
            filter_input.value = ""
            only_changed_switch.value = False
            await apply_filter_now()

        async def sort_by(direction: str) -> None:
            key = filter_column_select.value
            if not key:
                return
            await grid.run_grid_method(
                "applyColumnState",
                {"state": [{"colId": key, "sort": direction}], "defaultState": {"sort": None}},
            )

        async def fit_content() -> None:
            await grid.run_grid_method("autoSizeAllColumns", False)

        async def fit_display() -> None:
            await grid.run_grid_method("sizeColumnsToFit")
            narrowest = await ui.run_javascript(
                "Math.round(Math.min(...Array.from("
                "document.querySelectorAll('.ag-header-cell'))"
                ".map((cell) => cell.getBoundingClientRect().width)))"
            )
            if isinstance(narrowest, int | float) and narrowest < MIN_COLUMN_WIDTH:
                ui.notify(
                    t(
                        "Spalten sind nur {width} px breit; Inhalte werden abgeschnitten.",
                        width=int(narrowest),
                    ),
                    color="warning",
                )

        async def cell_changed(event: Any) -> None:
            args = event.args or {}
            data = args.get("data") if isinstance(args, dict) else None
            file_id = data.get("fileId") if isinstance(data, dict) else None
            key = args.get("colId") if isinstance(args, dict) else None
            column = _column_for(columns, key)
            if not isinstance(file_id, int) or column is None:
                return
            revision_value = await ui.run_javascript("window.__ws.currentRevision()")
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is None:
                    return
                try:
                    set_change(
                        session,
                        current,
                        file_id=file_id,
                        column=column,
                        value=args.get("newValue"),
                        actor=session.get(AppUser, user.id),
                        expected_revision=(
                            int(revision_value) if isinstance(revision_value, int | float) else None
                        ),
                    )
                except WorkspaceConflictError as exc:
                    ui.notify(str(exc), color="negative")
                except (ScriptError, WorkspaceError) as exc:
                    ui.notify(str(exc), color="negative")
                else:
                    ui.notify(t("{field} gespeichert.", field=column.label))
            await reload_changes_and_grid()

        grid.on(
            "cellValueChanged",
            cell_changed,
            args=["data", "colId", "newValue", "oldValue"],
        )

        def selected_file_ids(rows: Sequence[dict[str, Any]] | None) -> list[int]:
            return [int(row["fileId"]) for row in rows or [] if isinstance(row.get("fileId"), int)]

        def targets_for(scope: str, file_ids: Sequence[int]) -> list[int]:
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is None:
                    return []
                return resolve_targets(
                    session,
                    current,
                    file_ids=list(file_ids) if scope == "selection" else None,
                    filter_column=_column_for(columns, state["filterKey"]),
                    filter_value=state["filter"],
                    only_changed=state["onlyChanged"],
                )

        async def apply_value() -> None:
            column = _column_for(columns, target_column_select.value)
            if column is None:
                ui.notify(t("Bitte eine Zielspalte wählen."), color="warning")
                return
            scope = str(target_scope_select.value or "selection")
            file_ids = selected_file_ids(await grid.get_selected_rows())
            if scope == "selection" and not file_ids:
                ui.notify(t("Keine Zeile markiert."), color="warning")
                return
            apply_filter()
            target_ids = targets_for(scope, file_ids)
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is None:
                    return
                try:
                    changed_cells = bulk_set(
                        session,
                        current,
                        column=column,
                        value=value_state["widget"].value if value_state["widget"] else None,
                        file_ids=target_ids,
                        actor=session.get(AppUser, user.id),
                    )
                except ScriptError as exc:
                    ui.notify(str(exc), color="negative")
                    return
            ui.notify(
                t(
                    "{changed} von {total} Zeilen geändert.",
                    changed=changed_cells,
                    total=len(target_ids),
                )
            )
            await reload_changes_and_grid()

        async def revert_selection() -> None:
            file_ids = selected_file_ids(await grid.get_selected_rows())
            apply_filter()
            target_ids = targets_for("selection" if file_ids else "all", file_ids)
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is None:
                    return
                removed = clear_changes(session, current, file_ids=target_ids)
            ui.notify(t("{count} Änderungen verworfen.", count=removed))
            await reload_changes_and_grid()

        def close_workspace_now() -> None:
            if changed:
                close_text.set_text(
                    t(
                        "Arbeitsbestand '{name}' schließen? Der Entwurf verschwindet aus der "
                        "Liste; {changes} nicht geschriebene Änderungen bleiben nur über "
                        "„geschlossene anzeigen“ erreichbar.",
                        name=name,
                        changes=changed,
                    )
                )
            else:
                close_text.set_text(
                    t(
                        "Arbeitsbestand '{name}' schließen? Der Entwurf verschwindet aus der "
                        "Liste und lässt sich über „geschlossene anzeigen“ wieder öffnen.",
                        name=name,
                    )
                )
            close_dialog.open()

        def _confirm_close() -> None:
            with session_scope(session_factory) as session:
                current = session.get(Workspace, workspace_id)
                if current is not None:
                    close_workspace(session, current)
            close_dialog.close()
            ui.navigate.to(LIST_ROUTE)

        async def export_excel() -> None:
            file_ids = selected_file_ids(await grid.get_selected_rows())
            apply_filter()
            if not file_ids and (state["filter"] or state["onlyChanged"]):
                file_ids = targets_for("filtered", [])

            def job() -> Any:
                with session_scope(session_factory) as session:
                    current = session.get(Workspace, workspace_id)
                    actor = session.get(AppUser, user.id)
                    if current is None or actor is None:
                        raise WorkspaceError(t("Der Arbeitsbestand wurde nicht gefunden."))
                    profile_row = session.get(Profile, current.profile_id)
                    if profile_row is None:
                        raise WorkspaceError(t("Das Profil fehlt."))
                    return export_workbook(
                        session,
                        workspace=current,
                        profile=profile_row,
                        columns=columns,
                        actor=actor,
                        script_label=script_label(session, current),
                        file_ids=file_ids or None,
                    )

            try:
                exported = await run.io_bound(job)
            except XlsxError as exc:
                ui.notify(describe_error(exc), color="negative")
                return
            if exported is None:
                return
            ui.download(exported.data, exported.filename)
            if exported.pending_changes:
                ui.notify(
                    t("Export erstellt: ungeschriebene Änderungen sind nicht enthalten."),
                    color="warning",
                )
            else:
                ui.notify(t("Export erstellt: {rows} Zeilen.", rows=exported.row_count))

        with filter_row:
            ui.separator().props("vertical")
            action_button("filter_alt_off", t("Filter zurücksetzen"), reset_filter)
            action_button("arrow_upward", t("Aufsteigend sortieren"), lambda: sort_by("asc"))
            action_button("arrow_downward", t("Absteigend sortieren"), lambda: sort_by("desc"))

        with bulk_row:
            ui.separator().props("vertical")
            action_button("edit_note", t("Wert auf Ziel setzen"), apply_value)
            action_button("undo", t("Änderungen verwerfen"), revert_selection)

        with ui.row().classes("w-full items-center gap-1 mt-1"):
            action_button("straighten", t("Spalten an Inhalt anpassen"), fit_content)
            action_button("open_in_full", t("Spalten an Anzeige anpassen"), fit_display)
            action_button("view_column", t("Spalten auswählen"), _open_columns)
            with ui.row().classes("items-center gap-1 ml-auto"):
                action_button(
                    "table_view", t("Excel-Export (markierte oder gefilterte Zeilen)"), export_excel
                )
                action_button(
                    "fact_check",
                    t("Review und schreiben"),
                    lambda: ui.navigate.to(f"/workspaces/{workspace_id}/review"),
                )
                action_button("close", t("Arbeitsbestand schließen"), close_workspace_now)

        filter_input.on("keydown.enter", lambda _: apply_filter_now())
        only_changed_switch.on_value_change(lambda _: apply_filter_now())

        async def after_grid_ready() -> None:
            await reload_changes_and_grid()
            if focus_key:
                try:
                    await grid.run_grid_method("ensureColumnVisible", focus_key)
                except Exception:  # noqa: BLE001 - reine Anzeigehilfe
                    pass
            await fill_missing_values()

        grid.on("gridReady", after_grid_ready, args=[])


def _expiry_text(workspace: Workspace) -> str:
    warning = expiry_warning_days(workspace)
    if warning is None:
        return ""
    return f"laeuft in {warning} Tagen ab"


__all__ = [
    "column_def",
    "ordered_keys",
    "owned_workspace",
    "register_workspace_pages",
    "script_column_keys",
    "workspace_columns",
]
