"""Tests der Laufuebersicht, Feldhistorie und Undo-Vorbereitung (ohne Netzzugriff)."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.auth import create_user
from app.models import AppUser, ChangeLog, Profile, Run, Workspace
from app.models.base import utc_now
from app.models.enums import (
    ChangeStatus,
    RunKind,
    RunMode,
    RunSource,
    RunStatus,
)
from app.profiles import ProfileData, create_profile
from app.runs import (
    UndoError,
    describe_change,
    list_runs,
    prepare_undo,
    purge_change_values,
    run_changes,
    undoable_changes,
)
from app.schema import ColumnDef, ProfileSchema
from app.workspaces import AssetRow, changed_count, create_workspace, store_snapshot
from app.writeplan import build_preview

SUBJECT = ColumnDef(key="std:subject", label="Titel", source="file_attr", edit_type="text")


class FakeFiles:
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
def _reset_store() -> None:
    FakeFiles.store = {
        1: {
            "id": 1,
            "modifyDate": "2026-10-05 10:00:00",
            "subject": "Neu 1",
            "metadataFields": {},
        },
        2: {
            "id": 2,
            "modifyDate": "2026-10-05 10:00:00",
            "subject": "Neu 2",
            "metadataFields": {},
        },
    }


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pixxio_client.files.File", FakeFiles)


@pytest.fixture
def box(master_key: str) -> Any:
    from app.crypto import SecretBox

    return SecretBox(master_key)


@pytest.fixture
def owner(session: Session) -> AppUser:
    return create_user(session, username="pruefer", password="Pruefer-Passwort-2026")


@pytest.fixture
def profile(session: Session, box: Any, owner: AppUser) -> Profile:
    return create_profile(
        session,
        box,
        ProfileData(name="runs", host="demo.px.media", api_key="api-key-mit-32-zeichen-laenge"),
        actor=owner,
    )


def _run(
    session: Session,
    workspace: Workspace,
    profile: Profile,
    owner: AppUser,
    *,
    mode: RunMode = RunMode.LIVE,
    status: RunStatus = RunStatus.OK,
    started: Any = None,
) -> Run:
    run = Run(
        kind=RunKind.WRITE,
        mode=mode,
        source=RunSource.GRID,
        status=status,
        user_id=owner.id,
        profile_id=profile.id,
        workspace_id=workspace.id,
        started_at=started or utc_now(),
    )
    session.add(run)
    session.flush()
    return run


def _log(
    session: Session,
    run: Run,
    *,
    file_id: int,
    key: str = "std:subject",
    old: Any = "Alt",
    new: Any = "Neu",
    status: ChangeStatus = ChangeStatus.OK,
) -> ChangeLog:
    row = ChangeLog(
        run_id=run.id,
        file_id=file_id,
        field_key=key,
        old_value=None if old is None else json.dumps(old, ensure_ascii=False),
        new_value=None if new is None else json.dumps(new, ensure_ascii=False),
        status=status,
    )
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def workspace(session: Session, owner: AppUser, profile: Profile) -> Workspace:
    created = create_workspace(session, owner=owner, profile=profile, name="Runs")
    store_snapshot(
        session,
        created,
        [
            AssetRow(1, "2026-10-04 10:00:00", {"std:subject": "Neu 1"}),
            AssetRow(2, "2026-10-04 10:00:00", {"std:subject": "Neu 2"}),
        ],
    )
    return created


def test_laufuebersicht_zaehlt_status(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    run = _run(session, workspace, profile, owner)
    _log(session, run, file_id=1)
    _log(session, run, file_id=2, status=ChangeStatus.PLANNED)
    _log(session, run, file_id=2, status=ChangeStatus.UNKNOWN)
    session.add(
        Run(
            kind=RunKind.QUERY,
            mode=RunMode.DRY_RUN,
            status=RunStatus.OK,
            workspace_id=workspace.id,
        )
    )
    session.flush()

    summaries = list_runs(session, limit=10)

    assert len(summaries) == 2
    write_summary = next(item for item in summaries if item.run.id == run.id)
    assert write_summary.ok == 1
    assert write_summary.planned == 1
    assert write_summary.unknown == 1
    assert write_summary.total == 3
    assert write_summary.user_name == "pruefer"
    assert write_summary.profile_name == "runs"
    assert write_summary.workspace_name == "Runs"
    assert len(list_runs(session, limit=10, kind=RunKind.QUERY)) == 1


def test_nur_wirksame_aenderungen_sind_ruecknehmbar(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    run = _run(session, workspace, profile, owner)
    _log(session, run, file_id=1)
    _log(session, run, file_id=2, status=ChangeStatus.UNKNOWN)

    assert [row.status for row in run_changes(session, run.id)] == [
        ChangeStatus.OK,
        ChangeStatus.UNKNOWN,
    ]
    assert [row.file_id for row in undoable_changes(session, run.id)] == [1]


def test_undo_bereitet_neuen_arbeitsbestand_vor(
    session: Session,
    workspace: Workspace,
    profile: Profile,
    owner: AppUser,
    fake_client: None,
) -> None:
    run = _run(session, workspace, profile, owner)
    _log(session, run, file_id=1, old="Alt 1", new="Neu 1")
    _log(session, run, file_id=2, old="Alt 2", new="Neu 2")

    report = prepare_undo(session, run, ProfileSchema(), FakeFiles(), actor=owner)

    assert report.changed == 2
    assert report.skipped_diverged == []
    undo_workspace = session.get(Workspace, report.workspace_id)
    assert undo_workspace is not None
    assert undo_workspace.name == f"Undo zu Lauf {run.id}"
    assert changed_count(session, undo_workspace.id) == 2


def test_undo_ueberspringt_abweichende_und_unwirksame_felder(
    session: Session,
    workspace: Workspace,
    profile: Profile,
    owner: AppUser,
    fake_client: None,
) -> None:
    run = _run(session, workspace, profile, owner, status=RunStatus.PARTIAL)
    _log(session, run, file_id=1, old="Alt 1", new="Neu 1")
    _log(session, run, file_id=2, old="Alt 2", new="Anders")
    _log(session, run, file_id=2, new="Neu 2", status=ChangeStatus.UNKNOWN)
    FakeFiles.store[2]["subject"] = "Extern geaendert"

    report = prepare_undo(session, run, ProfileSchema(), FakeFiles(), actor=owner)

    assert report.changed == 1
    assert report.skipped_diverged == [(2, "std:subject")]
    assert report.skipped_status == [(2, "std:subject")]


def test_undo_ohne_wirksame_felder_wird_abgelehnt(
    session: Session,
    workspace: Workspace,
    profile: Profile,
    owner: AppUser,
    fake_client: None,
) -> None:
    run = _run(session, workspace, profile, owner, status=RunStatus.FAILED)
    _log(session, run, file_id=1, status=ChangeStatus.FAILED)

    with pytest.raises(UndoError) as excinfo:
        prepare_undo(session, run, ProfileSchema(), FakeFiles(), actor=owner)

    assert "Kein Feld" in str(excinfo.value)


def test_undo_meldet_fehlende_dateien(
    session: Session,
    workspace: Workspace,
    profile: Profile,
    owner: AppUser,
    fake_client: None,
) -> None:
    run = _run(session, workspace, profile, owner)
    _log(session, run, file_id=3)

    with pytest.raises(UndoError) as excinfo:
        prepare_undo(session, run, ProfileSchema(), FakeFiles(), actor=owner)

    assert "Dateien fehlen: 3" in str(excinfo.value)


def test_feldwerte_werden_nach_aufbewahrung_entfernt(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    old_run = _run(session, workspace, profile, owner, started=utc_now() - timedelta(days=91))
    fresh_run = _run(session, workspace, profile, owner, started=utc_now() - timedelta(days=10))
    _log(session, old_run, file_id=1)
    _log(session, fresh_run, file_id=2)

    removed = purge_change_values(session)

    assert removed == 1
    old_row = run_changes(session, old_run.id)[0]
    assert old_row.old_value is None
    assert old_row.new_value is None
    assert old_row.field_key == "std:subject"
    assert old_row.status is ChangeStatus.OK
    fresh_row = run_changes(session, fresh_run.id)[0]
    assert fresh_row.new_value == '"Neu"'


def test_anzeigezeile_eines_feldeintrags(
    session: Session, workspace: Workspace, profile: Profile, owner: AppUser
) -> None:
    run = _run(session, workspace, profile, owner)
    row = _log(session, run, file_id=1, old=None, new="Neu", status=ChangeStatus.FAILED)
    row.error = "kaputt"
    session.flush()

    described = describe_change(row)

    assert described["file_id"] == "1"
    assert described["old"] == ""
    assert described["new"] == "Neu"
    assert described["status"] == "failed"
    assert described["error"] == "kaputt"


def test_undo_eines_statuswechsels_verlangt_kommentar(
    session: Session,
    workspace: Workspace,
    profile: Profile,
    owner: AppUser,
    fake_client: None,
) -> None:
    schema = ProfileSchema(file_states=((371896184, "neu"), (1872385346, "gesperrt")))
    FakeFiles.store[1]["fileState"] = {"id": 1872385346}
    run = _run(session, workspace, profile, owner)
    _log(session, run, file_id=1, key="std:fileStateID", old="neu", new="gesperrt")

    report = prepare_undo(session, run, schema, FakeFiles(), actor=owner)

    undo_workspace = session.get(Workspace, report.workspace_id)
    assert undo_workspace is not None
    preview = build_preview(session, undo_workspace, schema, None)
    assert preview.requires_comment is True
    assert preview.errors == ["Ein Statuswechsel verlangt einen Kommentar (fileStateID)."]
    with_comment = build_preview(session, undo_workspace, schema, None, comment="Sperre aufgehoben")
    assert with_comment.errors == []
    assert with_comment.steps[0].payload == {
        "fileStateID": 371896184,
        "fileStateChangeComment": "Sperre aufgehoben",
    }
