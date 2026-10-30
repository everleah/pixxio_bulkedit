"""Excel-Schnittstelle im Format ``bulkedit-xlsx/1``.

Der Export schreibt den Snapshot des Arbeitsbestands, niemals ungeschriebene
Grid-Änderungen. Der Import vergleicht Exportbasis, Excel und aktuellen
pixx.io-Stand (Drei-Wege) und legt daraus einen neuen Arbeitsbestand mit
ChangeSet an; ohne Exportbasis ist nur ein Zwei-Wege-Vergleich möglich.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import uuid
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.i18n import t
from app.models import AppUser, Profile, Workspace, WorkspaceAsset, XlsxExport, utc_now
from app.normalize import canonical, display_value, is_empty, values_equal
from app.schema import ColumnDef, ProfileSchema
from app.scripts.errors import ScriptContractError
from app.workspaces import (
    AssetRow,
    WorkspaceError,
    changed_count,
    create_workspace,
    set_change,
    store_snapshot,
)

FORMAT = "bulkedit-xlsx"
FORMAT_VERSION = 1
FORMAT_VERSION_TEXT = "1.0"

DATA_SHEET = "Daten"
FIELDS_SHEET = "Felder"
OPTIONS_SHEET = "Auswahlwerte"
INFO_SHEET = "Info"

ID_KEY = "file_id"
ID_LABEL = "Datei-ID"
MODIFY_KEY = "@modifyDate"
MODIFY_LABEL = "Geändert in pixx.io"
INFO_PREFIX = "@"
MULTI_SEPARATOR = "; "

EXPORT_TTL_DAYS = 90
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_CELL_CHARS = 32_767
HEADER_FILL = PatternFill("solid", fgColor="E2E8F0")
ERROR_FILL = PatternFill("solid", fgColor="FCA5A5")
ERROR_SHEET = "Fehler"
ISSUE_AUTHOR = "pixx.io Bulk-Editor"
SLUG_PATTERN = re.compile(r"[^0-9A-Za-zÄÖÜäöüß._-]+")
READ_ONLY_NOTE = "nur lesen, wird beim Import ignoriert"


class XlsxError(WorkspaceError):
    """Die Excel-Datei kann nicht geschrieben oder gelesen werden."""


@dataclass(frozen=True)
class CellIssue:
    """Ein Befund zu genau einer Zelle."""

    row: int
    label: str
    message: str
    key: str = ""

    def as_text(self) -> str:
        return t(
            "Zeile {row} · {column} · {message}",
            row=self.row,
            column=self.label,
            message=self.message,
        )


@dataclass(frozen=True)
class ImportRow:
    """Eine Datenzeile der Arbeitsmappe."""

    row: int
    file_id: int
    cells: dict[str, Any]


@dataclass
class ParsedWorkbook:
    """Gelesene Arbeitsmappe vor dem Abgleich mit pixx.io."""

    info: dict[str, str]
    keys: tuple[str, ...]
    columns: dict[str, ColumnDef]
    rows: list[ImportRow]
    issues: list[CellIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def export_id(self) -> str | None:
        value = self.info.get("export_id", "").strip()
        return value or None


@dataclass(frozen=True)
class ExportResult:
    """Ergebnis eines Exports."""

    data: bytes
    filename: str
    export_id: str
    row_count: int
    pending_changes: bool


@dataclass
class DiffResult:
    """Vorschläge und Befunde des Drei-Wege-Abgleichs."""

    proposals: list[tuple[int, ColumnDef, Any]] = field(default_factory=list)
    issues: list[CellIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    """Ergebnis eines Imports."""

    workspace_id: int | None
    changed: int
    row_count: int
    three_way: bool
    issues: list[CellIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --- Export ------------------------------------------------------------------


def slugify(text: str, fallback: str) -> str:
    cleaned = SLUG_PATTERN.sub("-", (text or "").strip()).strip("-._")
    return cleaned[:60] or fallback


def export_filename(profile_name: str, script_label: str, moment: datetime) -> str:
    stamp = moment.strftime("%Y%m%d-%H%M")
    return f"{slugify(profile_name, 'profil')}_{slugify(script_label, 'export')}_{stamp}.xlsx"


def export_key(column: ColumnDef) -> str:
    """Technischer Spaltenschlüssel; nicht schreibbare Spalten sind reine Infospalten."""
    return column.key if column.writable else f"{INFO_PREFIX}{column.key}"


def _text_cell(cell: Any, value: str) -> None:
    """Text als Text schreiben, damit aus ``=``-Inhalten keine Formel wird."""
    cell.value = value
    cell.data_type = "s"


def _export_value(column: ColumnDef, value: Any) -> Any:
    if is_empty(value):
        return None
    if column.multi_value:
        items = value if isinstance(value, list | tuple) else [value]
        return MULTI_SEPARATOR.join(str(item) for item in items)
    if isinstance(value, bool | int | float):
        return value
    return str(value)


def _write_cell(
    cell: Any, key: str, value: Any, truncated: dict[int, list[str]], file_id: int
) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if len(value) > MAX_CELL_CHARS:
            value = value[:MAX_CELL_CHARS]
            truncated.setdefault(file_id, []).append(key)
        _text_cell(cell, value)
        return
    cell.value = value


def _write_header_row(ws: Any, row: int, values: Sequence[str]) -> None:
    for index, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=index)
        _text_cell(cell, value)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL


def _write_data(
    ws: Any, columns: Sequence[ColumnDef], files: Sequence[tuple[int, str | None, dict[str, Any]]]
) -> dict[int, list[str]]:
    _write_header_row(ws, 1, [ID_KEY, MODIFY_KEY, *(export_key(item) for item in columns)])
    _write_header_row(ws, 2, [t(ID_LABEL), t(MODIFY_LABEL), *(item.label for item in columns)])
    truncated: dict[int, list[str]] = {}
    for offset, (file_id, modify_date, values) in enumerate(files):
        row = 3 + offset
        ws.cell(row=row, column=1, value=int(file_id))
        if modify_date:
            _text_cell(ws.cell(row=row, column=2), str(modify_date))
        for index, column in enumerate(columns, start=3):
            _write_cell(
                ws.cell(row=row, column=index),
                column.key,
                _export_value(column, values.get(column.key)),
                truncated,
                file_id,
            )
    last_row = 2 + len(files)
    last_column = get_column_letter(2 + len(columns))
    ws.freeze_panes = "B3"
    ws.auto_filter.ref = f"A2:{last_column}{max(last_row, 2)}"
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 20
    for index in range(3, 3 + len(columns)):
        ws.column_dimensions[get_column_letter(index)].width = 28
    return truncated


def _write_options(ws: Any, columns: Sequence[ColumnDef]) -> dict[str, str]:
    letters: dict[str, str] = {}
    position = 1
    for column in columns:
        if not column.options or not column.writable:
            continue
        letter = get_column_letter(position)
        letters[column.key] = letter
        _text_cell(ws.cell(row=1, column=position), column.key)
        ws.cell(row=1, column=position).fill = HEADER_FILL
        label_cell = ws.cell(row=2, column=position)
        _text_cell(label_cell, column.label)
        label_cell.font = Font(bold=True)
        for offset, option in enumerate(column.options):
            _text_cell(ws.cell(row=3 + offset, column=position), str(option))
        ws.column_dimensions[letter].width = max(16, min(48, len(column.label) + 10))
        position += 1
    return letters


def _add_validations(
    ws: Any,
    columns: Sequence[ColumnDef],
    letters: dict[str, str],
    row_count: int,
) -> None:
    if row_count <= 0:
        return
    last_row = 2 + row_count
    for index, column in enumerate(columns, start=3):
        letter = letters.get(column.key)
        if letter is None or column.multi_value or column.edit_type != "selection":
            continue
        count = len(column.options)
        if count == 0:
            continue
        validation = DataValidation(
            type="list",
            formula1=f"{OPTIONS_SHEET}!${letter}$3:${letter}${2 + count}",
            allow_blank=True,
        )
        ws.add_data_validation(validation)
        target = get_column_letter(index)
        validation.add(f"{target}3:{target}{last_row}")


def _field_note(column: ColumnDef) -> str:
    if not column.writable:
        return t(READ_ONLY_NOTE)
    if column.multi_value:
        return t("Mehrfachwerte mit „{separator}“ trennen", separator=MULTI_SEPARATOR.strip())
    if column.options:
        return t("Auswahl aus Blatt „{sheet}“", sheet=OPTIONS_SHEET)
    return ""


def _write_fields(ws: Any, columns: Sequence[ColumnDef]) -> None:
    _write_header_row(
        ws,
        1,
        [
            t("Schlüssel"),
            t("Anzeigename"),
            t("Feldtyp"),
            t("Schreibbar"),
            t("Auswahlwerte"),
            t("Hinweis"),
        ],
    )
    for offset, column in enumerate(columns):
        row = 2 + offset
        _text_cell(ws.cell(row=row, column=1), export_key(column))
        _text_cell(ws.cell(row=row, column=2), column.label)
        _text_cell(ws.cell(row=row, column=3), column.edit_type)
        _text_cell(ws.cell(row=row, column=4), t("ja") if column.writable else t("nein"))
        _text_cell(ws.cell(row=row, column=5), MULTI_SEPARATOR.join(column.options))
        _text_cell(ws.cell(row=row, column=6), _field_note(column))
    for letter, width in (("A", 24), ("B", 32), ("C", 16), ("D", 12), ("E", 40), ("F", 32)):
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A2"


def _write_info(ws: Any, info: dict[str, str]) -> None:
    for offset, (key, value) in enumerate(info.items(), start=1):
        _text_cell(ws.cell(row=offset, column=1), key)
        ws.cell(row=offset, column=1).font = Font(bold=True)
        _text_cell(ws.cell(row=offset, column=2), str(value))
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 60


def build_workbook(
    columns: Sequence[ColumnDef],
    files: Sequence[tuple[int, str | None, dict[str, Any]]],
    info: dict[str, str],
) -> tuple[bytes, dict[int, list[str]]]:
    """Baut die Arbeitsmappe und meldet gekürzte Zellen je Datei."""
    workbook = Workbook()
    data_sheet = workbook.worksheets[0]
    data_sheet.title = DATA_SHEET
    truncated = _write_data(data_sheet, columns, files)
    letters = _write_options(workbook.create_sheet(OPTIONS_SHEET), columns)
    _add_validations(data_sheet, columns, letters, len(files))
    _write_fields(workbook.create_sheet(FIELDS_SHEET), columns)
    _write_info(workbook.create_sheet(INFO_SHEET), info)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), truncated


def _workspace_rows(
    session: Session, workspace: Workspace, columns: Sequence[ColumnDef]
) -> list[tuple[int, str | None, dict[str, Any]]]:
    assets = session.scalars(
        select(WorkspaceAsset)
        .where(WorkspaceAsset.workspace_id == workspace.id)
        .order_by(WorkspaceAsset.position)
    )
    rows: list[tuple[int, str | None, dict[str, Any]]] = []
    for asset in assets:
        values = json.loads(asset.values_json or "{}")
        rows.append(
            (
                int(asset.file_id),
                asset.modify_date,
                {column.key: values.get(column.key) for column in columns},
            )
        )
    return rows


def export_workbook(
    session: Session,
    *,
    workspace: Workspace,
    profile: Profile,
    columns: Sequence[ColumnDef],
    actor: AppUser | None = None,
    script_label: str = "",
    file_ids: Sequence[int] | None = None,
    moment: datetime | None = None,
) -> ExportResult:
    """Exportiert den Snapshot des Arbeitsbestands als Arbeitsmappe."""
    now = moment or utc_now()
    rows = _workspace_rows(session, workspace, columns)
    if file_ids is not None:
        wanted = {int(file_id) for file_id in file_ids}
        rows = [row for row in rows if row[0] in wanted]
    if not rows:
        raise XlsxError(t("Der Arbeitsbestand enthält keine Zeilen zum Export."))
    pending = changed_count(session, workspace.id) > 0
    export_id = str(uuid.uuid4())
    info = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION_TEXT,
        "export_id": export_id,
        "profile": profile.name,
        "host": profile.host,
        "script": script_label or "-",
        "exported_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "exported_by": actor.username if actor is not None else "-",
        "row_count": str(len(rows)),
        "column_count": str(len(columns)),
        "pending_changes": t("ja") if pending else t("nein"),
    }
    if pending:
        info["hinweis"] = t("Ungeschriebene Änderungen des Arbeitsbestands sind nicht enthalten.")
    data, truncated = build_workbook(columns, rows, info)
    snapshot = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "profile": profile.name,
        "host": profile.host,
        "columns": [column.key for column in columns],
        "truncated": {str(file_id): keys for file_id, keys in truncated.items()},
        "files": {
            str(file_id): {"modifyDate": modify_date or "", "values": values}
            for file_id, modify_date, values in rows
        },
    }
    session.add(
        XlsxExport(
            id=export_id,
            user_id=actor.id if actor is not None else None,
            profile_id=profile.id,
            workspace_id=workspace.id,
            columns_json=json.dumps([column.key for column in columns], ensure_ascii=False),
            snapshot_blob=gzip.compress(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")),
            row_count=len(rows),
            had_pending_changes=pending,
            created_at=now,
            expires_at=now + timedelta(days=EXPORT_TTL_DAYS),
        )
    )
    session.flush()
    return ExportResult(
        data=data,
        filename=export_filename(profile.name, script_label, now),
        export_id=export_id,
        row_count=len(rows),
        pending_changes=pending,
    )


def load_snapshot(session: Session, export_id: str | None) -> dict[str, Any] | None:
    """Liest den gespeicherten Exportstand; ``None`` wenn er fehlt."""
    if not export_id:
        return None
    export = session.get(XlsxExport, export_id)
    if export is None or not export.snapshot_blob:
        return None
    try:
        snapshot = json.loads(gzip.decompress(export.snapshot_blob).decode("utf-8"))
    except OSError, ValueError:
        return None
    return snapshot if isinstance(snapshot, dict) else None


def purge_exports(
    session: Session, *, days: int = EXPORT_TTL_DAYS, now: datetime | None = None
) -> int:
    """Löscht Export-Snapshots, die älter als die Aufbewahrungsfrist sind."""
    threshold = (now or utc_now()) - timedelta(days=days)
    exports = list(session.scalars(select(XlsxExport).where(XlsxExport.created_at < threshold)))
    for export in exports:
        session.delete(export)
    session.flush()
    return len(exports)


# --- Import ------------------------------------------------------------------


def _check_payload(data: bytes) -> None:
    if not data:
        raise XlsxError(t("Die Datei ist leer."))
    if len(data) > MAX_FILE_BYTES:
        raise XlsxError(
            t(
                "Die Datei ist größer als {size} MB.",
                size=MAX_FILE_BYTES // (1024 * 1024),
            )
        )
    if not data.startswith(b"PK"):
        raise XlsxError(t("Die Datei ist keine Excel-Arbeitsmappe (.xlsx)."))


def _check_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [item.lower() for item in archive.namelist()]
            unpacked = sum(item.file_size for item in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise XlsxError(t("Die Datei ist keine gültige Excel-Arbeitsmappe (.xlsx).")) from exc
    if any(name.endswith("vbaproject.bin") for name in names):
        raise XlsxError(t("Arbeitsmappen mit Makros werden nicht unterstützt."))
    if unpacked > MAX_UNPACKED_BYTES:
        raise XlsxError(t("Die entpackte Arbeitsmappe ist zu groß."))


def _cell_text(cell: Any) -> str:
    value = getattr(cell, "value", None)
    return "" if value is None else str(value).strip()


def _read_info(ws: Any) -> dict[str, str]:
    info: dict[str, str] = {}
    for row in ws.iter_rows(values_only=False):
        cells = list(row)
        if len(cells) < 2:
            continue
        key = _cell_text(cells[0])
        if key:
            info[key] = _cell_text(cells[1])
    return info


def _as_file_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _read_data(
    ws: Any,
    columns: Sequence[ColumnDef],
    info: dict[str, str],
    max_rows: int | None,
) -> ParsedWorkbook:
    lookup = {column.key: column for column in columns}
    issues: list[CellIssue] = []
    warnings: list[str] = []
    iterator = iter(ws.iter_rows(values_only=False))
    header = next(iterator, None)
    labels = next(iterator, None)
    if header is None:
        raise XlsxError(t("Das Blatt „{sheet}“ ist leer.", sheet=DATA_SHEET))
    header_keys = [_cell_text(cell) for cell in header]
    if not header_keys or header_keys[0] != ID_KEY:
        raise XlsxError(t("Spalte A muss den Schlüssel „file_id“ enthalten."))
    label_values = [_cell_text(cell) for cell in (labels or [])]

    resolved: dict[int, ColumnDef] = {}
    labels_by_index: dict[int, str] = {}
    ignored: list[str] = []
    seen: set[str] = set()
    for index, key in enumerate(header_keys):
        if index == 0 or key in {MODIFY_KEY, ""}:
            continue
        if key.startswith(INFO_PREFIX):
            continue
        column = lookup.get(key)
        if column is None:
            raise XlsxError(t("Unbekannter Spaltenschlüssel: {key}", key=key))
        if key in seen:
            raise XlsxError(t("Der Spaltenschlüssel {key} kommt doppelt vor.", key=key))
        seen.add(key)
        if not column.writable:
            ignored.append(column.label)
            continue
        resolved[index] = column
        label = label_values[index] if index < len(label_values) else ""
        labels_by_index[index] = label or column.label
    if ignored:
        warnings.append(
            t(
                "Nur lesbare Spalten werden ignoriert: {columns}",
                columns=", ".join(ignored),
            )
        )
    if not resolved:
        raise XlsxError(t("Die Datei enthält keine schreibbaren Spalten."))

    rows: list[ImportRow] = []
    seen_ids: set[int] = set()
    row_number = 2
    for cells in iterator:
        row_number += 1
        if not cells:
            continue
        raw_id = getattr(cells[0], "value", None)
        if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
            continue
        file_id = _as_file_id(raw_id)
        if file_id is None:
            issues.append(
                CellIssue(
                    row_number,
                    t(ID_LABEL),
                    t("Die Datei-ID „{value}“ ist keine Zahl.", value=raw_id),
                    key=ID_KEY,
                )
            )
            continue
        if file_id in seen_ids:
            issues.append(
                CellIssue(
                    row_number,
                    t(ID_LABEL),
                    t("Die Datei-ID {id} kommt mehrfach vor.", id=file_id),
                    key=ID_KEY,
                )
            )
            continue
        seen_ids.add(file_id)
        values: dict[str, Any] = {}
        for index, column in resolved.items():
            cell = cells[index] if index < len(cells) else None
            if getattr(cell, "data_type", None) == "f":
                issues.append(
                    CellIssue(
                        row_number,
                        labels_by_index[index],
                        t("Formeln werden nicht unterstützt."),
                        key=column.key,
                    )
                )
                continue
            raw = getattr(cell, "value", None)
            try:
                canonical(column.edit_type, raw, options=column.options)
            except ScriptContractError as exc:
                issues.append(
                    CellIssue(row_number, labels_by_index[index], str(exc), key=column.key)
                )
                continue
            values[column.key] = raw
        rows.append(ImportRow(row=row_number, file_id=file_id, cells=values))
        if max_rows is not None and len(rows) > max_rows:
            raise XlsxError(
                t("Die Datei enthält mehr Zeilen als das Profillimit von {rows}.", rows=max_rows)
            )
    return ParsedWorkbook(
        info=info,
        keys=tuple(column.key for column in resolved.values()),
        columns={column.key: column for column in resolved.values()},
        rows=rows,
        issues=issues,
        warnings=warnings,
    )


def parse_workbook(
    data: bytes, columns: Sequence[ColumnDef], *, max_rows: int | None = None
) -> ParsedWorkbook:
    """Liest eine Arbeitsmappe und prüft Format, Schlüssel und Grenzen."""
    _check_payload(data)
    _check_archive(data)
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except Exception as exc:  # noqa: BLE001 - openpyxl meldet sehr unterschiedlich
        raise XlsxError(
            t("Die Arbeitsmappe konnte nicht gelesen werden: {error}", error=str(exc))
        ) from exc
    try:
        for name in (DATA_SHEET, INFO_SHEET):
            if name not in workbook.sheetnames:
                raise XlsxError(
                    t(
                        "Die Datei ist keine Arbeitsmappe des Bulk-Editors (Blatt „{sheet}“ fehlt).",
                        sheet=name,
                    )
                )
        info = _read_info(workbook[INFO_SHEET])
        if info.get("format") != FORMAT:
            raise XlsxError(t("Unbekanntes Format: {value}", value=info.get("format") or "-"))
        try:
            version = int(float(info.get("format_version") or "0"))
        except ValueError:
            version = 0
        if version != FORMAT_VERSION:
            raise XlsxError(
                t(
                    "Das Format hat Version {version}; unterstützt wird Version {supported}.",
                    version=info.get("format_version") or "-",
                    supported=FORMAT_VERSION_TEXT,
                )
            )
        return _read_data(workbook[DATA_SHEET], columns, info, max_rows)
    finally:
        workbook.close()


def _base_values(base: dict[str, Any] | None, file_id: int) -> dict[str, Any] | None:
    if base is None:
        return None
    entry = base.get(str(file_id))
    if not isinstance(entry, dict):
        return {}
    values = entry.get("values")
    return values if isinstance(values, dict) else {}


def diff_rows(
    parsed: ParsedWorkbook,
    *,
    current: dict[int, dict[str, Any]],
    base: dict[str, Any] | None = None,
    truncated: dict[str, set[str]] | None = None,
    clear_empty: bool = False,
) -> DiffResult:
    """Vergleicht Excel, Exportbasis und aktuellen Stand und schlägt Änderungen vor."""
    result = DiffResult(issues=list(parsed.issues), warnings=list(parsed.warnings))
    cut_cells = truncated or {}
    conflicts = 0
    for row in parsed.rows:
        values = current.get(row.file_id)
        if values is None:
            result.issues.append(
                CellIssue(
                    row.row,
                    t(ID_LABEL),
                    t("Die Datei ist nicht mehr vorhanden oder nicht sichtbar."),
                    key=ID_KEY,
                )
            )
            continue
        old_values = _base_values(base, row.file_id)
        cut = cut_cells.get(str(row.file_id), set())
        for key, raw in row.cells.items():
            column = parsed.columns[key]
            try:
                value = canonical(column.edit_type, raw, options=column.options)
            except ScriptContractError as exc:
                result.issues.append(CellIssue(row.row, column.label, str(exc), key=key))
                continue
            if old_values is not None:
                old = old_values.get(key)
                if values_equal(value, old):
                    continue
                if (
                    key in cut
                    and isinstance(old, str)
                    and values_equal(value, old[:MAX_CELL_CHARS])
                ):
                    continue
                live = values.get(key)
                if values_equal(live, old):
                    result.proposals.append((row.file_id, column, value))
                elif values_equal(live, value):
                    continue
                else:
                    conflicts += 1
                    result.issues.append(
                        CellIssue(
                            row.row,
                            column.label,
                            t(
                                "In pixx.io steht inzwischen „{current}“; die Zelle wird übersprungen.",
                                current=display_value(live),
                            ),
                            key=key,
                        )
                    )
                continue
            if is_empty(value):
                if not clear_empty or is_empty(values.get(key)):
                    continue
                result.proposals.append((row.file_id, column, None))
                continue
            if values_equal(value, values.get(key)):
                continue
            result.proposals.append((row.file_id, column, value))
    if conflicts:
        result.warnings.append(
            t(
                "{count} Zellen wurden wegen zwischenzeitlicher Änderungen übersprungen.",
                count=conflicts,
            )
        )
    return result


def has_snapshot(session: Session, parsed: ParsedWorkbook) -> bool:
    """Ob zum ``export_id`` der Datei noch ein Exportstand vorliegt."""
    return load_snapshot(session, parsed.export_id) is not None


def import_workbook(
    session: Session,
    *,
    owner: AppUser,
    profile: Profile,
    schema: ProfileSchema,
    client: Any,
    data: bytes,
    filename: str,
    clear_empty: bool = False,
    moment: datetime | None = None,
) -> ImportResult:
    """Legt aus einer Arbeitsmappe einen Arbeitsbestand mit ChangeSet an."""
    from app.writer import read_files

    parsed = parse_workbook(data, schema.columns(), max_rows=profile.max_rows)
    host = parsed.info.get("host", "").strip()
    if host and host != profile.host:
        raise XlsxError(
            t(
                "Die Datei wurde für den Host „{host}“ erstellt, nicht für „{profile}“.",
                host=host,
                profile=profile.host,
            )
        )
    if not parsed.rows:
        raise XlsxError(t("Die Datei enthält keine Datenzeilen."))
    snapshot = load_snapshot(session, parsed.export_id)
    base: dict[str, Any] | None = None
    truncated: dict[str, set[str]] = {}
    if snapshot is not None:
        files = snapshot.get("files")
        base = files if isinstance(files, dict) else {}
        raw_truncated = snapshot.get("truncated")
        if isinstance(raw_truncated, dict):
            truncated = {
                str(file_id): {str(key) for key in keys}
                for file_id, keys in raw_truncated.items()
                if isinstance(keys, list)
            }
    columns = [parsed.columns[key] for key in parsed.keys]
    current_raw = read_files(client, columns, [row.file_id for row in parsed.rows])
    current = {file_id: item["values"] for file_id, item in current_raw.items()}
    modify_dates = {file_id: item["modifyDate"] for file_id, item in current_raw.items()}
    diff = diff_rows(
        parsed,
        current=current,
        base=base,
        truncated=truncated,
        clear_empty=clear_empty,
    )
    three_way = base is not None
    if not diff.proposals:
        return ImportResult(
            workspace_id=None,
            changed=0,
            row_count=len(parsed.rows),
            three_way=three_way,
            issues=diff.issues,
            warnings=diff.warnings,
        )
    now = moment or utc_now()
    meta = {
        "filename": filename,
        "export_id": parsed.export_id,
        "three_way": three_way,
        "clear_empty": clear_empty,
        "imported_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "rows": len(parsed.rows),
    }
    name = f"{t('Excel-Import')}: {filename}"[:200]
    workspace = create_workspace(
        session, owner=owner, profile=profile, name=name, params={"xlsx": meta}
    )
    store_snapshot(
        session,
        workspace,
        [
            AssetRow(
                file_id=row.file_id,
                modify_date=modify_dates.get(row.file_id),
                values=current[row.file_id],
            )
            for row in parsed.rows
            if row.file_id in current
        ],
    )
    changed = 0
    for file_id, column, value in diff.proposals:
        if set_change(session, workspace, file_id=file_id, column=column, value=value, actor=owner):
            changed += 1
    return ImportResult(
        workspace_id=workspace.id,
        changed=changed,
        row_count=workspace.row_count,
        three_way=three_way,
        issues=diff.issues,
        warnings=diff.warnings,
    )


def error_filename(filename: str, moment: datetime | None = None) -> str:
    """Name der Fehlerdatei zu einer hochgeladenen Arbeitsmappe."""
    stem = Path(filename or "import").stem or "import"
    stamp = (moment or utc_now()).strftime("%Y%m%d-%H%M")
    return f"{slugify(stem, 'import')}_fehler_{stamp}.xlsx"


def build_error_workbook(
    data: bytes,
    *,
    issues: Sequence[CellIssue],
    filename: str = "",
    moment: datetime | None = None,
) -> tuple[bytes, str]:
    """Kopie der Arbeitsmappe mit markierten Problemzellen und Blatt ``Fehler``.

    Die Kopie bleibt importierbar: Nach dem Korrigieren der markierten Zellen kann
    dieselbe Datei erneut hochgeladen werden.
    """
    _check_payload(data)
    workbook = load_workbook(io.BytesIO(data), data_only=False)
    if DATA_SHEET in workbook.sheetnames:
        sheet = workbook[DATA_SHEET]
        keys = {
            _cell_text(cell): index
            for index, cell in enumerate(sheet[1], start=1)
            if _cell_text(cell)
        }
        labels: dict[str, int] = {}
        if sheet.max_row >= 2:
            labels = {
                _cell_text(cell): index
                for index, cell in enumerate(sheet[2], start=1)
                if _cell_text(cell)
            }
        for issue in issues:
            index = keys.get(issue.key or "") or labels.get(issue.label) or 1
            cell = sheet.cell(row=max(1, issue.row), column=index)
            cell.fill = ERROR_FILL
            cell.comment = Comment(issue.message, ISSUE_AUTHOR)
    report = (
        workbook[ERROR_SHEET]
        if ERROR_SHEET in workbook.sheetnames
        else workbook.create_sheet(ERROR_SHEET)
    )
    _write_header_row(report, 1, [t("Zeile"), t("Spalte"), t("Meldung")])
    for offset, issue in enumerate(issues, start=1):
        report.cell(row=1 + offset, column=1, value=int(issue.row))
        _text_cell(report.cell(row=1 + offset, column=2), issue.label)
        _text_cell(report.cell(row=1 + offset, column=3), issue.message)
    report.column_dimensions["A"].width = 10
    report.column_dimensions["B"].width = 28
    report.column_dimensions["C"].width = 80
    report.freeze_panes = "A2"
    if INFO_SHEET in workbook.sheetnames:
        info_sheet = workbook[INFO_SHEET]
        existing = {_cell_text(cell) for cell in info_sheet["A"]}
        row = info_sheet.max_row + 1
        additions = (
            ("fehler", str(len(issues))),
            ("hinweis", t("Fehlerdatei: markierte Zellen prüfen, dann erneut importieren.")),
        )
        for key_name, value in additions:
            if key_name in existing:
                continue
            key_cell = info_sheet.cell(row=row, column=1)
            _text_cell(key_cell, key_name)
            key_cell.font = Font(bold=True)
            _text_cell(info_sheet.cell(row=row, column=2), value)
            row += 1
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), error_filename(filename, moment)


def document_summary(parsed: ParsedWorkbook) -> list[str]:
    """Kurzfassung der gelesenen Arbeitsmappe für die Oberfläche."""
    lines = [
        t(
            "Format {format} {version}",
            format=FORMAT,
            version=parsed.info.get("format_version", "-"),
        ),
        t("Profil: {profile}", profile=parsed.info.get("profile") or "-"),
        t("{count} Datenzeilen", count=len(parsed.rows)),
        t("{count} Spalten", count=len(parsed.keys)),
    ]
    exported_at = parsed.info.get("exported_at")
    if exported_at:
        lines.append(t("Exportiert am {moment}", moment=exported_at))
    return lines


def iter_issue_texts(issues: Iterable[CellIssue]) -> list[str]:
    return [issue.as_text() for issue in issues]


__all__ = [
    "FORMAT",
    "FORMAT_VERSION",
    "MAX_FILE_BYTES",
    "MAX_CELL_CHARS",
    "CellIssue",
    "DiffResult",
    "ExportResult",
    "ImportResult",
    "ParsedWorkbook",
    "XlsxError",
    "build_error_workbook",
    "build_workbook",
    "diff_rows",
    "document_summary",
    "error_filename",
    "export_filename",
    "export_key",
    "export_workbook",
    "has_snapshot",
    "import_workbook",
    "iter_issue_texts",
    "load_snapshot",
    "parse_workbook",
    "purge_exports",
    "slugify",
]
