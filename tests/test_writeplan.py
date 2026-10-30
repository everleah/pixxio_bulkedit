"""Tests fuer Schreibplan, Payload-Bildung und Gruppierung (ohne Netzzugriff)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.auth import create_user
from app.models import AppUser, Profile, Workspace, WorkspaceChange
from app.models.enums import PlanStatus, RunMode
from app.profiles import ProfileData, create_profile
from app.schema import ColumnDef, MetadataField, ProfileSchema
from app.workspaces import AssetRow, create_workspace, set_change, store_snapshot
from app.writeplan import (
    CHUNK_SIZE,
    PlanPreview,
    WritePlanError,
    build_preview,
    canonical_payload,
    change_digest,
    current_digest,
    detect_conflicts,
    latest_plan,
    modify_dates,
    payload_digest,
    plan_comment,
    plan_is_current,
    plan_steps,
    preview_summary,
    save_plan,
)

TEXT_COLUMN = ColumnDef(key="std:subject", label="Titel", source="file_attr", edit_type="text")
SELECTION_COLUMN = ColumnDef(
    key="custom:4711",
    label="Kampagne",
    source="custom",
    edit_type="selection",
    field_id=4711,
    options=("A", "B"),
    option_ids=((11, "A"), (12, "B")),
)


@pytest.fixture
def box(master_key: str) -> Any:
    from app.crypto import SecretBox

    return SecretBox(master_key)


@pytest.fixture
def owner(session: Session) -> AppUser:
    return create_user(session, username="planer", password="Planer-Passwort-2026")


@pytest.fixture
def profile(session: Session, box: Any, owner: AppUser) -> Profile:
    return create_profile(
        session,
        box,
        ProfileData(name="plan", host="demo.px.media", api_key="api-key-mit-32-zeichen-laenge"),
        actor=owner,
    )


def _rows(count: int = 2) -> list[AssetRow]:
    return [
        AssetRow(
            file_id=index,
            modify_date="2026-10-01 10:00:00",
            values={"std:subject": f"Alt {index}", "custom:4711": "A", "std:keywords": ["rot"]},
        )
        for index in range(1, count + 1)
    ]


@pytest.fixture
def workspace(session: Session, owner: AppUser, profile: Profile) -> Workspace:
    created = create_workspace(session, owner=owner, profile=profile, name="Plan")
    store_snapshot(session, created, _rows())
    return created


def _raw_change(
    session: Session, workspace: Workspace, *, file_id: int, key: str, value: Any
) -> None:
    """ChangeSet-Eintrag am Service vorbei (wie ihn ein Import schreiben könnte)."""
    session.add(
        WorkspaceChange(
            workspace_id=workspace.id,
            file_id=file_id,
            field_key=key,
            old_value=None,
            new_value=json.dumps(value, ensure_ascii=False),
        )
    )
    session.flush()


@pytest.fixture
def schema() -> ProfileSchema:
    return ProfileSchema(
        custom=(
            MetadataField(
                kind="custom",
                id=4711,
                name="Kampagne",
                edit_type="selection",
                options=("A", "B"),
                option_ids=((11, "A"), (12, "B")),
            ),
            MetadataField(kind="custom", id=4712, name="Datum", edit_type="date"),
            MetadataField(kind="custom", id=4713, name="Anzahl", edit_type="number"),
        )
    )


def test_subject_aenderung_wird_zu_filesput_feld(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Neu")

    preview = build_preview(session, workspace, schema, None)

    assert preview.errors == []
    assert preview.changed_cells == 1
    assert preview.steps[0].ids == (1,)
    assert preview.steps[0].payload == {"subject": "Neu"}


def test_geleertes_feld_wird_abgeschnitten(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="")

    preview = build_preview(session, workspace, schema, None)

    assert preview.steps[0].payload == {"truncateSubject": True}


def test_schlagworte_werden_als_diff_geschrieben(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    column = ColumnDef(
        key="std:keywords", label="Schlagwörter", source="file_attr", edit_type="multiselection"
    )
    set_change(session, workspace, file_id=1, column=column, value=["blau", "grün"])

    preview = build_preview(session, workspace, schema, None)

    payload = preview.steps[0].payload
    assert payload["keywordsToAdd"] == ["blau", "grün"]
    assert payload["keywordsToRemove"] == ["rot"]


def test_metadaten_auswahl_wird_zu_options_id(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=SELECTION_COLUMN, value="B")

    preview = build_preview(session, workspace, schema, None)

    assert preview.steps[0].payload == {
        "metadataCustom": [{"action": "replace", "id": 4711, "value": 12}]
    }


def test_geleerte_metadaten_werden_entfernt(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=SELECTION_COLUMN, value="")

    preview = build_preview(session, workspace, schema, None)

    assert preview.steps[0].payload == {"metadataCustom": [{"action": "remove", "id": 4711}]}


def test_datum_wird_im_api_format_geschrieben(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    column = ColumnDef(
        key="custom:4712", label="Datum", source="custom", edit_type="date", field_id=4712
    )
    set_change(session, workspace, file_id=1, column=column, value="2026-12-31 23:45")

    preview = build_preview(session, workspace, schema, None)

    assert preview.steps[0].payload["metadataCustom"][0]["value"] == "2026-12-31 23:45:00"


def test_gleiche_payloads_werden_gruppiert(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Gleich")
    set_change(session, workspace, file_id=2, column=TEXT_COLUMN, value="Gleich")

    preview = build_preview(session, workspace, schema, None)

    assert len(preview.steps) == 1
    assert preview.steps[0].ids == (1, 2)


def test_gruppen_werden_auf_chunkgroesse_geteilt(
    session: Session, owner: AppUser, profile: Profile, schema: ProfileSchema
) -> None:
    many = create_workspace(session, owner=owner, profile=profile, name="Viele")
    store_snapshot(session, many, _rows(CHUNK_SIZE + 5))
    for file_id in range(1, CHUNK_SIZE + 6):
        set_change(session, many, file_id=file_id, column=TEXT_COLUMN, value="Gleich")

    preview = build_preview(session, many, schema, None)

    assert [len(step.ids) for step in preview.steps] == [CHUNK_SIZE, 5]


def test_unbekannte_spalte_wird_gemeldet(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    column = ColumnDef(
        key="custom:9999", label="Fremd", source="custom", edit_type="text", field_id=9999
    )
    set_change(session, workspace, file_id=1, column=column, value="X")

    preview = build_preview(session, workspace, schema, None)

    assert preview.errors == ["Unbekannte Spalte: custom:9999"]


def test_spalte_ausserhalb_des_arbeitsbestands(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Neu")

    preview = build_preview(session, workspace, schema, ["custom:4711"])

    assert preview.errors == ["Die Spalte std:subject gehört nicht zum Arbeitsbestand."]


def test_dateiname_ist_nicht_schreibbar(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    _raw_change(session, workspace, file_id=1, key="std:fileName", value="neu.jpg")

    preview = build_preview(session, workspace, schema, None)

    assert preview.errors == ["Die Spalte 'Dateiname' ist nicht schreibbar."]


def test_unbekannte_auswahl_wird_abgelehnt(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    _raw_change(session, workspace, file_id=1, key="custom:4711", value="Z")

    preview = build_preview(session, workspace, schema, None)

    assert preview.errors == ["Kampagne: Unbekannte Auswahl für Kampagne: Z"]


def test_ohne_aenderungen_ist_der_plan_leer(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    preview = build_preview(session, workspace, schema, None)

    assert preview.errors == ["Es gibt keine Änderungen."]
    assert preview.steps == []


def test_digest_haengt_am_entwurf(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Eins")
    first = build_preview(session, workspace, schema, None)

    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Zwei")
    second = build_preview(session, workspace, schema, None)

    assert first.digest != second.digest
    assert change_digest([]) == change_digest([])
    assert payload_digest({"a": 1, "b": 2}) == payload_digest({"b": 2, "a": 1})
    assert canonical_payload({"a": 1}) == '{"a":1}'


def test_plan_wird_gespeichert_und_gelesen(
    session: Session, workspace: Workspace, schema: ProfileSchema, owner: AppUser
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Neu")
    preview = build_preview(session, workspace, schema, None)

    plan = save_plan(session, workspace, preview, actor=owner, mode=RunMode.DRY_RUN)
    session.flush()

    assert plan.status is PlanStatus.DRAFT
    assert plan.mode is RunMode.DRY_RUN
    assert plan.step_count == 1
    assert plan_is_current(preview, plan) is True
    assert latest_plan(session, workspace.id) is not None

    steps = plan_steps(session, plan)
    assert len(steps) == 1
    assert json.loads(steps[0].ids_json) == [1]
    stored = json.loads(plan.plan_json)
    assert stored["changes"][0]["new"] == "Neu"


def test_fehlplan_wird_nicht_gespeichert(
    session: Session, workspace: Workspace, owner: AppUser
) -> None:
    preview = PlanPreview(errors=["kaputt"])

    with pytest.raises(WritePlanError):
        save_plan(session, workspace, preview, actor=owner)


def test_dateistatus_wird_als_id_geschrieben(
    session: Session, workspace: Workspace, owner: AppUser
) -> None:
    state_schema = ProfileSchema(file_states=((371896184, "neu"), (1872385346, "gesperrt")))
    column = state_schema.file_attr_column("fileStateID", "selection")
    set_change(session, workspace, file_id=1, column=column, value="gesperrt")

    preview = build_preview(session, workspace, state_schema, None, comment="Freigabe entzogen")

    assert preview.errors == []
    assert preview.requires_comment is True
    assert preview.steps[0].payload == {
        "fileStateID": 1872385346,
        "fileStateChangeComment": "Freigabe entzogen",
    }
    assert plan_comment(save_plan(session, workspace, preview, actor=owner)) == "Freigabe entzogen"


def test_statuswechsel_ohne_kommentar_wird_abgelehnt(
    session: Session, workspace: Workspace
) -> None:
    state_schema = ProfileSchema(file_states=((1872385346, "gesperrt"),))
    column = state_schema.file_attr_column("fileStateID", "selection")
    set_change(session, workspace, file_id=1, column=column, value="gesperrt")

    preview = build_preview(session, workspace, state_schema, None)

    assert preview.requires_comment is True
    assert preview.errors == ["Ein Statuswechsel verlangt einen Kommentar (fileStateID)."]


def test_unbekannter_dateistatus_wird_abgelehnt(session: Session, workspace: Workspace) -> None:
    state_schema = ProfileSchema(file_states=((1872385346, "gesperrt"),))
    column = state_schema.file_attr_column("fileStateID", "selection")
    column = ColumnDef(
        key=column.key,
        label=column.label,
        source=column.source,
        edit_type=column.edit_type,
        options=column.options,
        option_ids=column.option_ids,
    )
    _raw_change(session, workspace, file_id=1, key="std:fileStateID", value="unbekannt")

    preview = build_preview(session, workspace, state_schema, None, comment="Test")

    assert preview.errors == ["Dateistatus: Unbekannter Dateistatus: unbekannt"]


def test_kommentar_gehoert_zum_digest(session: Session, workspace: Workspace) -> None:
    state_schema = ProfileSchema(file_states=((1872385346, "gesperrt"),))
    column = state_schema.file_attr_column("fileStateID", "selection")
    set_change(session, workspace, file_id=1, column=column, value="gesperrt")

    first = build_preview(session, workspace, state_schema, None, comment="Grund A")
    second = build_preview(session, workspace, state_schema, None, comment="Grund B")

    assert first.digest != second.digest
    assert current_digest(session, workspace.id, comment="Grund A") == first.digest


def test_geleerter_dateistatus_wird_abgeschnitten(
    session: Session, owner: AppUser, profile: Profile
) -> None:
    rows = [
        AssetRow(
            file_id=1,
            modify_date="2026-10-01 10:00:00",
            values={"std:subject": "Alt", "std:fileStateID": "gesperrt"},
        )
    ]
    other = create_workspace(session, owner=owner, profile=profile, name="Status")
    store_snapshot(session, other, rows)
    state_schema = ProfileSchema(file_states=((1872385346, "gesperrt"),))
    column = state_schema.file_attr_column("fileStateID", "selection")
    set_change(session, other, file_id=1, column=column, value="")

    preview = build_preview(session, other, state_schema, None, comment="Zurueckgesetzt")

    payload = preview.steps[0].payload
    assert payload["truncateFileState"] is True
    assert payload["fileStateChangeComment"] == "Zurueckgesetzt"


def test_vorschau_kurzfassung(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Neu")
    preview = build_preview(session, workspace, schema, None)

    summary = preview_summary(preview)

    assert summary["changes"] == 1
    assert summary["files"] == 1
    assert summary["steps"] == 1
    assert summary["digest"] == preview.digest


def test_modify_dates_und_konflikte(
    session: Session, workspace: Workspace, schema: ProfileSchema
) -> None:
    set_change(session, workspace, file_id=1, column=TEXT_COLUMN, value="Neu")
    set_change(session, workspace, file_id=2, column=TEXT_COLUMN, value="Neu")
    preview = build_preview(session, workspace, schema, None)

    assert modify_dates(session, workspace.id, [1, 2]) == {
        1: "2026-10-01 10:00:00",
        2: "2026-10-01 10:00:00",
    }
    conflicts = detect_conflicts(
        session,
        workspace,
        preview,
        {1: "2026-10-01 10:00:00", 2: "2026-10-02 08:00:00"},
    )

    assert conflicts == [2]
    assert preview.conflict_files == [2]
    assert preview.warnings == ["Externe Änderungen erkannt: 2"]
