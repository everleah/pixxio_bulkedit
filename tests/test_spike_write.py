"""Tests des Schreibpfads der Phase-1-Pruefungen (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.spike.cli import main
from app.spike.errors import LedgerError, SpikeError, WriteNotAllowedError
from app.spike.fixtures import PNG_SIGNATURE, png_bytes, probe_file_name, write_test_png
from app.spike.guard import assert_deletion_allowed, assert_write_allowed
from app.spike.ledger import Ledger, LedgerEntry
from app.spike.probe import build_metadata_entries, matches, select_probe_fields

CUSTOM_FIELDS = [
    {"id": 1, "name": "Web Text", "editType": "text", "selectionOptions": None},
    {
        "id": 2,
        "name": "Land",
        "editType": "selection",
        "selectionOptions": [{"id": 21, "name": "Deutschland"}],
    },
    {
        "id": 3,
        "name": "Produktbereich",
        "editType": "multiselection",
        "selectionOptions": [{"id": 31, "name": "Kabel"}, {"id": 32, "name": "Dichtung"}],
    },
]
STANDARD_FIELDS = [
    {"id": 9, "name": "Width", "editType": "number", "selectionOptions": None},
]


def _entry(asset_id: int = 1) -> LedgerEntry:
    return LedgerEntry(asset_id=asset_id, file_name=f"probe-{asset_id}.png", created_at="now")


def test_ledger_ohne_datei_ist_leer(tmp_path: Path) -> None:
    assert Ledger(tmp_path / "ledger.json").load() == []


def test_ledger_speichert_und_entfernt(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "spike" / "ledger.json")
    ledger.add(_entry(5))
    ledger.add(_entry(6))
    assert ledger.ids() == {5, 6}

    ledger.add(_entry(5))
    assert ledger.ids() == {5, 6}

    ledger.remove(5)
    assert ledger.ids() == {6}
    assert json.loads(ledger.path.read_text(encoding="utf-8"))["version"] == 1
    assert not ledger.path.with_suffix(".json.tmp").exists()


def test_kaputtes_ledger_wird_nicht_zurueckgesetzt(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text("{kein json", encoding="utf-8")
    with pytest.raises(LedgerError):
        Ledger(path).load()


def test_ledger_mit_fremder_version_wird_abgelehnt(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text('{"version": 99, "assets": []}', encoding="utf-8")
    with pytest.raises(LedgerError):
        Ledger(path).load()


def test_ledger_mit_ungueltigem_eintrag_wird_abgelehnt(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text('{"version": 1, "assets": [{"file_name": "x"}]}', encoding="utf-8")
    with pytest.raises(LedgerError):
        Ledger(path).load()


def test_schreibschutz_verlangt_testsystem() -> None:
    with pytest.raises(WriteNotAllowedError, match="PXTEST_IS_DEV"):
        assert_write_allowed(is_dev=False, ledger_ids={1}, collection_ids={1}, targets=[1])


def test_schreibschutz_verlangt_ziel_ids() -> None:
    with pytest.raises(WriteNotAllowedError, match="keine Ziel-IDs"):
        assert_write_allowed(is_dev=True, ledger_ids={1}, collection_ids={1}, targets=[])


def test_schreibschutz_sperrt_fremde_assets() -> None:
    with pytest.raises(WriteNotAllowedError, match="nicht im Ledger"):
        assert_write_allowed(is_dev=True, ledger_ids={1}, collection_ids={1, 2}, targets=[2])


def test_schreibschutz_sperrt_assets_ausserhalb_der_collection() -> None:
    with pytest.raises(WriteNotAllowedError, match="nicht in der freigegebenen Collection"):
        assert_write_allowed(is_dev=True, ledger_ids={1, 2}, collection_ids={1}, targets=[2])


def test_schreibschutz_erlaubt_ledger_assets_der_collection() -> None:
    assert_write_allowed(is_dev=True, ledger_ids={1, 2}, collection_ids={1, 2}, targets=[1, 2])


def test_loeschschutz_verlangt_ledger_aber_keine_collection_mitgliedschaft() -> None:
    assert_deletion_allowed(is_dev=True, ledger_ids={1, 2}, targets=[1, 2])
    with pytest.raises(WriteNotAllowedError, match="PXTEST_IS_DEV"):
        assert_deletion_allowed(is_dev=False, ledger_ids={1}, targets=[1])
    with pytest.raises(WriteNotAllowedError, match="nicht im Ledger"):
        assert_deletion_allowed(is_dev=True, ledger_ids={1}, targets=[2])


def test_png_ist_gueltig_und_unterscheidet_sich_nach_seed() -> None:
    first = png_bytes(size=8, seed=0)
    second = png_bytes(size=8, seed=1)
    assert first.startswith(PNG_SIGNATURE)
    assert first != second
    assert b"IHDR" in first
    assert b"IEND" in first


def test_write_test_png_schreibt_datei(tmp_path: Path) -> None:
    path = write_test_png(tmp_path / "probe.png", size=8)
    assert path.read_bytes().startswith(PNG_SIGNATURE)


def test_dateinamen_sind_eindeutig_und_png() -> None:
    names = {probe_file_name() for _ in range(20)}
    assert len(names) == 20
    assert all(name.endswith(".png") for name in names)


def test_select_probe_fields_waehlt_vertreter() -> None:
    chosen = select_probe_fields(CUSTOM_FIELDS)
    assert chosen.text_id == 1
    assert chosen.selection_name == "Land"
    assert chosen.selection_option == "Deutschland"
    assert chosen.multiselection_options == ("Kabel", "Dichtung")


def test_select_probe_fields_meldet_fehlende_felder() -> None:
    with pytest.raises(SpikeError, match="Mehrfachauswahl"):
        select_probe_fields(CUSTOM_FIELDS[:2])


def test_metadata_eintraege_nutzen_client_builder() -> None:
    text_entries = build_metadata_entries(CUSTOM_FIELDS, [("replace", 1, "hallo")])
    assert text_entries == [{"action": "replace", "id": 1, "value": "hallo"}]

    selection_entries = build_metadata_entries(CUSTOM_FIELDS, [("replace", 2, "Deutschland")])
    assert selection_entries == [{"action": "replace", "id": 2, "value": 21}]

    multi_entries = build_metadata_entries(CUSTOM_FIELDS, [("replace", 3, ["Kabel", "Dichtung"])])
    assert multi_entries == [{"action": "replace", "id": 3, "value": [31, 32]}]

    remove_entries = build_metadata_entries(CUSTOM_FIELDS, [("remove", 1, None)])
    assert remove_entries == [{"action": "remove", "id": 1}]


def test_matches_ist_tolerant() -> None:
    assert matches("2026-10-30 12:34:56", "2026-10-30")
    assert matches(["Kabel", "Dichtung"], "Kabel")
    assert not matches(None, "Kabel")
    assert not matches("", "Kabel")


@pytest.fixture
def spike_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("PXTEST_HOST", "demo.px.media")
    monkeypatch.setenv("PXTEST_API_KEY", "test-key")
    monkeypatch.setenv("PXTEST_COLLECTION_ID", "614405567")
    monkeypatch.setenv("PXTEST_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PXTEST_IS_DEV", raising=False)
    return tmp_path


def test_fixtures_create_ohne_dev_flag_verweigert(
    spike_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["fixtures", "create", "--count", "1"]) == 1
    assert "PXTEST_IS_DEV" in capsys.readouterr().err
    assert not (spike_env / "ledger.json").exists()


def test_probe_ohne_ledger_bricht_ab(spike_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["probe"]) == 1
    assert "Ledger ist leer" in capsys.readouterr().err


def test_status_zeigt_leeres_ledger(spike_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status"]) == 0
    assert "Eigene Test-Assets: 0" in capsys.readouterr().out


def test_status_zeigt_eintraege(spike_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    Ledger(spike_env / "ledger.json").add(_entry(4711))
    assert main(["status"]) == 0
    assert "4711" in capsys.readouterr().out
