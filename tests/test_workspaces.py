"""Tests fuer Schema, Normalisierung und Arbeitsbestaende (ohne Netzzugriff)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.auth import create_user
from app.models import AppUser, Profile, Workspace
from app.models.base import utc_now
from app.models.enums import WorkspaceStatus
from app.normalize import (
    canonical,
    canonical_boolean,
    canonical_date,
    canonical_list,
    canonical_number,
    display_value,
    is_empty,
    values_equal,
)
from app.profiles import ProfileData, create_profile
from app.schema import (
    ColumnDef,
    ProfileSchema,
    SchemaCache,
    build_schema,
    resolve_columns,
)
from app.scripts.contract import ScriptResult
from app.scripts.errors import ScriptContractError
from app.scripts.runner import ScriptOutcome
from app.workspaces import (
    MAX_SELECTED_COLUMNS,
    AssetRow,
    WorkspaceConflictError,
    WorkspaceError,
    bulk_set,
    changed_changes,
    changed_count,
    clear_changes,
    clear_columns,
    close_workspace,
    create_workspace,
    effective_page,
    expiry_warning_days,
    file_values,
    load_assets,
    resolve_targets,
    revert_change,
    set_change,
    snapshot_value,
    store_columns,
    store_snapshot,
    stored_columns,
)

FIELD_TEXT = ColumnDef(
    key="custom:4711", label="Kampagne", source="custom", edit_type="text", field_id=4711
)
FIELD_DATE = ColumnDef(
    key="custom:4712", label="Datum", source="custom", edit_type="date", field_id=4712
)
FIELD_NUMBER = ColumnDef(
    key="custom:4713", label="Anzahl", source="custom", edit_type="number", field_id=4713
)
FIELD_SUBJECT = ColumnDef(
    key="std:subject", label="Titel (Subject)", source="file_attr", edit_type="text"
)


# --- Normalisierung --------------------------------------------------------


def test_texte_bleiben_exakt() -> None:
    assert canonical("text", "  Rand  ") == "  Rand  "
    assert canonical("text", "Zeile\nzwei") == "Zeile\nzwei"


def test_leere_werte_werden_zu_none() -> None:
    for value in (None, "", [], {}):
        assert canonical("text", value) is None
    assert is_empty("") is True
    assert is_empty(" ") is False


def test_datum_wird_normalisiert() -> None:
    assert canonical_date("2026-12-31") == "2026-12-31 00:00:00"
    assert canonical_date("2026-12-31 23:45") == "2026-12-31 23:45:00"
    assert canonical_date("2026-12-31T23:45:12") == "2026-12-31 23:45:12"


@pytest.mark.parametrize("value", ["31.12.2026", "2026-12-31 23:45:00+02:00", "morgen"])
def test_ungueltige_daten_werden_abgelehnt(value: str) -> None:
    with pytest.raises(ScriptContractError):
        canonical_date(value)


def test_zahlen_werden_typisiert() -> None:
    assert canonical_number("42") == 42
    assert canonical_number("1,5") == 1.5
    assert canonical_number(3.0) == 3
    with pytest.raises(ScriptContractError):
        canonical_number("drei")


def test_wahrheitswerte() -> None:
    assert canonical_boolean("ja") is True
    assert canonical_boolean("nein") is False
    with pytest.raises(ScriptContractError):
        canonical_boolean("vielleicht")


def test_mehrfachauswahl_wird_liste() -> None:
    assert canonical_list("b, a") == ["b", "a"]
    assert canonical_list(["a", "a", "b"]) == ["a", "b"]


def test_auswahl_prueft_optionen() -> None:
    assert canonical("selection", "Sommer", options=["Sommer", "Winter"]) == "Sommer"
    with pytest.raises(ScriptContractError):
        canonical("selection", "Herbst", options=["Sommer", "Winter"])


def test_werte_vergleich() -> None:
    assert values_equal(None, "") is True
    assert values_equal(["a", "b"], ["b", "a"]) is True
    assert values_equal(1, 1.0) is True
    assert values_equal("a", "a ") is False


def test_darstellung() -> None:
    assert display_value(None) == ""
    assert display_value(["a", "b"]) == "a, b"
    assert display_value(True) == "ja"


# --- Schema ----------------------------------------------------------------


def _fields() -> list[dict[str, Any]]:
    return [
        {
            "kind": "custom",
            "id": 4711,
            "name": "Kampagne",
            "editType": "text",
            "selectionOptions": [],
        },
        {
            "kind": "custom",
            "id": 4712,
            "name": "Datum",
            "editType": "date",
            "selectionOptions": [],
        },
        {
            "kind": "custom",
            "id": 4714,
            "name": "Auswahl",
            "editType": "selection",
            "selectionOptions": [{"id": 11, "name": "Sommer"}, {"id": 12, "name": "Winter"}],
        },
        {
            "kind": "custom",
            "id": 4715,
            "name": "Struktur",
            "editType": "map",
            "selectionOptions": [],
        },
        {
            "kind": "standard",
            "id": 978216530,
            "name": "DateSent",
            "editType": "date",
            "selectionOptions": [],
        },
    ]


def test_schema_bauen() -> None:
    schema = build_schema(_fields())
    assert [field.name for field in schema.custom] == ["Kampagne", "Datum", "Auswahl", "Struktur"]
    assert [field.name for field in schema.standard] == ["DateSent"]
    keys = [column.key for column in schema.columns()]
    assert "std:subject" in keys
    assert "custom:4711" in keys
    assert "standard:978216530" in keys


def test_spalten_werden_per_id_und_name_aufgeloest() -> None:
    schema = build_schema(_fields())
    columns, unknown = resolve_columns(schema, ["custom:Kampagne", "custom:4712", "std:subject"])
    assert [column.key for column in columns] == ["custom:4711", "custom:4712", "std:subject"]
    assert unknown == []


def test_unbekannte_spalten_werden_gemeldet() -> None:
    schema = build_schema(_fields())
    columns, unknown = resolve_columns(schema, ["custom:Gibt es nicht", "std:unbekannt", "x:1"])
    assert columns == []
    assert unknown == ["custom:Gibt es nicht", "std:unbekannt", "x:1"]


def test_dateistatus_bringt_optionen_mit() -> None:
    schema = build_schema(_fields(), [{"id": 371896184, "name": "neu"}, {"id": 1872385346}])
    column = schema.file_attr_column("fileStateID", "selection")

    assert column.options == ("neu",)
    assert column.option_ids == ((371896184, "neu"),)
    keys = [item.key for item in schema.columns()]
    assert "std:fileStateID" in keys
    resolved, unknown = resolve_columns(schema, ["std:fileStateID"])
    assert unknown == []
    assert resolved[0].option_ids == ((371896184, "neu"),)


def test_dateistatus_wird_aus_file_state_gelesen() -> None:
    payload = {
        "id": 7,
        "fileState": {"id": 1872385346},
        "metadataFields": {},
    }
    column = ColumnDef(
        key="std:fileStateID",
        label="Dateistatus",
        source="file_attr",
        edit_type="selection",
        options=("neu", "gesperrt"),
        option_ids=((371896184, "neu"), (1872385346, "gesperrt")),
    )

    assert file_values(payload, [column]) == {"std:fileStateID": "gesperrt"}
    assert file_values({"id": 8}, [column]) == {"std:fileStateID": None}


def test_optionen_und_schreibbarkeit() -> None:
    schema = build_schema(_fields())
    columns, _ = resolve_columns(schema, ["custom:Auswahl", "custom:Struktur", "std:fileName"])
    assert columns[0].options == ("Sommer", "Winter")
    assert columns[0].option_ids == ((11, "Sommer"), (12, "Winter"))
    assert columns[1].editable is False
    assert columns[1].writable is False
    assert columns[2].writable is False  # Dateiname bleibt unveraenderlich


def test_schema_cache_nutzt_builder_und_ttl(box: Any, session: Session, profile: Profile) -> None:
    calls: list[int] = []

    def builder(loaded: Profile, api_key: str) -> ProfileSchema:
        calls.append(loaded.id or 0)
        return build_schema(_fields())

    cache = SchemaCache(box, ttl_seconds=60, builder=builder)
    first = cache.get(profile)
    second = cache.get(profile)
    assert first is second
    assert calls == [profile.id]
    assert cache.cached_profile_ids() == [profile.id]
    cache.invalidate(profile.id or 0)
    cache.get(profile)
    assert len(calls) == 2


# --- Arbeitsbestaende ------------------------------------------------------


@pytest.fixture
def box(master_key: str) -> Any:
    from app.crypto import SecretBox

    return SecretBox(master_key)


@pytest.fixture
def owner(session: Session) -> AppUser:
    return create_user(session, username="besitzer", password="ein-sehr-langes-passwort")


@pytest.fixture
def profile(session: Session, box: Any, owner: AppUser) -> Profile:
    return create_profile(
        session,
        box,
        ProfileData(name="test", host="demo.px.media", api_key="api-key-mit-32-zeichen-laenge"),
        actor=owner,
    )


def _rows() -> list[AssetRow]:
    return [
        AssetRow(1, "2026-10-01 10:00:00", {"std:subject": "Zebra", "custom:4711": "B"}),
        AssetRow(2, "2026-10-01 10:00:00", {"std:subject": "Antilope", "custom:4711": "A"}),
        AssetRow(3, "2026-10-01 10:00:00", {"std:subject": "Maus", "custom:4711": None}),
    ]


@pytest.fixture
def workspace(session: Session, owner: AppUser, profile: Profile) -> Workspace:
    created = create_workspace(session, owner=owner, profile=profile, name="Test")
    store_snapshot(session, created, _rows())
    return created


def test_arbeitsbestand_anlegen_und_fuellen(workspace: Workspace) -> None:
    assert workspace.status is WorkspaceStatus.READY
    assert workspace.row_count == 3
    assert workspace.edit_revision == 0
    assert workspace.expires_at is not None
    assert workspace.expires_at > utc_now() + timedelta(days=29)


def test_geschlossener_bestand_laesst_sich_wieder_oeffnen(
    session: Session, workspace: Workspace, owner: AppUser
) -> None:
    from app.workspaces import list_workspaces, reopen_workspace

    close_workspace(session, workspace)
    assert workspace.status is WorkspaceStatus.CLOSED
    assert list_workspaces(session, owner.id) == []
    assert [item.id for item in list_workspaces(session, owner.id, include_closed=True)] == [
        workspace.id
    ]
    reopen_workspace(session, workspace)
    assert workspace.status is WorkspaceStatus.READY
    assert [item.id for item in list_workspaces(session, owner.id)] == [workspace.id]


def test_snapshot_wert_lesen(session: Session, workspace: Workspace) -> None:
    assert snapshot_value(session, workspace.id, 1, "std:subject") == "Zebra"
    with pytest.raises(WorkspaceError):
        snapshot_value(session, workspace.id, 99, "std:subject")


# --- Spaltenauswahl --------------------------------------------------------


def test_spaltenauswahl_wird_gespeichert(session: Session, workspace: Workspace) -> None:
    assert stored_columns(workspace) is None
    stored = store_columns(
        session, workspace, ["std:subject", "custom:4711", "std:subject", " ", "7"]
    )
    assert stored == ["std:subject", "custom:4711", "7"]
    assert stored_columns(workspace) == ["std:subject", "custom:4711", "7"]
    clear_columns(session, workspace)
    assert stored_columns(workspace) is None


def test_spaltenauswahl_erhaelt_script_parameter(
    session: Session, owner: AppUser, profile: Profile
) -> None:
    import json

    created = create_workspace(
        session,
        owner=owner,
        profile=profile,
        name="Mit Parametern",
        params={"collection": "chub", "include_archived": False},
    )
    store_columns(session, created, ["std:subject"])
    params = json.loads(created.params_json or "{}")
    assert params["collection"] == "chub"
    assert params["include_archived"] is False
    assert params["@columns"] == ["std:subject"]
    clear_columns(session, created)
    assert json.loads(created.params_json or "{}") == {
        "collection": "chub",
        "include_archived": False,
    }


def test_spaltenauswahl_verlangt_mindestens_eine_spalte(
    session: Session, workspace: Workspace
) -> None:
    with pytest.raises(WorkspaceError, match="mindestens eine Spalte"):
        store_columns(session, workspace, [" ", ""])
    assert stored_columns(workspace) is None


def test_spaltenauswahl_hat_eine_obergrenze(session: Session, workspace: Workspace) -> None:
    keys = [f"custom:{index}" for index in range(MAX_SELECTED_COLUMNS + 1)]
    with pytest.raises(WorkspaceError, match="hoechstens"):
        store_columns(session, workspace, keys)
    assert stored_columns(workspace) is None


def test_ansicht_folgt_der_spaltenauswahl(
    session: Session, workspace: Workspace, profile: Profile
) -> None:
    from app.ui.workspaces import view_columns, workspace_columns

    schema = build_schema(_fields())
    default = workspace_columns(schema, None)
    assert [column.key for column in default][:3] == [
        "std:fileName",
        "std:subject",
        "std:description",
    ]
    assert any(column.source == "standard" for column in schema.columns())
    store_columns(session, workspace, ["std:subject", "standard:978216530", "custom:9999"])
    selected = view_columns(session, workspace, schema)
    assert [column.key for column in selected] == ["std:subject", "standard:978216530"]
    clear_columns(session, workspace)
    assert [column.key for column in view_columns(session, workspace, schema)] == [
        column.key for column in default
    ]


def test_spaltenauswahl_sortiert_innerhalb_der_gruppen() -> None:
    from app.ui.workspaces import COLUMN_GROUPS, column_sort_key, grouped_columns

    schema = build_schema(_fields())
    groups = grouped_columns(schema.columns())
    assert [source for source, _title in COLUMN_GROUPS] == ["file_attr", "custom", "standard"]
    for group in groups.values():
        labels = [column.label for column in group]
        assert labels == sorted(labels, key=str.casefold)
    assert [column.label for column in groups["custom"]][:2] == ["Auswahl", "Datum"]
    umlaut = ColumnDef(key="std:subject", label="Änderung", source="file_attr", edit_type="text")
    plain = ColumnDef(key="std:subject", label="Bild", source="file_attr", edit_type="text")
    assert column_sort_key(umlaut) < column_sort_key(plain)
    assert column_sort_key(umlaut) < column_sort_key(
        ColumnDef(key="std:subject", label="Zebra", source="file_attr", edit_type="text")
    )


def test_aenderung_setzen_und_zuruecknehmen(
    session: Session, workspace: Workspace, owner: AppUser
) -> None:
    changed = set_change(session, workspace, file_id=1, column=FIELD_TEXT, value="Neu", actor=owner)
    assert changed is True
    assert changed_count(session, workspace.id) == 1
    assert workspace.edit_revision == 1
    entries = changed_changes(session, workspace.id)
    assert entries[0].old_value == "B"
    assert entries[0].new_value == "Neu"

    again = set_change(session, workspace, file_id=1, column=FIELD_TEXT, value="B")
    assert again is False
    assert changed_count(session, workspace.id) == 0


def test_unschreibbare_spalte_wird_abgelehnt(session: Session, workspace: Workspace) -> None:
    with pytest.raises(WorkspaceError, match="nicht schreibbar"):
        set_change(
            session,
            workspace,
            file_id=1,
            column=ColumnDef("std:fileName", "Dateiname", "file_attr", "text"),
            value="x",
        )


def test_veraltete_revision_wird_erkannt(session: Session, workspace: Workspace) -> None:
    set_change(session, workspace, file_id=1, column=FIELD_TEXT, value="Neu")
    with pytest.raises(WorkspaceConflictError):
        set_change(
            session,
            workspace,
            file_id=2,
            column=FIELD_TEXT,
            value="Anders",
            expected_revision=0,
        )


def test_mehrfachauswahl_runde(session: Session, workspace: Workspace) -> None:
    column = ColumnDef(
        key="custom:4800", label="Tags", source="custom", edit_type="multiselection", field_id=4800
    )
    set_change(session, workspace, file_id=1, column=column, value=["b", "a"])
    entry = changed_changes(session, workspace.id)[0]
    assert entry.new_value == ["b", "a"]
    assert entry.old_value is None


def test_effektive_seite_sortiert_und_filtert(session: Session, workspace: Workspace) -> None:
    page = effective_page(session, workspace, count=2)
    assert page.total == 3
    assert [row["fileId"] for row in page.rows] == [1, 2]
    assert page.rows[0]["std:subject"] == "Zebra"

    sorted_page = effective_page(session, workspace, sort_column=FIELD_SUBJECT, count=3)
    assert [row["fileId"] for row in sorted_page.rows] == [2, 3, 1]

    descending = effective_page(
        session, workspace, sort_column=FIELD_SUBJECT, descending=True, count=3
    )
    assert [row["fileId"] for row in descending.rows] == [1, 3, 2]


def test_filter_sieht_aenderungen(session: Session, workspace: Workspace) -> None:
    set_change(session, workspace, file_id=3, column=FIELD_TEXT, value="Treffer")
    page = effective_page(
        session, workspace, filter_column=FIELD_TEXT, filter_value="Treffer", count=10
    )
    assert [row["fileId"] for row in page.rows] == [3]
    assert page.total == 1
    assert page.rows[0]["custom:4711"] == "Treffer"


def test_zeilen_zeigen_den_effektiven_wert(session: Session, workspace: Workspace) -> None:
    set_change(session, workspace, file_id=1, column=FIELD_TEXT, value="Neu")
    page = effective_page(session, workspace, count=10)
    row = next(item for item in page.rows if item["fileId"] == 1)
    assert row["custom:4711"] == "Neu"

    # Zeile 3 hat keinen Wert: ein Leeren ist keine Aenderung.
    cleared = set_change(session, workspace, file_id=3, column=FIELD_TEXT, value="")
    assert cleared is False

    set_change(session, workspace, file_id=3, column=FIELD_SUBJECT, value="Geaendert")
    page = effective_page(session, workspace, count=10)
    row = next(item for item in page.rows if item["fileId"] == 3)
    assert row["std:subject"] == "Geaendert"
    assert row["custom:4711"] == ""
    assert row["__changed"] is True


def test_nur_geaenderte_zeilen(session: Session, workspace: Workspace) -> None:
    set_change(session, workspace, file_id=2, column=FIELD_TEXT, value="Neu")
    page = effective_page(session, workspace, only_changed=True, count=10)
    assert [row["fileId"] for row in page.rows] == [2]
    assert page.rows[0]["__changed"] is True


def test_zahlen_spalte_sortiert_numerisch(session: Session, workspace: Workspace) -> None:
    set_change(session, workspace, file_id=1, column=FIELD_NUMBER, value="10")
    set_change(session, workspace, file_id=2, column=FIELD_NUMBER, value="9")
    set_change(session, workspace, file_id=3, column=FIELD_NUMBER, value="11")
    page = effective_page(session, workspace, sort_column=FIELD_NUMBER, count=3)
    assert [row["fileId"] for row in page.rows] == [2, 1, 3]


def test_massenaktion_und_zielauswahl(session: Session, workspace: Workspace) -> None:
    changed = bulk_set(session, workspace, column=FIELD_TEXT, value="Gleich", file_ids=[1, 2, 3])
    assert changed == 3
    targets = resolve_targets(session, workspace, filter_column=FIELD_TEXT, filter_value="Gleich")
    assert sorted(targets) == [1, 2, 3]


def test_aenderungen_verwerfen(session: Session, workspace: Workspace) -> None:
    set_change(session, workspace, file_id=1, column=FIELD_TEXT, value="X")
    set_change(session, workspace, file_id=2, column=FIELD_TEXT, value="Y")
    revert_change(session, workspace, file_id=1, key=FIELD_TEXT.key)
    assert [entry.file_id for entry in changed_changes(session, workspace.id)] == [2]
    removed = clear_changes(session, workspace)
    assert removed == 1
    assert changed_count(session, workspace.id) == 0


def test_ablaufwarnung(workspace: Workspace) -> None:
    assert expiry_warning_days(workspace) is None
    workspace.expires_at = utc_now() + timedelta(days=5)
    assert expiry_warning_days(workspace) == 4


def test_arbeitsbestand_schliessen(session: Session, workspace: Workspace) -> None:
    close_workspace(session, workspace)
    assert workspace.status is WorkspaceStatus.CLOSED


def test_datumsspalte_wird_normalisiert_gespeichert(session: Session, workspace: Workspace) -> None:
    set_change(session, workspace, file_id=1, column=FIELD_DATE, value="2026-05-01")
    entry = changed_changes(session, workspace.id)[0]
    assert entry.new_value == "2026-05-01 00:00:00"


# --- Laden -----------------------------------------------------------------


class _FakeFile:
    def __init__(self, file_id: int, subject: str, campaign: str | None) -> None:
        self.id = file_id
        self.modifyDate = "2026-10-01 10:00:00"
        self.subject = subject
        self.keywords = []
        self.metadataFields = {"4711": {"name": "Kampagne", "value": campaign}}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "modifyDate": self.modifyDate,
            "subject": self.subject,
            "keywords": list(self.keywords),
            "metadataFields": {key: dict(value) for key, value in self.metadataFields.items()},
        }


def _fake_files(monkeypatch: pytest.MonkeyPatch, items: list[_FakeFile]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class FakeFileResource:
        def __init__(self, client: object) -> None:
            self.client = client

        def iter_all(self, **kwargs: Any) -> Iterator[_FakeFile]:
            calls.append(kwargs)
            return iter(items)

    monkeypatch.setattr("pixxio_client.files.File", FakeFileResource)
    return calls


def _outcome(
    filter_obj: dict[str, Any] | None = None, ids: list[int] | None = None
) -> ScriptOutcome:
    return ScriptOutcome(ok=True, result=ScriptResult(filter=filter_obj, ids=ids))


def test_laden_ueber_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_files(monkeypatch, [_FakeFile(1, "Zebra", "B"), _FakeFile(2, "Maus", None)])
    rows = load_assets(
        object(),
        [FIELD_SUBJECT, FIELD_TEXT],
        _outcome(filter_obj={"filterType": "all"}),
        max_rows=10,
    )
    assert [row.file_id for row in rows] == [1, 2]
    assert rows[0].values == {"std:subject": "Zebra", "custom:4711": "B"}
    assert rows[1].values["custom:4711"] is None
    assert calls[0]["filter"] == {"filterType": "all"}


def test_laden_ueber_ids_in_bloecken(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_files(monkeypatch, [_FakeFile(5, "Maus", "A")])
    rows = load_assets(
        object(),
        [FIELD_SUBJECT],
        _outcome(ids=list(range(1, 250))),
        max_rows=500,
    )
    assert len(rows) == 1
    assert calls[0]["filter"] == {"filterType": "files", "fileIDs": list(range(1, 201))}
    assert len(calls) == 2


def test_laden_begrenzt_auf_max_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_files(monkeypatch, [_FakeFile(index, f"F{index}", None) for index in range(1, 6)])
    with pytest.raises(WorkspaceError, match="Profillimit"):
        load_assets(
            object(),
            [FIELD_SUBJECT],
            _outcome(filter_obj={"filterType": "all"}),
            max_rows=3,
        )
