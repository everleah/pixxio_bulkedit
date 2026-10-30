"""Tests der Excel-Schnittstelle (Export, Import, Drei-Wege-Abgleich)."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import xlsx
from app.auth import create_user
from app.models import AppUser, Profile, Run, Workspace, XlsxExport
from app.models.enums import RunMode, RunSource
from app.profiles import ProfileData, create_profile
from app.schema import ColumnDef, MetadataField, ProfileSchema
from app.workspaces import (
    AssetRow,
    changed_changes,
    create_workspace,
    store_snapshot,
)
from app.writeplan import build_preview, save_plan
from app.writer import dry_run
from app.xlsx import ERROR_SHEET, XlsxError

FILENAME = ColumnDef(key="std:fileName", label="Dateiname", source="file_attr", edit_type="text")
SUBJECT = ColumnDef(key="std:subject", label="Titel", source="file_attr", edit_type="text")
KEYWORDS = ColumnDef(
    key="std:keywords", label="Schlagwörter", source="file_attr", edit_type="multiselection"
)
CAMPAIGN = ColumnDef(
    key="custom:4711",
    label="Kampagne",
    source="custom",
    edit_type="selection",
    field_id=4711,
    options=("A", "B"),
    option_ids=((11, "A"), (12, "B")),
)
COLUMNS = (FILENAME, SUBJECT, KEYWORDS, CAMPAIGN)
SCHEMA = ProfileSchema(
    custom=(
        MetadataField(
            kind="custom",
            id=4711,
            name="Kampagne",
            edit_type="selection",
            options=("A", "B"),
            option_ids=((11, "A"), (12, "B")),
        ),
    ),
    file_attrs=("fileName", "subject", "keywords"),
)
MOMENT = datetime(2026, 10, 30, 15, 11, 0)


class FakeFiles:
    """Minimaler Ersatz fuer ``pixxio_client.files.File`` (nur Lesen)."""

    store: dict[int, dict[str, Any]] = {}

    def __init__(self, client: Any = None) -> None:
        self.client = client

    def iter_all(self, filter: Any = None, page_size: int = 100, max_items: Any = None) -> Any:
        ids = list(filter["fileIDs"]) if filter else list(self.store)
        for file_id in ids:
            item = self.store.get(int(file_id))
            if item is not None:
                yield json.loads(json.dumps(item))


@pytest.fixture(autouse=True)
def _fake() -> None:
    FakeFiles.store = {
        1: {
            "id": 1,
            "modifyDate": "2026-10-01 10:00:00",
            "fileName": "eins.jpg",
            "subject": "Alt 1",
            "keywords": ["rot"],
            "metadataFields": {"4711": {"id": 4711, "value": "A"}},
        },
        2: {
            "id": 2,
            "modifyDate": "2026-10-01 10:00:00",
            "fileName": "zwei.jpg",
            "subject": "Alt 2",
            "keywords": ["rot"],
            "metadataFields": {"4711": {"id": 4711, "value": "A"}},
        },
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pixxio_client.files.File", FakeFiles)


@pytest.fixture
def box(master_key: str) -> Any:
    from app.crypto import SecretBox

    return SecretBox(master_key)


@pytest.fixture
def owner(session: Session) -> AppUser:
    return create_user(session, username="excel", password="ein-langes-passwort")


@pytest.fixture
def profile(session: Session, box: Any, owner: AppUser) -> Profile:
    return create_profile(
        session,
        box,
        ProfileData(name="excel", host="demo.px.media", api_key="api-key-mit-32-zeichen-laenge"),
        actor=owner,
    )


def _rows(overrides: dict[int, dict[str, Any]] | None = None) -> list[AssetRow]:
    base = {
        1: {
            "std:fileName": "eins.jpg",
            "std:subject": "Alt 1",
            "std:keywords": ["rot"],
            "custom:4711": "A",
        },
        2: {
            "std:fileName": "zwei.jpg",
            "std:subject": "Alt 2",
            "std:keywords": ["rot"],
            "custom:4711": "A",
        },
    }
    base.update(overrides or {})
    return [
        AssetRow(file_id=file_id, modify_date="2026-10-01 10:00:00", values=values)
        for file_id, values in base.items()
    ]


@pytest.fixture
def workspace(session: Session, owner: AppUser, profile: Profile) -> Workspace:
    created = create_workspace(session, owner=owner, profile=profile, name="Excel")
    store_snapshot(session, created, _rows())
    return created


def _export(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, **kwargs: Any
) -> xlsx.ExportResult:
    return xlsx.export_workbook(
        session,
        workspace=workspace,
        profile=profile,
        columns=COLUMNS,
        actor=owner,
        script_label="Auswahl",
        moment=MOMENT,
        **kwargs,
    )


def _sheet(data: bytes, name: str) -> Any:
    return load_workbook(io.BytesIO(data), data_only=False)[name]


def _info(data: bytes) -> dict[str, Any]:
    sheet = _sheet(data, xlsx.INFO_SHEET)
    info: dict[str, Any] = {}
    for row in range(1, sheet.max_row + 1):
        key = sheet.cell(row=row, column=1).value
        if key is not None:
            info[key] = sheet.cell(row=row, column=2).value
    return info


def _edit(data: bytes, sheet_name: str, cell: str, value: Any) -> bytes:
    workbook = load_workbook(io.BytesIO(data), data_only=False)
    workbook[sheet_name][cell] = value
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _header(data: bytes) -> list[str]:
    sheet = _sheet(data, xlsx.DATA_SHEET)
    return [sheet.cell(row=1, column=index).value for index in range(1, sheet.max_column + 1)]


def _import(
    session: Session,
    profile: Profile,
    owner: AppUser,
    data: bytes,
    *,
    clear_empty: bool = False,
) -> xlsx.ImportResult:
    return xlsx.import_workbook(
        session,
        owner=owner,
        profile=profile,
        schema=SCHEMA,
        client=object(),
        data=data,
        filename="probe.xlsx",
        clear_empty=clear_empty,
        moment=MOMENT,
    )


# --- Export ------------------------------------------------------------------


def test_export_hat_vier_blatt_und_info(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    result = _export(session, workspace, profile, owner)
    workbook = load_workbook(io.BytesIO(result.data))
    assert workbook.sheetnames == [
        xlsx.DATA_SHEET,
        xlsx.OPTIONS_SHEET,
        xlsx.FIELDS_SHEET,
        xlsx.INFO_SHEET,
    ]
    info = _info(result.data)
    assert info["format"] == xlsx.FORMAT
    assert info["format_version"] == xlsx.FORMAT_VERSION_TEXT
    assert info["host"] == "demo.px.media"
    assert info["row_count"] == "2"
    assert info["export_id"] == result.export_id
    assert info["pending_changes"] == "nein"


def test_export_kopfzeilen_und_infospalten(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    result = _export(session, workspace, profile, owner)
    assert _header(result.data) == [
        "file_id",
        "@modifyDate",
        "@std:fileName",
        "std:subject",
        "std:keywords",
        "custom:4711",
    ]
    sheet = _sheet(result.data, xlsx.DATA_SHEET)
    assert sheet.cell(row=2, column=4).value == "Titel"
    assert sheet.cell(row=3, column=1).value == 1
    assert sheet.cell(row=3, column=5).value == "rot"
    assert sheet.freeze_panes == "B3"
    assert sheet.auto_filter.ref == "A2:F4"


def test_export_mehrfachwerte_mit_semikolon(
    session: Session,
    workspace: Workspace,
    profile: Profile,
    owner: AppUser,
) -> None:
    store_snapshot(
        session,
        workspace,
        _rows({1: {"std:subject": "x", "std:keywords": ["rot", "blau"]}}),
    )
    result = _export(session, workspace, profile, owner)
    sheet = _sheet(result.data, xlsx.DATA_SHEET)
    assert sheet.cell(row=3, column=5).value == "rot; blau"


def test_export_schreibt_formeln_als_text(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    store_snapshot(session, workspace, _rows({1: {"std:subject": "=1+1", "std:keywords": []}}))
    result = _export(session, workspace, profile, owner)
    sheet = _sheet(result.data, xlsx.DATA_SHEET)
    cell = sheet.cell(row=3, column=4)
    assert cell.value == "=1+1"
    assert cell.data_type == "s"


def test_export_kuerzt_lange_texte_und_haelt_sie_im_snapshot(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    lange = "x" * (xlsx.MAX_CELL_CHARS + 50)
    store_snapshot(session, workspace, _rows({1: {"std:subject": lange, "std:keywords": []}}))
    result = _export(session, workspace, profile, owner)
    sheet = _sheet(result.data, xlsx.DATA_SHEET)
    assert len(sheet.cell(row=3, column=4).value) == xlsx.MAX_CELL_CHARS
    snapshot = xlsx.load_snapshot(session, result.export_id)
    assert snapshot is not None
    assert snapshot["truncated"]["1"] == ["std:subject"]
    assert snapshot["files"]["1"]["values"]["std:subject"] == lange
    assert snapshot["files"]["1"]["modifyDate"] == "2026-10-01 10:00:00"


def test_export_setzt_auswahlliste(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    result = _export(session, workspace, profile, owner)
    sheet = _sheet(result.data, xlsx.DATA_SHEET)
    validations = sheet.data_validations.dataValidation
    assert len(validations) == 1
    assert validations[0].formula1 == f"{xlsx.OPTIONS_SHEET}!$A$3:$A$4"
    assert str(validations[0].sqref) == "F3:F4"
    options = _sheet(result.data, xlsx.OPTIONS_SHEET)
    assert [options.cell(row=row, column=1).value for row in (1, 3, 4)] == [
        "custom:4711",
        "A",
        "B",
    ]


def test_export_dateiname_und_auswahl(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    result = _export(session, workspace, profile, owner, file_ids=[2])
    assert result.filename == "excel_Auswahl_20261030-1511.xlsx"
    assert result.row_count == 1
    sheet = _sheet(result.data, xlsx.DATA_SHEET)
    assert sheet.cell(row=3, column=1).value == 2


def test_export_meldet_ungeschriebene_aenderungen(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    from app.workspaces import set_change

    set_change(session, workspace, file_id=1, column=SUBJECT, value="Neu")
    result = _export(session, workspace, profile, owner)
    assert result.pending_changes is True
    info = _info(result.data)
    assert info["pending_changes"] == "ja"
    assert "hinweis" in info
    sheet = _sheet(result.data, xlsx.DATA_SHEET)
    assert sheet.cell(row=3, column=4).value == "Alt 1"


# --- Import ------------------------------------------------------------------


def test_import_uebernimmt_geaenderte_zellen(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", "Neu 1")
    result = _import(session, profile, owner, data)
    assert result.three_way is True
    assert result.changed == 1
    assert result.workspace_id is not None
    changes = changed_changes(session, result.workspace_id)
    assert [(entry.file_id, entry.key, entry.new_value) for entry in changes] == [
        (1, "std:subject", "Neu 1")
    ]
    assert result.row_count == 2


def test_import_ignoriert_unveraenderte_zellen(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _export(session, workspace, profile, owner).data
    result = _import(session, profile, owner, data)
    assert result.changed == 0
    assert result.workspace_id is None


def test_import_erkennt_bereits_erledigte_zellen(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", "Neu 1")
    FakeFiles.store[1]["subject"] = "Neu 1"
    result = _import(session, profile, owner, data)
    assert result.changed == 0


def test_import_erkennt_konflikt(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", "Neu 1")
    FakeFiles.store[1]["subject"] = "Extern"
    result = _import(session, profile, owner, data)
    assert result.changed == 0
    assert any("übersprungen" in issue.message for issue in result.issues)
    assert any("übersprungen" in warning for warning in result.warnings)


def test_import_leert_zellen_mit_leerem_excel_wert(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", None)
    result = _import(session, profile, owner, data)
    assert result.changed == 1
    changes = changed_changes(session, result.workspace_id or 0)
    assert [(entry.file_id, entry.key, entry.new_value) for entry in changes] == [
        (1, "std:subject", None)
    ]


def test_import_ohne_snapshot_ignoriert_leere_zellen(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _export(session, workspace, profile, owner).data
    data = _edit(data, xlsx.INFO_SHEET, "B3", "unbekannt")
    data = _edit(data, xlsx.DATA_SHEET, "D3", None)
    data = _edit(data, xlsx.DATA_SHEET, "D4", "Neu 2")
    result = _import(session, profile, owner, data)
    assert result.three_way is False
    assert [
        (entry.file_id, entry.key) for entry in changed_changes(session, result.workspace_id or 0)
    ] == [(2, "std:subject")]


def test_import_ohne_snapshot_leert_nach_bestaetigung(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _export(session, workspace, profile, owner).data
    data = _edit(data, xlsx.INFO_SHEET, "B3", "unbekannt")
    data = _edit(data, xlsx.DATA_SHEET, "D3", None)
    result = _import(session, profile, owner, data, clear_empty=True)
    assert result.three_way is False
    changes = changed_changes(session, result.workspace_id or 0)
    assert [(entry.file_id, entry.key, entry.new_value) for entry in changes] == [
        (1, "std:subject", None)
    ]


def test_import_ohne_snapshot_meldet_unbekannte_datei(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "A3", 99)
    data = _edit(data, xlsx.DATA_SHEET, "D3", "Neu")
    result = _import(session, profile, owner, data)
    assert any("nicht mehr vorhanden" in issue.message for issue in result.issues)
    assert result.workspace_id is None


def test_import_meldet_unbekannten_schluessel(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(
        _export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D1", "custom:9"
    )
    with pytest.raises(XlsxError, match="Unbekannter Spaltenschlüssel"):
        _import(session, profile, owner, data)


def test_import_meldet_doppelten_schluessel(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(
        _export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "E1", "std:subject"
    )
    with pytest.raises(XlsxError, match="doppelt"):
        _import(session, profile, owner, data)


def test_import_verlangt_file_id_spalte(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "A1", "id")
    with pytest.raises(XlsxError, match="file_id"):
        _import(session, profile, owner, data)


def test_import_prueft_formatversion(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _export(session, workspace, profile, owner).data
    data = _edit(data, xlsx.INFO_SHEET, "B2", "9.0")
    with pytest.raises(XlsxError, match="Version"):
        _import(session, profile, owner, data)


def test_import_prueft_formatkennung(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _export(session, workspace, profile, owner).data
    data = _edit(data, xlsx.INFO_SHEET, "B1", "fremd")
    with pytest.raises(XlsxError, match="Format"):
        _import(session, profile, owner, data)


def test_import_prueft_host(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(
        _export(session, workspace, profile, owner).data, xlsx.INFO_SHEET, "B5", "andere.host"
    )
    with pytest.raises(XlsxError, match="Host"):
        _import(session, profile, owner, data)


def test_import_lehnt_formeln_ab(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(
        _export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", "=SUM(1,2)"
    )
    result = _import(session, profile, owner, data)
    assert result.changed == 0
    assert any("Formeln" in issue.message for issue in result.issues)


def test_import_prueft_zeilenlimit(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _export(session, workspace, profile, owner).data
    with pytest.raises(XlsxError, match="Profillimit"):
        xlsx.parse_workbook(data, COLUMNS, max_rows=1)


def test_import_lehnt_fremde_datei_ab(profile: Profile, session: Session) -> None:
    with pytest.raises(XlsxError, match="keine Excel-Arbeitsmappe"):
        xlsx.parse_workbook(b"kein zip", COLUMNS)


def test_import_lehnt_makros_ab(profile: Profile, session: Session) -> None:
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/vbaProject.bin", b"makro")
    with pytest.raises(XlsxError, match="Makros"):
        xlsx.parse_workbook(buffer.getvalue(), COLUMNS)


def test_import_meldet_fehlendes_blatt(profile: Profile) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.worksheets[0].title = "Tabelle1"
    buffer = io.BytesIO()
    workbook.save(buffer)
    with pytest.raises(XlsxError, match="Bulk-Editors"):
        xlsx.parse_workbook(buffer.getvalue(), COLUMNS)


def test_import_meldet_unbekannte_auswahl(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "F3", "C")
    result = _import(session, profile, owner, data)
    assert result.changed == 0
    assert any("keine bekannte Auswahl" in issue.message for issue in result.issues)


def test_import_text_bleibt_exakt(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", "  Neu  ")
    result = _import(session, profile, owner, data)
    changes = changed_changes(session, result.workspace_id or 0)
    assert [entry.new_value for entry in changes] == ["  Neu  "]


def test_import_schreibt_metadaten_in_den_bestand(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    result = _import(
        session,
        profile,
        owner,
        _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", "Neu 1"),
    )
    from app.workspaces import import_meta

    created = session.get(Workspace, result.workspace_id)
    assert created is not None
    meta = import_meta(created)
    assert meta is not None
    assert meta["three_way"] is True
    assert meta["filename"] == "probe.xlsx"
    assert created.params_json is not None


def test_import_speichert_spaltenauswahl(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    from app.workspaces import stored_columns

    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "D3", "Neu 1")
    result = _import(session, profile, owner, data)
    created = session.get(Workspace, result.workspace_id)
    assert created is not None
    assert stored_columns(created) == ["std:subject", "std:keywords", "custom:4711"]


def test_import_lauf_hat_quelle_xlsx(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    export = _export(session, workspace, profile, owner)
    data = _edit(export.data, xlsx.DATA_SHEET, "D3", "Neu 1")
    result = _import(session, profile, owner, data)
    created = session.get(Workspace, result.workspace_id)
    assert created is not None
    preview = build_preview(session, created, SCHEMA, None)
    plan = save_plan(session, created, preview, actor=owner, mode=RunMode.DRY_RUN)
    session.flush()
    report = dry_run(session, plan, preview, object(), [SUBJECT], actor=owner)
    run = session.get(Run, report.run_id)
    assert run is not None
    assert run.source is RunSource.XLSX
    assert run.xlsx_export_id == export.export_id


# --- Fehlerdatei -------------------------------------------------------------


def test_fehlerdatei_markiert_zelle_und_listet_befunde(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "F3", "C")
    parsed = xlsx.parse_workbook(data, COLUMNS)
    payload, name = xlsx.build_error_workbook(
        data, issues=parsed.issues, filename="probe.xlsx", moment=MOMENT
    )
    assert name == "probe_fehler_20261030-1511.xlsx"
    report = load_workbook(io.BytesIO(payload))
    sheet = report[xlsx.DATA_SHEET]
    cell = sheet["F3"]
    assert cell.value == "C"
    assert cell.fill.fgColor.rgb.endswith("FCA5A5")
    assert cell.comment is not None
    assert "Auswahl" in cell.comment.text
    fehler = report[ERROR_SHEET]
    assert [fehler.cell(row=1, column=index).value for index in (1, 2, 3)] == [
        "Zeile",
        "Spalte",
        "Meldung",
    ]
    assert fehler.cell(row=2, column=1).value == 3
    assert fehler.cell(row=2, column=2).value == "Kampagne"
    message = str(fehler.cell(row=2, column=3).value)
    assert "Auswahl" in message
    assert fehler.max_row == 2


def test_fehlerdatei_markiert_zeilenfehler_in_spalte_a(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "A3", "abc")
    parsed = xlsx.parse_workbook(data, COLUMNS)
    payload, _name = xlsx.build_error_workbook(data, issues=parsed.issues, filename="probe.xlsx")
    sheet = load_workbook(io.BytesIO(payload))[xlsx.DATA_SHEET]
    assert sheet["A3"].fill.fgColor.rgb.endswith("FCA5A5")
    assert sheet["A3"].comment is not None


def test_fehlerdatei_bleibt_importierbar(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    export = _export(session, workspace, profile, owner)
    broken = _edit(export.data, xlsx.DATA_SHEET, "F3", "C")
    parsed = xlsx.parse_workbook(broken, COLUMNS)
    payload, _name = xlsx.build_error_workbook(broken, issues=parsed.issues, filename="probe.xlsx")
    fixed = _edit(payload, xlsx.DATA_SHEET, "F3", "B")
    result = _import(session, profile, owner, fixed)
    assert result.three_way is True
    assert result.changed == 1
    assert result.issues == []


def test_fehlerdatei_traegt_hinweis_im_info_blatt(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser, client: None
) -> None:
    data = _edit(_export(session, workspace, profile, owner).data, xlsx.DATA_SHEET, "F3", "C")
    parsed = xlsx.parse_workbook(data, COLUMNS)
    payload, _name = xlsx.build_error_workbook(data, issues=parsed.issues, filename="probe.xlsx")
    info = _info(payload)
    assert info["fehler"] == "1"
    assert "markierte Zellen" in info["hinweis"]
    assert info["format"] == xlsx.FORMAT


def test_fehlerdatei_ohne_befunde_bleibt_leer(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    data = _export(session, workspace, profile, owner).data
    payload, _name = xlsx.build_error_workbook(data, issues=[], filename="probe.xlsx")
    report = load_workbook(io.BytesIO(payload))
    assert report[ERROR_SHEET].max_row == 1


# --- Aufbewahrung ------------------------------------------------------------


def test_purge_exports_entfernt_alte_snapshots(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    _export(session, workspace, profile, owner)
    assert session.scalars(select(XlsxExport)).all()
    removed = xlsx.purge_exports(session, days=1, now=MOMENT + timedelta(days=2))
    assert removed == 1
    assert session.scalars(select(XlsxExport)).all() == []


def test_kurzfassung_der_arbeitsmappe(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    parsed = xlsx.parse_workbook(_export(session, workspace, profile, owner).data, COLUMNS)
    lines = xlsx.document_summary(parsed)
    assert any("bulkedit-xlsx" in line for line in lines)
    assert any("2 Datenzeilen" in line for line in lines)
    assert parsed.export_id is not None
