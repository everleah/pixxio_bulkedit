"""Schreibplan: Änderungen validieren, Payloads bilden, gruppieren und speichern.

Ein Plan ist unveränderlich und über einen Digest an das ChangeSet gebunden. Dry Run
und Live-Lauf verwenden denselben Plan; ändert sich der Entwurf, verliert er die Gültigkeit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.i18n import t
from app.models import AppUser, Workspace, WorkspaceAsset, WritePlan, WritePlanStep
from app.models.enums import PlanStatus, RunMode
from app.normalize import display_value, is_empty
from app.schema import ColumnDef, ProfileSchema, resolve_columns
from app.scripts.errors import ScriptContractError
from app.workspaces import WorkspaceError, changed_changes

CHUNK_SIZE = 200
METADATA_ACTIONS = ("replace", "remove")

FILE_STATE_KEY = "std:fileStateID"
FILE_STATE_FIELD = "fileStateID"
FILE_STATE_TRUNCATE = "truncateFileState"
FILE_STATE_COMMENT = "fileStateChangeComment"

# Standardattribute und ihre filesPut-Felder (Setzen / Leeren).
FILE_ATTR_FIELDS: dict[str, tuple[str, str]] = {
    "subject": ("subject", "truncateSubject"),
    "description": ("description", "truncateDescription"),
    "creator": ("creator", "truncateCreator"),
    "rating": ("rating", "truncateRating"),
    "createDate": ("createDate", "truncateCreateDate"),
    "location": ("location", "truncateLocation"),
    "fileStateID": ("fileStateID", "truncateFileState"),
}

METADATA_FIELD = "metadataCustom"
STANDARD_FIELD = "metadataStandard"


class WritePlanError(WorkspaceError):
    """Der Plan kann aus dem ChangeSet nicht gebildet werden."""


@dataclass(frozen=True)
class PlannedChange:
    """Eine Feldänderung mit Anzeige- und Schreibwert."""

    file_id: int
    key: str
    label: str
    old_value: Any
    new_value: Any

    @property
    def old_display(self) -> str:
        return display_value(self.old_value)

    @property
    def new_display(self) -> str:
        return display_value(self.new_value)


@dataclass(frozen=True)
class PlannedStep:
    """Eine filesPut-Anfrage: gleiche Payload für mehrere IDs."""

    ids: tuple[int, ...]
    payload: dict[str, Any]

    @property
    def payload_hash(self) -> str:
        return payload_digest(self.payload)


@dataclass
class PlanPreview:
    """Ergebnis der Planbildung vor dem Speichern."""

    changes: list[PlannedChange] = field(default_factory=list)
    steps: list[PlannedStep] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    digest: str = ""
    conflict_files: list[int] = field(default_factory=list)
    comment: str = ""
    requires_comment: bool = False

    @property
    def changed_cells(self) -> int:
        return len(self.changes)

    @property
    def affected_files(self) -> int:
        return len({change.file_id for change in self.changes})


def canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(payload).encode("utf-8")).hexdigest()


def change_digest(changes: Iterable[tuple[int, str, str]]) -> str:
    """Digest über (Datei, Feld, neuer Wert) für die Gültigkeitsprüfung."""
    material = "\n".join(sorted(f"{file_id}\t{key}\t{value}" for file_id, key, value in changes))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def current_digest(session: Session, workspace_id: int, *, comment: str = "") -> str:
    """Digest des ChangeSets plus Kommentar (der Kommentar gehört zum Plan)."""
    changes = list(
        (entry.file_id, entry.key, canonical_payload({"value": entry.new_value}))
        for entry in changed_changes(session, workspace_id)
    )
    if comment.strip():
        changes.append((-1, "comment", comment.strip()))
    return change_digest(changes)


def _metadata_namespace(column: ColumnDef) -> SimpleNamespace:
    """Feldbeschreibung im Format des Client-Builders."""
    options = [{"id": option_id, "name": name} for option_id, name in column.option_ids] or [
        {"id": index + 1, "name": name} for index, name in enumerate(column.options)
    ]
    return SimpleNamespace(
        id=column.field_id,
        name=column.label,
        editType=column.edit_type,
        selectionOptions=options,
    )


def _check_options(column: ColumnDef, value: Any) -> None:
    """Auswahlwerte muessen zu den Optionen des Feldes passen."""
    if column.edit_type not in {"selection", "multiselection"} or not column.options:
        return
    known = set(column.options)
    values = value if isinstance(value, list) else [value]
    unknown = [str(item) for item in values if str(item) not in known]
    if unknown:
        raise ScriptContractError(
            t(
                "Unbekannte Auswahl für {label}: {values}",
                label=column.label,
                values=", ".join(unknown),
            )
        )


def _write_value(column: ColumnDef, value: Any) -> dict[str, Any]:
    """Bildet den Metadaten-Eintrag für ein Feld (leer wird zu ``remove``)."""
    if is_empty(value):
        return {"action": "remove", "id": int(column.field_id or 0)}
    _check_options(column, value)
    from pixxio_client.metadata import MetadataValueBuilder

    builder = MetadataValueBuilder([_metadata_namespace(column)])
    builder.append("replace", int(column.field_id or 0), value)
    entries = builder.build()
    if not entries:
        raise ScriptContractError(
            t("Der Wert für {label!r} konnte nicht umgewandelt werden.", label=column.label)
        )
    return entries[0]


def _file_attr_payload(attribute: str, value: Any) -> dict[str, Any] | None:
    mapping = FILE_ATTR_FIELDS.get(attribute)
    if mapping is None:
        return None
    field_name, truncate_name = mapping
    if is_empty(value):
        return {truncate_name: True}
    return {field_name: value}


def _state_id(column: ColumnDef, value: Any) -> int:
    """Dateistatus-Namen auf die API-ID abbilden."""
    mapping = {name: state_id for state_id, name in column.option_ids}
    text = str(value).strip()
    state_id = mapping.get(text)
    if state_id is None:
        raise ScriptContractError(t("Unbekannter Dateistatus: {value}", value=text))
    return state_id


def _keywords_payload(old_value: Any, new_value: Any) -> dict[str, Any]:
    old_set = {str(item) for item in (old_value or [])} if isinstance(old_value, list) else set()
    new_set = {str(item) for item in (new_value or [])} if isinstance(new_value, list) else set()
    payload: dict[str, Any] = {}
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    if added:
        payload["keywordsToAdd"] = added
    if removed:
        payload["keywordsToRemove"] = removed
    return payload


def build_preview(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    script_columns: Sequence[str] | None,
    *,
    comment: str = "",
) -> PlanPreview:
    """Prüft das ChangeSet und bildet die Schreibschritte."""
    preview = PlanPreview()
    preview.comment = comment.strip()
    entries = changed_changes(session, workspace.id)
    if not entries:
        preview.errors.append(t("Es gibt keine Änderungen."))
        preview.digest = change_digest([])
        return preview

    column_keys = list({entry.key for entry in entries})
    columns, unknown = resolve_columns(schema, column_keys)
    by_key = {column.key: column for column in columns}
    preview.requires_comment = any(column.key == FILE_STATE_KEY for column in columns)
    if preview.requires_comment and not preview.comment:
        preview.errors.append(
            t("Ein Statuswechsel verlangt einen Kommentar ({field}).", field=FILE_STATE_FIELD)
        )
    for key in unknown:
        preview.errors.append(t("Unbekannte Spalte: {key}", key=key))
    available = set(script_columns or []) or None
    if available is not None:
        for key in column_keys:
            if key not in available and key not in unknown:
                preview.errors.append(
                    t("Die Spalte {key} gehört nicht zum Arbeitsbestand.", key=key)
                )

    per_file: dict[int, dict[str, Any]] = {}
    for entry in entries:
        column = by_key.get(entry.key)
        if column is None:
            continue
        if not column.writable:
            preview.errors.append(
                t("Die Spalte {label!r} ist nicht schreibbar.", label=column.label)
            )
            continue
        preview.changes.append(
            PlannedChange(
                file_id=entry.file_id,
                key=entry.key,
                label=column.label,
                old_value=entry.old_value,
                new_value=entry.new_value,
            )
        )
        try:
            payload = _payload_for(column, entry.old_value, entry.new_value)
        except (ScriptContractError, ValueError) as exc:
            preview.errors.append(t("{label}: {message}", label=column.label, message=str(exc)))
            continue
        if not payload:
            continue
        merged = per_file.setdefault(entry.file_id, {})
        for key, value in payload.items():
            if key in merged and merged[key] != value:
                preview.errors.append(
                    t(
                        "{label}: widersprüchliche Werte im selben Schreibvorgang.",
                        label=column.label,
                    )
                )
            merged[key] = value

    grouped: dict[str, list[int]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for file_id, payload in per_file.items():
        if not payload:
            continue
        if FILE_STATE_FIELD in payload or FILE_STATE_TRUNCATE in payload:
            payload[FILE_STATE_COMMENT] = preview.comment
        digest = payload_digest(payload)
        grouped.setdefault(digest, []).append(file_id)
        payloads[digest] = payload
    for digest, ids in grouped.items():
        ordered = sorted(ids)
        for start in range(0, len(ordered), CHUNK_SIZE):
            preview.steps.append(
                PlannedStep(
                    ids=tuple(ordered[start : start + CHUNK_SIZE]), payload=payloads[digest]
                )
            )

    preview.digest = current_digest(session, workspace.id, comment=preview.comment)
    if not preview.steps and not preview.errors:
        preview.errors.append(t("Die Änderungen ergeben keinen Schreibvorgang."))
    return preview


def _payload_for(column: ColumnDef, old_value: Any, new_value: Any) -> dict[str, Any]:
    if column.source == "file_attr":
        attribute = column.key.split(":", 1)[1]
        if attribute == "keywords":
            return _keywords_payload(old_value, new_value)
        if attribute == "fileStateID":
            if is_empty(new_value):
                return {"truncateFileState": True}
            return {"fileStateID": _state_id(column, new_value)}
        payload = _file_attr_payload(attribute, new_value)
        if payload is None:
            raise ScriptContractError(
                t("Das Attribut {attribute!r} ist nicht schreibbar.", attribute=attribute)
            )
        return payload
    field_name = METADATA_FIELD if column.source == "custom" else STANDARD_FIELD
    return {field_name: [_write_value(column, new_value)]}


def preview_summary(preview: PlanPreview) -> dict[str, Any]:
    """Kurzfassung für Review und Statuszeile."""
    return {
        "changes": preview.changed_cells,
        "files": preview.affected_files,
        "steps": len(preview.steps),
        "errors": list(preview.errors),
        "warnings": list(preview.warnings),
        "conflicts": list(preview.conflict_files),
        "digest": preview.digest,
    }


def save_plan(
    session: Session,
    workspace: Workspace,
    preview: PlanPreview,
    *,
    actor: AppUser | None,
    mode: RunMode = RunMode.DRY_RUN,
) -> WritePlan:
    """Speichert den Plan unveränderlich mit seinen Schritten."""
    if preview.errors:
        raise WritePlanError(t("Der Plan enthält Fehler und kann nicht gespeichert werden."))
    plan = WritePlan(
        workspace_id=workspace.id,
        mode=mode,
        status=PlanStatus.DRAFT,
        change_digest=preview.digest,
        plan_json=json.dumps(
            {
                "changes": [
                    {
                        "file_id": change.file_id,
                        "key": change.key,
                        "label": change.label,
                        "old": change.old_display,
                        "new": change.new_display,
                    }
                    for change in preview.changes
                ],
                "warnings": preview.warnings,
                "conflicts": preview.conflict_files,
                "comment": preview.comment,
            },
            ensure_ascii=False,
        ),
        step_count=len(preview.steps),
        created_by_id=actor.id if actor is not None else None,
    )
    session.add(plan)
    session.flush()
    for index, step in enumerate(preview.steps, start=1):
        session.add(
            WritePlanStep(
                plan_id=plan.id,
                step_no=index,
                ids_json=json.dumps(list(step.ids)),
                payload_json=canonical_payload(step.payload),
                payload_hash=step.payload_hash,
            )
        )
    session.flush()
    return plan


def latest_plan(session: Session, workspace_id: int) -> WritePlan | None:
    return session.scalars(
        select(WritePlan)
        .where(WritePlan.workspace_id == workspace_id)
        .order_by(WritePlan.id.desc())
        .limit(1)
    ).first()


def plan_steps(session: Session, plan: WritePlan) -> list[WritePlanStep]:
    return list(
        session.scalars(
            select(WritePlanStep)
            .where(WritePlanStep.plan_id == plan.id)
            .order_by(WritePlanStep.step_no)
        )
    )


def plan_is_current(preview: PlanPreview, plan: WritePlan) -> bool:
    """Der Plan gilt nur für genau dieses ChangeSet."""
    return plan.change_digest == preview.digest


def plan_comment(plan: WritePlan) -> str:
    """Der im Plan gespeicherte Kommentar (Pflicht bei Statuswechsel)."""
    stored = json.loads(plan.plan_json or "{}")
    return str(stored.get("comment") or "")


def modify_dates(session: Session, workspace_id: int, file_ids: Sequence[int]) -> dict[int, str]:
    """Gespeicherte ``modifyDate``-Werte aus dem Snapshot."""
    if not file_ids:
        return {}
    rows = session.execute(
        select(WorkspaceAsset.file_id, WorkspaceAsset.modify_date).where(
            WorkspaceAsset.workspace_id == workspace_id,
            WorkspaceAsset.file_id.in_(list(file_ids)),
        )
    ).all()
    return {int(row.file_id): str(row.modify_date or "") for row in rows}


def detect_conflicts(
    session: Session,
    workspace: Workspace,
    preview: PlanPreview,
    current: dict[int, str],
) -> list[int]:
    """Dateien, deren ``modifyDate`` seit dem Laden abweicht."""
    file_ids = sorted({change.file_id for change in preview.changes})
    stored = modify_dates(session, workspace.id, file_ids)
    conflicts = [
        file_id
        for file_id, modify_date in current.items()
        if stored.get(int(file_id), "") not in {"", str(modify_date or "")}
    ]
    preview.conflict_files = sorted(set(conflicts))
    if preview.conflict_files:
        preview.warnings.append(
            t(
                "Externe Änderungen erkannt: {files}",
                files=", ".join(str(file_id) for file_id in preview.conflict_files),
            )
        )
    return preview.conflict_files


__all__ = [
    "CHUNK_SIZE",
    "FILE_ATTR_FIELDS",
    "PlanPreview",
    "PlannedChange",
    "PlannedStep",
    "WritePlanError",
    "build_preview",
    "canonical_payload",
    "change_digest",
    "current_digest",
    "detect_conflicts",
    "latest_plan",
    "modify_dates",
    "payload_digest",
    "plan_comment",
    "plan_is_current",
    "plan_steps",
    "preview_summary",
    "save_plan",
]
