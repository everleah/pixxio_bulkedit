"""Arbeitsbestaende: Snapshot, ChangeSet, Abfragen und Entwurfsverwaltung.

Der Snapshot je Asset liegt als JSON in ``workspace_asset.values_json`` (Schluessel
sind technische Feldkennungen). Das ChangeSet haelt nur Zellen, deren Wert vom
Snapshot abweicht. Gelesen wird immer der effektive Stand:
``CASE WHEN change.id IS NOT NULL THEN change.new_value ELSE json_extract(...) END``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.clients import plain
from app.models import (
    AppUser,
    Profile,
    QueryScriptVersion,
    Workspace,
    WorkspaceAsset,
    WorkspaceChange,
)
from app.models.base import as_utc, utc_now
from app.models.enums import WorkspaceStatus
from app.normalize import canonical, display_value, is_empty, values_equal
from app.schema import ColumnDef
from app.scripts.errors import ScriptContractError
from app.scripts.runner import ScriptOutcome

DRAFT_TTL_DAYS = 30
EXPIRY_WARNING_DAYS = 7
INSERT_CHUNK = 500
ID_FILTER_CHUNK = 200
LOAD_PAGE_SIZE = 200
# Spaltenauswahl je Arbeitsbestand; reservierter Schluessel, der kein Script-Parameter sein kann.
VIEW_PARAM = "@columns"
MAX_SELECTED_COLUMNS = 80


class WorkspaceError(Exception):
    """Fachlicher Fehler eines Arbeitsbestands."""


class WorkspaceConflictError(WorkspaceError):
    """Der Entwurf wurde inzwischen in einem anderen Tab geaendert."""


@dataclass(frozen=True)
class AssetRow:
    """Ein geladenes Asset mit seinem Snapshot."""

    file_id: int
    modify_date: str | None
    values: dict[str, Any]


@dataclass(frozen=True)
class WorkspacePage:
    """Ein Tabellenblock fuer das Grid."""

    rows: list[dict[str, Any]]
    total: int
    revision: int


@dataclass(frozen=True)
class ChangeEntry:
    """Eine ausstehende Aenderung."""

    file_id: int
    key: str
    old_value: Any
    new_value: Any


def json_path(field_key: str) -> str:
    """JSON-Pfad eines Spaltenschluessels fuer SQLite."""
    return f'$."{field_key}"'


def effective_expression(alias: str, parameter: str) -> str:
    return (
        f"CASE WHEN {alias}.id IS NOT NULL THEN {alias}.new_value "
        f"ELSE json_extract(asset.values_json, :{parameter}) END"
    )


def _change_join(alias: str) -> str:
    return (
        f"LEFT JOIN workspace_change AS {alias}"
        f" ON {alias}.workspace_id = asset.workspace_id"
        f" AND {alias}.file_id = asset.file_id"
        f" AND {alias}.field_key = :{alias}_key"
    )


# --- Entwuerfe ---------------------------------------------------------------


def expiry_for(moment: datetime) -> datetime:
    return moment + timedelta(days=DRAFT_TTL_DAYS)


def expiry_warning_days(workspace: Workspace, now: datetime | None = None) -> int | None:
    """Verbleibende Tage bis zum Ablauf, wenn die Warnschwelle erreicht ist."""
    if workspace.expires_at is None:
        return None
    current = now or utc_now()
    remaining = (as_utc(workspace.expires_at) - as_utc(current)).days
    return remaining if remaining <= EXPIRY_WARNING_DAYS else None


def create_workspace(
    session: Session,
    *,
    owner: AppUser,
    profile: Profile,
    name: str | None = None,
    script_version: QueryScriptVersion | None = None,
    params: dict[str, Any] | None = None,
) -> Workspace:
    """Legt einen Arbeitsbestand im Zustand ``loading`` an."""
    now = utc_now()
    workspace = Workspace(
        name=(name or "").strip() or None,
        owner_id=owner.id,
        profile_id=profile.id,
        script_version_id=script_version.id if script_version is not None else None,
        params_json=json.dumps(params, ensure_ascii=False) if params else None,
        status=WorkspaceStatus.LOADING,
        row_count=0,
        edit_revision=0,
        created_at=now,
        updated_at=now,
        last_activity_at=now,
        expires_at=expiry_for(now),
    )
    session.add(workspace)
    session.flush()
    return workspace


def store_snapshot(session: Session, workspace: Workspace, rows: Sequence[AssetRow]) -> None:
    """Schreibt den Snapshot und markiert den Arbeitsbestand als bereit."""
    session.execute(delete(WorkspaceAsset).where(WorkspaceAsset.workspace_id == workspace.id))
    for start in range(0, len(rows), INSERT_CHUNK):
        chunk = rows[start : start + INSERT_CHUNK]
        session.execute(
            insert(WorkspaceAsset),
            [
                {
                    "workspace_id": workspace.id,
                    "file_id": row.file_id,
                    "modify_date": row.modify_date,
                    "values_json": json.dumps(row.values, ensure_ascii=False),
                    "position": start + index,
                }
                for index, row in enumerate(chunk)
            ],
        )
    workspace.row_count = len(rows)
    workspace.status = WorkspaceStatus.READY
    workspace.updated_at = utc_now()
    workspace.last_activity_at = utc_now()
    workspace.expires_at = expiry_for(utc_now())
    session.flush()


def mark_failed(session: Session, workspace: Workspace) -> None:
    workspace.status = WorkspaceStatus.FAILED
    session.flush()


def close_workspace(session: Session, workspace: Workspace) -> None:
    workspace.status = WorkspaceStatus.CLOSED
    session.flush()


def delete_workspace(session: Session, workspace: Workspace) -> None:
    session.delete(workspace)
    session.flush()


def touch(session: Session, workspace: Workspace) -> None:
    """Verlaengert die Laufzeit bei Aktivitaet."""
    workspace.last_activity_at = utc_now()
    workspace.expires_at = expiry_for(workspace.last_activity_at)
    session.flush()


def import_meta(workspace: Workspace) -> dict[str, Any] | None:
    """Metadaten eines Excel-Imports, sonst ``None``."""
    meta = _params_dict(workspace).get("xlsx")
    return meta if isinstance(meta, dict) else None


def _params_dict(workspace: Workspace) -> dict[str, Any]:
    if not workspace.params_json:
        return {}
    try:
        params = json.loads(workspace.params_json)
    except ValueError:
        return {}
    return params if isinstance(params, dict) else {}


def _write_params(workspace: Workspace, params: dict[str, Any]) -> None:
    workspace.params_json = json.dumps(params, ensure_ascii=False) if params else None


def stored_columns(workspace: Workspace) -> list[str] | None:
    """Gespeicherte Spaltenauswahl des Arbeitsbestands."""
    value = _params_dict(workspace).get(VIEW_PARAM)
    if not isinstance(value, list):
        return None
    keys = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return keys or None


def store_columns(session: Session, workspace: Workspace, keys: Sequence[str]) -> list[str]:
    """Speichert die Spaltenauswahl; liefert die uebernommenen Schluessel."""
    cleaned: list[str] = []
    for key in keys:
        text = str(key).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        raise WorkspaceError("Es muss mindestens eine Spalte ausgewaehlt bleiben.")
    if len(cleaned) > MAX_SELECTED_COLUMNS:
        raise WorkspaceError(
            f"Es sind hoechstens {MAX_SELECTED_COLUMNS} Spalten gleichzeitig auswaehlbar."
        )
    params = _params_dict(workspace)
    params[VIEW_PARAM] = cleaned
    _write_params(workspace, params)
    touch(session, workspace)
    return cleaned


def clear_columns(session: Session, workspace: Workspace) -> None:
    """Verwirft die Spaltenauswahl; es gelten wieder Script- beziehungsweise Standardspalten."""
    params = _params_dict(workspace)
    if params.pop(VIEW_PARAM, None) is None:
        return
    _write_params(workspace, params)
    touch(session, workspace)


def list_workspaces(session: Session, owner_id: int) -> Sequence[Workspace]:
    return list(
        session.scalars(
            select(Workspace)
            .where(Workspace.owner_id == owner_id, Workspace.status != WorkspaceStatus.CLOSED)
            .order_by(Workspace.updated_at.desc())
        )
    )


# --- Laden -------------------------------------------------------------------


def load_assets(
    client: Any,
    columns: Sequence[ColumnDef],
    outcome: ScriptOutcome,
    *,
    max_rows: int,
) -> list[AssetRow]:
    """Laedt die Assets eines Script-Ergebnisses in den Snapshot."""
    from pixxio_client.files import File

    files = File(client)
    rows: list[AssetRow] = []
    seen: set[int] = set()
    if outcome.result is None:
        raise WorkspaceError("Das Script hat kein Ergebnis geliefert.")
    if outcome.result.ids:
        for chunk in _chunks(outcome.result.ids, ID_FILTER_CHUNK):
            selector = {"filterType": "files", "fileIDs": list(chunk)}
            for item in files.iter_all(
                filter=selector, page_size=LOAD_PAGE_SIZE, max_items=max_rows + 1
            ):
                _append_row(item, columns, rows, seen, max_rows)
    elif outcome.result.filter is not None:
        for item in files.iter_all(
            filter=outcome.result.filter, page_size=LOAD_PAGE_SIZE, max_items=max_rows + 1
        ):
            _append_row(item, columns, rows, seen, max_rows)
    else:
        raise WorkspaceError("Das Script-Ergebnis enthaelt weder Filter noch IDs.")
    return rows


def _chunks(values: Sequence[int], size: int) -> Iterable[Sequence[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _append_row(
    item: Any,
    columns: Sequence[ColumnDef],
    rows: list[AssetRow],
    seen: set[int],
    max_rows: int,
) -> None:
    payload = plain(item)
    file_id = int(payload.get("id"))
    if file_id in seen:
        return
    seen.add(file_id)
    if len(rows) > max_rows:
        raise WorkspaceError(
            f"Die Ergebnismenge ueberschreitet das Profillimit von {max_rows} Zeilen."
        )
    values = file_values(payload, columns)
    rows.append(
        AssetRow(
            file_id=file_id,
            modify_date=_text(payload.get("modifyDate")),
            values=values,
        )
    )


def _read_value(payload: dict[str, Any], column: ColumnDef, metadata: dict[str, Any]) -> Any:
    if column.source == "file_attr":
        attribute = column.key.split(":", 1)[1]
        if attribute == "fileStateID":
            state = payload.get("fileState")
            raw = state.get("id") if isinstance(state, dict) else None
        else:
            raw = payload.get(attribute)
        if attribute == "keywords":
            raw = raw or []
        return _canonical_safe(column, raw)
    entry = metadata.get(str(column.field_id))
    if not isinstance(entry, dict):
        return None
    return _canonical_safe(column, entry.get("value"))


def file_values(payload: dict[str, Any], columns: Sequence[ColumnDef]) -> dict[str, Any]:
    """Liest die Spaltenwerte eines Datei-Payloads in Anzeigenormalform."""
    metadata = payload.get("metadataFields") or {}
    return {column.key: _read_value(payload, column, metadata) for column in columns}


def _canonical_safe(column: ColumnDef, value: Any) -> Any:
    try:
        return canonical(column.edit_type, _option_names(column, value), options=column.options)
    except ScriptContractError:
        return None if is_empty(value) else value


def _option_names(column: ColumnDef, value: Any) -> Any:
    """Auswahl-IDs in Optionsnamen übersetzen (API liefert beides)."""
    mapping = {option_id: name for option_id, name in column.option_ids}
    if not mapping or is_empty(value):
        return value
    if isinstance(value, list):
        return [_option_names(column, item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return mapping.get(value, value)
    return value


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


# --- ChangeSet ---------------------------------------------------------------


def snapshot_value(session: Session, workspace_id: int, file_id: int, key: str) -> Any:
    asset = session.get(WorkspaceAsset, (workspace_id, file_id))
    if asset is None:
        raise WorkspaceError(f"Asset {file_id} gehoert nicht zum Arbeitsbestand.")
    return json.loads(asset.values_json).get(key)


def set_change(
    session: Session,
    workspace: Workspace,
    *,
    file_id: int,
    column: ColumnDef,
    value: Any,
    actor: AppUser | None = None,
    expected_revision: int | None = None,
) -> bool:
    """Speichert eine Zellaenderung; liefert ``True``, wenn sie wirksam ist."""
    _assert_revision(workspace, expected_revision)
    if not column.writable:
        raise WorkspaceError(f"Die Spalte {column.label!r} ist nicht schreibbar.")
    new_value = canonical(column.edit_type, value, options=column.options)
    old_value = snapshot_value(session, workspace.id, file_id, column.key)
    existing = session.scalar(
        select(WorkspaceChange).where(
            WorkspaceChange.workspace_id == workspace.id,
            WorkspaceChange.file_id == file_id,
            WorkspaceChange.field_key == column.key,
        )
    )
    if values_equal(new_value, old_value):
        if existing is not None:
            session.delete(existing)
        _bump(workspace, session)
        return False
    if existing is None:
        session.add(
            WorkspaceChange(
                workspace_id=workspace.id,
                file_id=file_id,
                field_key=column.key,
                old_value=_as_text(old_value),
                new_value=_as_text(new_value),
                updated_by_id=actor.id if actor is not None else None,
            )
        )
    else:
        existing.new_value = _as_text(new_value)
        existing.updated_at = utc_now()
        existing.updated_by_id = actor.id if actor is not None else None
    _bump(workspace, session)
    return True


def revert_change(
    session: Session,
    workspace: Workspace,
    *,
    file_id: int,
    key: str,
    expected_revision: int | None = None,
) -> None:
    _assert_revision(workspace, expected_revision)
    session.execute(
        delete(WorkspaceChange).where(
            WorkspaceChange.workspace_id == workspace.id,
            WorkspaceChange.file_id == file_id,
            WorkspaceChange.field_key == key,
        )
    )
    _bump(workspace, session)


def clear_changes(
    session: Session,
    workspace: Workspace,
    *,
    keys: Sequence[str] | None = None,
    file_ids: Sequence[int] | None = None,
) -> int:
    statement = delete(WorkspaceChange).where(WorkspaceChange.workspace_id == workspace.id)
    if keys:
        statement = statement.where(WorkspaceChange.field_key.in_(list(keys)))
    if file_ids:
        statement = statement.where(WorkspaceChange.file_id.in_(list(file_ids)))
    result = session.execute(statement)
    _bump(workspace, session)
    return int(getattr(result, "rowcount", 0) or 0)


def commit_applied(
    session: Session,
    workspace: Workspace,
    applied: Sequence[tuple[int, str]],
    *,
    values: dict[int, dict[str, Any]] | None = None,
    modify_dates: dict[int, str] | None = None,
) -> int:
    """Uebernimmt geschriebene Felder in den Snapshot und leert ihre Aenderung."""
    if not applied:
        return 0
    removed = 0
    touched: set[int] = set()
    for file_id, key in applied:
        result = session.execute(
            delete(WorkspaceChange).where(
                WorkspaceChange.workspace_id == workspace.id,
                WorkspaceChange.file_id == file_id,
                WorkspaceChange.field_key == key,
            )
        )
        removed += int(getattr(result, "rowcount", 0) or 0)
        asset = session.get(WorkspaceAsset, (workspace.id, file_id))
        if asset is None:
            continue
        stored = json.loads(asset.values_json)
        read_back = (values or {}).get(file_id, {})
        if key in read_back:
            stored[key] = read_back[key]
        asset.values_json = json.dumps(stored, ensure_ascii=False)
        touched.add(file_id)
    for file_id in touched:
        modify_date = (modify_dates or {}).get(file_id)
        if modify_date:
            asset = session.get(WorkspaceAsset, (workspace.id, file_id))
            if asset is not None:
                asset.modify_date = modify_date
    _bump(workspace, session)
    return removed


def _as_text(value: Any) -> str | None:
    # Alle Werte als JSON, damit Text und Liste eindeutig unterscheidbar bleiben.
    if is_empty(value):
        return None
    return json.dumps(value, ensure_ascii=False)


def _assert_revision(workspace: Workspace, expected: int | None) -> None:
    if expected is not None and expected != workspace.edit_revision:
        raise WorkspaceConflictError(
            "Der Entwurf wurde in einem anderen Tab geaendert. Bitte neu laden."
        )


def _bump(workspace: Workspace, session: Session) -> None:
    workspace.edit_revision = int(workspace.edit_revision) + 1
    workspace.updated_at = utc_now()
    workspace.last_activity_at = utc_now()
    session.flush()


def changed_changes(session: Session, workspace_id: int) -> list[ChangeEntry]:
    rows = session.execute(
        select(
            WorkspaceChange.file_id,
            WorkspaceChange.field_key,
            WorkspaceChange.old_value,
            WorkspaceChange.new_value,
        )
        .where(WorkspaceChange.workspace_id == workspace_id)
        .order_by(WorkspaceChange.file_id, WorkspaceChange.field_key)
    ).all()
    return [
        ChangeEntry(
            file_id=int(row.file_id),
            key=str(row.field_key),
            old_value=_from_text(row.old_value),
            new_value=_from_text(row.new_value),
        )
        for row in rows
    ]


def changed_count(session: Session, workspace_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(WorkspaceChange)
            .where(WorkspaceChange.workspace_id == workspace_id)
        )
        or 0
    )


def changed_file_ids(session: Session, workspace_id: int) -> list[int]:
    return [
        int(value)
        for value in session.scalars(
            select(WorkspaceChange.file_id)
            .where(WorkspaceChange.workspace_id == workspace_id)
            .distinct()
        )
    ]


def _from_text(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


# --- Abfragen ----------------------------------------------------------------


def effective_page(
    session: Session,
    workspace: Workspace,
    *,
    start: int = 0,
    count: int = 100,
    sort_column: ColumnDef | None = None,
    descending: bool = False,
    filter_column: ColumnDef | None = None,
    filter_value: str = "",
    only_changed: bool = False,
) -> WorkspacePage:
    """Liest einen Block im effektiven Stand inklusive Trefferzahl."""
    sort_column = sort_column or ColumnDef("std:fileName", "Dateiname", "file_attr", "text")
    params: dict[str, Any] = {"workspace_id": workspace.id}
    join_parts: list[str] = []
    if sort_column is not None:
        join_parts.append(_change_join("schg"))
        params["schg_key"] = sort_column.key
        params["schg_path"] = json_path(sort_column.key)
    filter_expression = "NULL"
    if filter_value:
        join_parts.append(_change_join("fchg"))
        params["fchg_key"] = (filter_column or sort_column).key
        params["fchg_path"] = json_path((filter_column or sort_column).key)
        filter_expression = f"CAST({effective_expression('fchg', 'fchg_path')} AS TEXT)"
        params["filter"] = f"%{filter_value}%"
    order_expression = effective_expression("schg", "schg_path")
    if sort_column.edit_type == "number":
        order_expression = f"CAST({order_expression} AS REAL)"
    joins = " ".join(join_parts)
    direction = "DESC" if descending else "ASC"
    changed_expression = (
        "EXISTS (SELECT 1 FROM workspace_change AS anyc"
        " WHERE anyc.workspace_id = asset.workspace_id"
        " AND anyc.file_id = asset.file_id)"
    )
    statement = text(
        "SELECT asset.file_id, asset.values_json, "
        f"{changed_expression} AS has_changes "
        "FROM workspace_asset AS asset "
        f"{joins} "
        "WHERE asset.workspace_id = :workspace_id "
        f"AND (:filter IS NULL OR {filter_expression} LIKE :filter) "
        f"AND (:only_changed = 0 OR {changed_expression}) "
        f"ORDER BY {order_expression} {direction}, asset.file_id {direction} "
        "LIMIT :limit OFFSET :offset"
    )
    count_statement = text(
        "SELECT COUNT(*) FROM workspace_asset AS asset "
        f"{joins} "
        "WHERE asset.workspace_id = :workspace_id "
        f"AND (:filter IS NULL OR {filter_expression} LIKE :filter) "
        f"AND (:only_changed = 0 OR {changed_expression})"
    )
    params.update(
        {
            "filter": params.get("filter"),
            "only_changed": 1 if only_changed else 0,
            "limit": count,
            "offset": start,
        }
    )
    total = int(session.execute(count_statement, params).scalar_one() or 0)
    rows = session.execute(statement, params).mappings().all()
    file_ids = [int(row["file_id"]) for row in rows]
    overrides: dict[tuple[int, str], Any] = {}
    if file_ids:
        for change in session.scalars(
            select(WorkspaceChange)
            .where(WorkspaceChange.workspace_id == workspace.id)
            .where(WorkspaceChange.file_id.in_(file_ids))
        ):
            overrides[(int(change.file_id), str(change.field_key))] = _from_text(change.new_value)
    payload = []
    for row in rows:
        file_id = int(row["file_id"])
        values = json.loads(row["values_json"])
        effective = {
            key: overrides.get((file_id, key), value) if (file_id, key) in overrides else value
            for key, value in values.items()
        }
        payload.append(
            {
                "fileId": file_id,
                **{key: display_value(value) for key, value in effective.items()},
                "__changed": bool(row["has_changes"]),
            }
        )
    return WorkspacePage(rows=payload, total=total, revision=int(workspace.edit_revision))


def resolve_targets(
    session: Session,
    workspace: Workspace,
    *,
    file_ids: Sequence[int] | None = None,
    filter_column: ColumnDef | None = None,
    filter_value: str = "",
    only_changed: bool = False,
) -> list[int]:
    """Ziel-IDs einer Massenaktion zum Zeitpunkt der Aktion."""
    if file_ids:
        return [int(value) for value in file_ids]
    page = effective_page(
        session,
        workspace,
        start=0,
        count=max(workspace.row_count, 1),
        filter_column=filter_column,
        filter_value=filter_value,
        only_changed=only_changed,
    )
    return [int(row["fileId"]) for row in page.rows]


def bulk_set(
    session: Session,
    workspace: Workspace,
    *,
    column: ColumnDef,
    value: Any,
    file_ids: Sequence[int],
    actor: AppUser | None = None,
) -> int:
    """Setzt denselben Wert auf die uebergebenen Assets; liefert wirksame Aenderungen."""
    changed = 0
    for file_id in file_ids:
        if set_change(
            session,
            workspace,
            file_id=file_id,
            column=column,
            value=value,
            actor=actor,
        ):
            changed += 1
    return changed


__all__ = [
    "DRAFT_TTL_DAYS",
    "EXPIRY_WARNING_DAYS",
    "MAX_SELECTED_COLUMNS",
    "VIEW_PARAM",
    "AssetRow",
    "ChangeEntry",
    "WorkspaceConflictError",
    "WorkspaceError",
    "WorkspacePage",
    "bulk_set",
    "changed_changes",
    "changed_count",
    "changed_file_ids",
    "clear_changes",
    "clear_columns",
    "close_workspace",
    "commit_applied",
    "create_workspace",
    "delete_workspace",
    "effective_page",
    "expiry_for",
    "expiry_warning_days",
    "file_values",
    "import_meta",
    "json_path",
    "list_workspaces",
    "load_assets",
    "mark_failed",
    "resolve_targets",
    "revert_change",
    "set_change",
    "snapshot_value",
    "store_columns",
    "store_snapshot",
    "stored_columns",
    "touch",
]
