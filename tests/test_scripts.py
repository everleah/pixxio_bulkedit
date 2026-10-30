"""Tests des Script-Systems ohne Netzzugriff.

Die Fassade laeuft gegen einen nachgebauten Client; der Kindprozess wird mit Scripts
getestet, die keine API brauchen.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_user
from app.models import AppUser, QueryScript, QueryScriptVersion, Role, Run
from app.models.enums import RunSource
from app.scripts.contract import (
    ScriptResult,
    coerce_params,
    normalize_result,
    parse_columns,
    parse_params,
    validate_filter,
)
from app.scripts.errors import (
    ScriptContractError,
    ScriptError,
    ScriptExecutionError,
    ScriptSecurityError,
)
from app.scripts.facade import Facade, Filters
from app.scripts.restricted import (
    LogCollector,
    check_source,
    read_literals,
)
from app.scripts.restricted import execute as execute_script
from app.scripts.runner import ScriptRunner
from app.scripts.service import (
    ScriptPermissionError,
    create_script,
    delete_script,
    ensure_templates,
    interface_for,
    latest_version,
    publish_version,
    record_run,
    rename_script,
    save_version,
    script_usage,
)
from app.workspaces import create_workspace


class FakeFacade:
    """Minimale Fassade fuer Vertragstests ohne API."""

    max_rows = 10

    def __init__(self, sink: Any = None) -> None:
        self.logs: list[str] = []
        self._sink = sink
        self.filters = Filters()

    def log(self, message: object) -> None:
        self.logs.append(str(message))
        if self._sink is not None:
            self._sink(str(message))


@pytest.fixture
def editor(session: Session) -> AppUser:
    user = create_user(
        session, username="redakteur", password="ein-sehr-langes-passwort", can_edit_scripts=True
    )
    return user


# --- Vertrag ---------------------------------------------------------------


def test_params_werden_geprueft() -> None:
    specs = parse_params(
        {
            "collection": {"type": "str", "label": "Collection", "required": True},
            "limit": {"type": "int", "default": 5},
            "flag": {"type": "bool"},
        }
    )
    assert list(specs) == ["collection", "limit", "flag"]
    assert specs["collection"].title == "Collection"
    assert specs["limit"].default == 5


@pytest.mark.parametrize(
    "raw",
    [
        {"1x": {"type": "str"}},
        {"name": {"type": "unknown"}},
        {"name": {"type": "int", "default": "abc"}},
        {"name": {"type": "str", "extra": 1}},
        {"name": "kein dict"},
        ["keine", "liste"],
    ],
)
def test_ungueltige_params_werden_abgelehnt(raw: object) -> None:
    with pytest.raises(ScriptContractError):
        parse_params(raw)


def test_params_werden_typisiert() -> None:
    specs = parse_params(
        {
            "limit": {"type": "int", "required": True},
            "aktiv": {"type": "bool"},
            "anteil": {"type": "float"},
            "name": {"type": "str"},
        }
    )
    typed = coerce_params(specs, {"limit": "42", "aktiv": "ja", "anteil": "1,5", "name": "Test"})
    assert typed == {"limit": 42, "aktiv": True, "anteil": 1.5, "name": "Test"}


def test_fehlender_pflichtparameter_meldet_sich() -> None:
    specs = parse_params({"collection": {"type": "str", "required": True}})
    with pytest.raises(ScriptContractError, match="erforderlich"):
        coerce_params(specs, {})


def test_unbekannter_parameter_wird_abgelehnt() -> None:
    specs = parse_params({"a": {"type": "str"}})
    with pytest.raises(ScriptContractError, match="Unbekannte Parameter"):
        coerce_params(specs, {"b": "x"})


def test_spalten_werden_geprueft() -> None:
    assert parse_columns(["std:subject", "custom:Kampagne"]) == [
        "std:subject",
        "custom:Kampagne",
    ]
    assert parse_columns(None) is None
    with pytest.raises(ScriptContractError):
        parse_columns(["subject"])


def test_filter_aus_der_feldtabelle_ist_gueltig() -> None:
    filters = Filters()
    validate_filter(filters.collection(123))
    validate_filter(filters.files([1, 2, 3]))
    validate_filter(
        filters.and_(
            filters.collection(123), filters.file_name("katze"), filters.not_(filters.rating(5))
        )
    )


@pytest.mark.parametrize(
    "payload",
    [
        "kein dict",
        {},
        {"filterType": "unbekannt"},
        {"filterType": "collection"},
        {"filterType": "collection", "collectionID": "abc"},
        {"filterType": "files", "fileIDs": []},
        {"filterType": "files", "fileIDs": [1, -2]},
        {"filterType": "collection", "collectionID": 1, "tippfehler": 1},
        {"filterType": "collection", "collectionID": 1, "inverted": "ja"},
        {"filterType": "connectorAnd", "filters": []},
        {"filterType": "connectorAnd", "filters": [{"filterType": "unbekannt"}]},
        {"filterType": "rating"},
        {"filterType": "fileName", "term": "  "},
    ],
)
def test_ungueltige_filter_werden_abgelehnt(payload: object) -> None:
    with pytest.raises(ScriptContractError):
        validate_filter(payload)


def test_ergebnis_liste_wird_entdoppelt_und_begrenzt() -> None:
    result = normalize_result([3, 1, 3, 2], max_rows=5)
    assert result.ids == [3, 1, 2]
    with pytest.raises(ScriptContractError, match="Profillimit"):
        normalize_result([1, 2, 3, 4], max_rows=3)
    with pytest.raises(ScriptContractError):
        normalize_result([], max_rows=3)
    with pytest.raises(ScriptContractError):
        normalize_result("filter", max_rows=3)


def test_ergebnisfilter_wird_geprueft() -> None:
    result = normalize_result({"filterType": "all"}, max_rows=5)
    assert result.filter == {"filterType": "all"}


# --- Sicherheitsschicht ----------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "import os\n",
        "from os import path\n",
        "f = open('x')\n",
        "getattr(1, 'x')\n",
        "eval('1')\n",
        "x = (1).__class__\n",
        "def q(px):\n    return px._client\n",
        "async def q():\n    pass\n",
        "yield 1\n",
    ],
)
def test_verbotene_konstrukte_werden_abgelehnt(source: str) -> None:
    with pytest.raises(ScriptSecurityError):
        check_source(source)


def test_erlaubtes_script_wird_akzeptiert() -> None:
    check_source(
        """
PARAMS = {"limit": {"type": "int", "default": 3}}

def query(px, params):
    ids = px.find_ids(px.filters.all(), params["limit"])
    return [item for item in ids if item > 0]
"""
    )


def test_literale_werden_ohne_ausfuehrung_gelesen() -> None:
    logs = LogCollector()
    source = """
PARAMS = {"term": {"type": "str"}}
COLUMNS = ["std:subject"]
print("darf nicht laufen")
"""
    params, columns = read_literals(source)
    assert params == {"term": {"type": "str"}}
    assert columns == ["std:subject"]
    assert logs.text() == ""


def test_nicht_literale_params_werden_abgelehnt() -> None:
    with pytest.raises(ScriptContractError):
        read_literals("PARAMS = dict(term='x')\n")


def test_execute_sammelt_ausgaben_und_ergebnis() -> None:
    logs = LogCollector()
    facade = FakeFacade(logs.add)
    run = execute_script(
        """
PARAMS = {"term": {"type": "str", "required": True}}

def query(px, params):
    print("suche", params["term"])
    px.log("zweite Zeile")
    return px.filters.file_name(params["term"])
""",
        {"term": "katze"},
        facade,
        log=logs,
    )
    assert run.result.filter == {
        "filterType": "fileName",
        "term": "katze",
        "exactMatch": False,
        "useSynonyms": False,
    }
    assert run.log == "suche katze\nzweite Zeile"


def test_execute_meldet_laufzeitfehler() -> None:
    facade = FakeFacade()
    with pytest.raises(ScriptExecutionError, match="Fehler in query"):
        execute_script("def query(px, params):\n    return 1 / 0\n", {}, facade)


def test_execute_verlangt_query() -> None:
    with pytest.raises(ScriptContractError, match="query"):
        execute_script("PARAMS = {}\n", {}, FakeFacade())


# --- Fassade ---------------------------------------------------------------


def test_fassade_loest_feldnamen_auf(monkeypatch: pytest.MonkeyPatch) -> None:
    facade = Facade(lambda: _FakeClient(), max_rows=100)
    prepared = facade._prepare(facade.filters.metadata_text("Kampagne", "Sommer"))
    assert prepared == {
        "filterType": "metadataFieldText",
        "customMetadataFieldID": 4711,
        "term": "Sommer",
        "exactMatch": False,
        "useSynonyms": False,
    }


def test_fassade_meldet_unbekanntes_feld() -> None:
    facade = Facade(lambda: _FakeClient(), max_rows=100)
    with pytest.raises(ScriptContractError, match="Metadatenfelder"):
        facade._prepare(facade.filters.metadata_text("Unbekannt", "x"))


def test_fassade_zaehlt_und_findet_ids() -> None:
    facade = Facade(lambda: _FakeClient(), max_rows=5)
    assert facade.count(facade.filters.all()) == 42
    assert facade.find_ids(facade.filters.all()) == [101, 102, 103]
    assert facade.find_ids(facade.filters.all(), max_items=2) == [101, 102]


def test_fassade_begrenzt_aufrufe() -> None:
    facade = Facade(lambda: _FakeClient(), max_rows=5, max_calls=2)
    facade.count(facade.filters.all())
    facade.count(facade.filters.all())
    with pytest.raises(ScriptExecutionError, match="API-Aufrufe"):
        facade.count(facade.filters.all())


def test_fassade_result_prueft_alternative() -> None:
    facade = Facade(lambda: _FakeClient(), max_rows=2)
    assert facade.result(ids=[1, 2]).ids == [1, 2]
    with pytest.raises(ScriptContractError, match="entweder filter oder ids"):
        facade.result()
    with pytest.raises(ScriptContractError, match="ueberschreiten"):
        facade.result(ids=[1, 2, 3])


# --- Service ---------------------------------------------------------------


def test_script_anlegen_und_veroeffentlichen(session: Session, editor: AppUser) -> None:
    source = "def query(px, params):\n    return px.filters.all()\n"
    script = create_script(session, name="Alle", source=source, actor=editor)
    assert script.current_version_id is not None
    first = latest_version(session, script)
    assert first is not None and first.version_no == 1

    second = save_version(
        session,
        script,
        source + "\n# Kommentar\n",
        actor=editor,
        comment="kleine Aenderung",
    )
    assert second.version_no == 2
    assert script.current_version_id == first.id

    publish_version(session, script, second, actor=editor)
    assert script.current_version_id == second.id


def test_script_ohne_recht_wird_abgelehnt(session: Session) -> None:
    viewer = create_user(
        session, username="leser", password="ein-sehr-langes-passwort", role=Role.VIEWER
    )
    with pytest.raises(ScriptPermissionError):
        create_script(
            session,
            name="Verboten",
            source="def query(px, params):\n    return [1]\n",
            actor=viewer,
        )


def test_fehlerhaftes_script_wird_nicht_gespeichert(session: Session, editor: AppUser) -> None:
    with pytest.raises(ScriptSecurityError):
        create_script(
            session,
            name="Import",
            source="import os\n\ndef query(px, params):\n    return [1]\n",
            actor=editor,
        )
    assert session.scalar(select(QueryScript).where(QueryScript.name == "Import")) is None


def test_doppelter_scriptname_wird_abgelehnt(session: Session, editor: AppUser) -> None:
    source = "def query(px, params):\n    return [1]\n"
    create_script(session, name="Doppelt", source=source, actor=editor)
    with pytest.raises(ScriptContractError, match="existiert bereits"):
        create_script(session, name="Doppelt", source=source, actor=editor)


def test_script_wird_umbenannt(session: Session, editor: AppUser) -> None:
    source = "def query(px, params):\n    return [1]\n"
    script = create_script(session, name="Collection (Kopie)", source=source, actor=editor)
    version_id = script.current_version_id
    renamed = rename_script(session, script, "  Meine Auswahl  ", actor=editor)
    assert renamed == "Meine Auswahl"
    assert script.name == "Meine Auswahl"
    assert script.current_version_id == version_id
    current = latest_version(session, script)
    assert current is not None and current.version_no == 1  # keine neue Version
    assert rename_script(session, script, "Meine Auswahl", actor=editor) == "Meine Auswahl"


def test_umbenennen_prueft_name_und_rechte(session: Session, editor: AppUser) -> None:
    source = "def query(px, params):\n    return [1]\n"
    first = create_script(session, name="Erstes", source=source, actor=editor)
    create_script(session, name="Zweites", source=source, actor=editor)
    with pytest.raises(ScriptContractError, match="darf nicht leer"):
        rename_script(session, first, "   ", actor=editor)
    with pytest.raises(ScriptContractError, match="existiert bereits"):
        rename_script(session, first, "Zweites", actor=editor)
    viewer = create_user(session, username="leser-rename", password="noch-ein-langes-passwort")
    with pytest.raises(ScriptPermissionError):
        rename_script(session, first, "Verboten", actor=viewer)


def test_vorlage_kann_nicht_umbenannt_werden(session: Session, editor: AppUser) -> None:
    ensure_templates(session, owner=editor)
    template = session.scalar(select(QueryScript).where(QueryScript.is_template.is_(True)))
    assert template is not None
    with pytest.raises(ScriptPermissionError, match="Vorlagen"):
        rename_script(session, template, "Eigene Vorlage", actor=editor)


def test_unbenutztes_script_wird_geloescht(session: Session, editor: AppUser) -> None:
    source = "def query(px, params):\n    return [1]\n"
    script = create_script(session, name="Wegwerf", source=source, actor=editor)
    script_id = script.id
    assert script_usage(session, script) == {"workspaces": 0, "runs": 0}
    delete_script(session, script, actor=editor)
    assert session.get(QueryScript, script_id) is None
    assert (
        session.scalar(select(QueryScriptVersion).where(QueryScriptVersion.script_id == script_id))
        is None
    )


def test_benutztes_script_wird_nicht_geloescht(
    session: Session, editor: AppUser, master_key: str
) -> None:
    from app.crypto import SecretBox
    from app.profiles import ProfileData, create_profile

    source = "def query(px, params):\n    return [1]\n"
    script = create_script(session, name="Im Einsatz", source=source, actor=editor)
    profile = create_profile(
        session,
        SecretBox(master_key),
        ProfileData(
            name="script-test", host="demo.px.media", api_key="api-key-mit-32-zeichen-laenge"
        ),
        actor=editor,
    )
    version = latest_version(session, script)
    assert version is not None
    create_workspace(
        session,
        owner=editor,
        profile=profile,
        name="Bestand",
        script_version=version,
    )
    usage = script_usage(session, script)
    assert usage["workspaces"] == 1
    with pytest.raises(ScriptError, match="noch verwendet"):
        delete_script(session, script, actor=editor)
    assert session.get(QueryScript, script.id) is not None


def test_script_loeschen_prueft_rechte_und_vorlagen(session: Session, editor: AppUser) -> None:
    source = "def query(px, params):\n    return [1]\n"
    script = create_script(session, name="Geschuetzt", source=source, actor=editor)
    viewer = create_user(session, username="leser-delete", password="noch-ein-langes-passwort")
    with pytest.raises(ScriptPermissionError):
        delete_script(session, script, actor=viewer)
    ensure_templates(session, owner=editor)
    template = session.scalar(select(QueryScript).where(QueryScript.is_template.is_(True)))
    assert template is not None
    with pytest.raises(ScriptPermissionError, match="Vorlagen"):
        delete_script(session, template, actor=editor)
    assert session.get(QueryScript, script.id) is not None


def test_vorlagen_werden_angelegt_und_sind_unveraenderlich(
    session: Session, editor: AppUser
) -> None:
    created = ensure_templates(session, owner=editor)
    assert created == 4
    assert ensure_templates(session, owner=editor) == 0
    template = session.scalar(select(QueryScript).where(QueryScript.is_template.is_(True)))
    assert template is not None
    with pytest.raises(ScriptPermissionError, match="Vorlagen"):
        save_version(session, template, "def query(px, params):\n    return [1]\n", actor=editor)


def test_run_wird_protokolliert(session: Session, editor: AppUser) -> None:
    script = create_script(
        session,
        name="Protokoll",
        source="def query(px, params):\n    return [1, 2]\n",
        actor=editor,
    )
    version = latest_version(session, script)
    assert version is not None
    outcome = _outcome_ok([1, 2])
    run = record_run(
        session,
        user=editor,
        profile_id=None,
        script_version_id=version.id,
        source=RunSource.GRID,
        params={"term": "x"},
        outcome=outcome,
    )
    assert run.id is not None
    assert run.script_version_id == version.id
    stored = session.scalar(select(Run).where(Run.id == run.id))
    assert stored is not None
    assert stored.params_json is not None and "term" in stored.params_json


def test_interface_fuer_formular() -> None:
    params, columns = interface_for(
        'PARAMS = {"term": {"type": "str"}}\nCOLUMNS = ["std:subject"]\n\n'
        "def query(px, params):\n    return [1]\n"
    )
    assert list(params) == ["term"]
    assert columns == ["std:subject"]


# --- Kindprozess -----------------------------------------------------------


def test_runner_fuehrt_im_kindprozess_aus() -> None:
    runner = ScriptRunner(timeout_seconds=30)
    outcome = runner.run(
        "PARAMS = {'ids': {'type': 'str'}}\n\n"
        "def query(px, params):\n"
        "    print('hallo')\n"
        "    px.log('world')\n"
        "    return [int(part) for part in params['ids'].split(',')]\n",
        {"ids": "4,5"},
        host="demo.px.media",
        api_key="test-key-1234567890",
        max_rows=10,
    )
    assert outcome.ok, outcome.error
    assert outcome.ids == [4, 5]
    assert "hallo" in outcome.log
    assert "world" in outcome.log


def test_runner_meldet_vertragsfehler() -> None:
    runner = ScriptRunner(timeout_seconds=30)
    with pytest.raises(ScriptContractError, match="erforderlich"):
        runner.run(
            'PARAMS = {"term": {"type": "str", "required": True}}\n\n'
            "def query(px, params):\n    return [1]\n",
            {},
            host="demo.px.media",
            api_key="test-key-1234567890",
            max_rows=10,
        )


def test_runner_bricht_bei_zeitlimit_ab() -> None:
    runner = ScriptRunner(timeout_seconds=3)
    outcome = runner.run(
        "def query(px, params):\n    while True:\n        pass\n",
        {},
        host="demo.px.media",
        api_key="test-key-1234567890",
        max_rows=10,
    )
    assert not outcome.ok
    assert outcome.timed_out
    assert outcome.error is not None and "Zeitlimit" in outcome.error


def test_runner_meldet_skriptfehler_aus_dem_kindprozess() -> None:
    runner = ScriptRunner(timeout_seconds=30)
    outcome = runner.run(
        "def query(px, params):\n    return 1 / 0\n",
        {},
        host="demo.px.media",
        api_key="test-key-1234567890",
        max_rows=10,
    )
    assert not outcome.ok
    assert outcome.error is not None and "ZeroDivisionError" in outcome.error


# --- Hilfen ----------------------------------------------------------------


def _outcome_ok(ids: list[int]) -> Any:
    from app.scripts.runner import ScriptOutcome

    return ScriptOutcome(ok=True, result=ScriptResult(ids=ids), log="", error=None, duration_ms=5)


class _FakeField:
    def __init__(self, field_id: int, name: str, kind: str) -> None:
        self.id = field_id
        self.name = name
        self.editType = "text"
        self.kind = kind

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "editType": self.editType, "kind": self.kind}


class _FakeQuery:
    quantity = 42

    def __init__(self, files: list[Any]) -> None:
        self.files = files


class _FakeFile:
    id = 0

    def __init__(self, file_id: int) -> None:
        self.id = file_id


class _FakeMetadata:
    def __init__(self, client: object) -> None:
        self.client = client

    def set_response_fields(self, _fields: list[str]) -> None:
        return None

    def iter_all(self, **_kwargs: Any) -> Iterator[Any]:
        return iter([])


class _FakeCustomMetadata(_FakeMetadata):
    def iter_all(self, **_kwargs: Any) -> Iterator[Any]:
        return iter([_FakeField(4711, "Kampagne", "custom")])


class _FakeFileResource:
    def __init__(self, client: object) -> None:
        self.client = client

    def set_response_fields(self, _fields: list[str]) -> None:
        return None

    def get(self, **_kwargs: Any) -> _FakeQuery:
        return _FakeQuery([])

    def iter_all(self, **kwargs: Any) -> Iterator[Any]:
        limit = kwargs.get("max_items") or 3
        return iter([_FakeFile(101 + index) for index in range(min(int(limit), 3))])


def _FakeClient() -> Any:  # noqa: N802 - Fabrik im Testcode
    class Client:
        pass

    return Client()


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr("app.scripts.facade.File", _FakeFileResource)
    monkeypatch.setattr("app.scripts.facade.CustomMetadata", _FakeCustomMetadata)
    monkeypatch.setattr("app.scripts.facade.StandardMetadata", _FakeMetadata)
    yield


def test_version_ist_unveraenderlich(session: Session, editor: AppUser) -> None:
    script = create_script(
        session,
        name="Unveraenderlich",
        source="def query(px, params):\n    return [1]\n",
        actor=editor,
    )
    first = latest_version(session, script)
    assert first is not None
    original = first.source
    save_version(session, script, original + "\n", actor=editor)
    assert first.source == original
    versions = list(
        session.scalars(
            select(QueryScriptVersion)
            .where(QueryScriptVersion.script_id == script.id)
            .order_by(QueryScriptVersion.version_no)
        )
    )
    assert [item.version_no for item in versions] == [1, 2]
    assert versions[0].sha256 != versions[1].sha256
