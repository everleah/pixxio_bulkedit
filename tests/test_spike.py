"""Tests der Phase-1-Spikepruefungen (offline)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.spike.cli import main
from app.spike.discovery import (
    as_plain,
    collection_filter,
    file_count,
    summarize_collection,
    summarize_collections,
    summarize_files,
    summarize_schema,
    summarize_user,
)
from app.spike.settings import SpikeSettings


class FakeResponse(SimpleNamespace):
    """Nachbildung der Client-Antwortobjekte mit ``to_dict``."""

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@pytest.fixture(autouse=True)
def _isolated_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verhindert, dass eine lokale .env die Standardwerte der Tests setzt."""
    monkeypatch.chdir(tmp_path)


def _settings(**overrides: Any) -> SpikeSettings:
    values: dict[str, Any] = {
        "host": "demo.px.media",
        "api_key": SecretStr("geheimer-test-key"),
        "collection_id": 4711,
    }
    values.update(overrides)
    return SpikeSettings(**values)


def test_pflichtwerte_fehlen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("PXTEST_HOST", "PXTEST_API_KEY", "PXTEST_COLLECTION_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    settings_class: Any = SpikeSettings
    with pytest.raises(ValidationError) as excinfo:
        settings_class()
    missing = {str(error["loc"][0]) for error in excinfo.value.errors()}
    assert {"host", "api_key", "collection_id"} <= missing


def test_is_dev_ist_standardmaessig_false() -> None:
    assert _settings().is_dev is False


def test_api_key_erscheint_nicht_im_repr() -> None:
    assert "geheimer-test-key" not in repr(_settings())


def test_host_wird_getrimmt() -> None:
    assert _settings(host="  demo.px.media ").host == "demo.px.media"


def test_leerer_host_wird_abgelehnt() -> None:
    with pytest.raises(ValidationError):
        _settings(host="   ")


def test_collection_id_muss_positiv_sein() -> None:
    with pytest.raises(ValidationError):
        _settings(collection_id=0)


def test_collection_filter_form() -> None:
    assert collection_filter(614405567) == {
        "filterType": "collection",
        "collectionID": 614405567,
        "includeArchived": False,
    }
    assert collection_filter(1, include_archived=True)["includeArchived"] is True


def test_summarize_user() -> None:
    response = {"success": True, "user": FakeResponse(id=130052009, displayName="Test User")}
    assert summarize_user(response) == {"id": 130052009, "displayName": "Test User"}


def test_summarize_collection_aus_liste() -> None:
    response = {
        "success": True,
        "collections": [
            FakeResponse(id=614405567, name="chub", isDynamic=True, filesQuantity=4),
        ],
    }
    summary = summarize_collection(response)
    assert summary == {
        "id": 614405567,
        "name": "chub",
        "isDynamic": True,
        "filesQuantity": 4,
    }


def test_summarize_collection_aus_einzelantwort() -> None:
    response = {"success": True, "collection": FakeResponse(id=1, name="einzeln")}
    summary = summarize_collection(response)
    assert summary["id"] == 1
    assert summary["name"] == "einzeln"
    assert summary["isDynamic"] is None


def test_summarize_collections_trennt_dynamisch_und_statisch() -> None:
    response = {
        "success": True,
        "collections": [
            FakeResponse(id=1, name="statisch", isDynamic=False, filesQuantity=4),
            FakeResponse(id=2, name="dynamisch", isDynamic=True, filesQuantity=10),
        ],
    }
    summary = summarize_collections(response)
    assert summary["count"] == 2
    assert summary["dynamic_count"] == 1
    assert summary["collections"][1]["name"] == "dynamisch"


def test_summarize_schema_zaehlt_edit_types_und_optionen() -> None:
    custom = [
        {"id": 1, "name": "Land", "editType": "text", "selectionOptions": None},
        {"id": 2, "name": "Typ", "editType": "multiselection", "selectionOptions": [{"id": 9}]},
    ]
    standard = [
        {"id": 3, "name": "A", "editType": "text"},
        {"id": 4, "name": "B", "editType": "text"},
        {"id": 5, "name": "C", "editType": "number"},
    ]
    summary = summarize_schema(custom, standard)
    assert summary["custom"] == {
        "count": 2,
        "edit_types": {"multiselection": 1, "text": 1},
        "with_selection_options": 1,
    }
    assert summary["standard"] == {"count": 3, "edit_types": {"number": 1, "text": 2}}


def test_summarize_files_trennt_gefuellte_custom_werte() -> None:
    page = {
        "quantity": 2,
        "files": [
            FakeResponse(
                id=418609759,
                fileName="background.bmp",
                modifyDate="2026-10-30 08:12:09",
                subject="background",
                rating=None,
                keywords=[FakeResponse(id=1, name="demo")],
                metadataFields={
                    "100": FakeResponse(type="iptc", name="ExtDescr", value="x"),
                    "200": FakeResponse(type="custom", name="Land", value="DE"),
                    "300": FakeResponse(type="custom", name="Produkttyp", value=None),
                },
            )
        ],
    }
    rows = summarize_files(page)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == 418609759
    assert row["keywords"] == [{"id": 1, "name": "demo"}]
    assert row["customFieldCount"] == 2
    assert row["customFilled"] == {"Land": "DE"}


def test_file_count_akzeptiert_zahl_und_text() -> None:
    assert file_count({"quantity": 4}) == 4
    assert file_count({"quantity": "4"}) == 4
    assert file_count({}) == 0
    assert file_count({"quantity": None}) == 0


def test_as_plain_reduziert_verschachtelte_objekte() -> None:
    value = {"a": [FakeResponse(id=1), {"b": FakeResponse(c=2)}]}
    assert as_plain(value) == {"a": [{"id": 1}, {"b": {"c": 2}}]}


def test_cli_ohne_konfiguration_bricht_ab(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("PXTEST_HOST", "PXTEST_API_KEY", "PXTEST_COLLECTION_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["whoami"]) == 1
    assert "PXTEST_HOST" in capsys.readouterr().err
