"""Tests des Schreiblaufs mit einem Fake-Client (ohne Netzzugriff)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pixxio_client.exceptions import TimeoutException, UnauthorizedException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_user
from app.models import AppUser, ChangeLog, Profile, Run, Workspace, WritePlan
from app.models.enums import (
    ChangeStatus,
    PlanStatus,
    RunKind,
    RunMode,
    RunStatus,
    StepStatus,
)
from app.profiles import ProfileData, create_profile
from app.schema import ColumnDef, MetadataField, ProfileSchema
from app.workspaces import (
    AssetRow,
    changed_count,
    create_workspace,
    set_change,
    snapshot_value,
    store_snapshot,
)
from app.writeplan import build_preview, save_plan
from app.writer import (
    WriteError,
    dry_run,
    execute,
    execution_blockers,
    overlap_warnings,
    read_files,
    reconcile,
    review,
)

SUBJECT = ColumnDef(key="std:subject", label="Titel", source="file_attr", edit_type="text")
CAMPAIGN = ColumnDef(
    key="custom:4711",
    label="Kampagne",
    source="custom",
    edit_type="selection",
    field_id=4711,
    options=("A", "B"),
    option_ids=((11, "A"), (12, "B")),
)


class FakeFiles:
    """Minimaler Ersatz fuer ``pixxio_client.files.File``."""

    store: dict[int, dict[str, Any]] = {}
    script: list[Any] = []
    ignore_writes: bool = False
    job_id: int | None = None

    def __init__(self, client: Any = None) -> None:
        self.client = client

    def iter_all(self, filter: Any = None, page_size: int = 100, max_items: Any = None) -> Any:
        ids = list(filter["fileIDs"]) if filter else list(self.store)
        for file_id in ids:
            item = self.store.get(int(file_id))
            if item is not None:
                yield json.loads(json.dumps(item))

    def update(self, ids: Any = None, filter: Any = None, **payload: Any) -> Any:
        outcome = type(self).script.pop(0) if type(self).script else None
        if isinstance(outcome, BaseException):
            raise outcome
        if not type(self).ignore_writes:
            for file_id in ids:
                _apply(self.store[int(file_id)], payload)
        if outcome is not None:
            return outcome
        if type(self).job_id is not None:
            return {"jobID": type(self).job_id}
        return {"success": True}


class FakeJobs:
    """Ersatz fuer ``pixxio_client.jobs.Job``."""

    reply: dict[str, Any] = {"success": True}

    def __init__(self, client: Any = None) -> None:
        self.client = client

    def wait_for_completion(self, job_id: int, **kwargs: Any) -> Any:
        return dict(type(self).reply)


def _apply(item: dict[str, Any], payload: dict[str, Any]) -> None:
    for field_name, value in payload.items():
        if field_name.startswith("truncate"):
            attribute = field_name[len("truncate") :]
            item[attribute[0].lower() + attribute[1:]] = None
        elif field_name in {"metadataCustom", "metadataStandard"}:
            metadata = item.setdefault("metadataFields", {})
            for entry in value:
                key = str(entry["id"])
                if entry["action"] == "remove":
                    metadata.pop(key, None)
                else:
                    metadata[key] = {"id": entry["id"], "value": entry["value"]}
        elif field_name == "keywordsToAdd":
            item["keywords"] = sorted(set(item.get("keywords") or []) | set(value))
        elif field_name == "keywordsToRemove":
            item["keywords"] = sorted(set(item.get("keywords") or []) - set(value))
        else:
            item[field_name] = value
    item["modifyDate"] = "2026-10-05 12:00:00"


@pytest.fixture(autouse=True)
def _reset_fake() -> Any:
    FakeFiles.store = {
        1: {
            "id": 1,
            "modifyDate": "2026-10-01 10:00:00",
            "subject": "Alt 1",
            "keywords": ["rot"],
            "metadataFields": {"4711": {"id": 4711, "value": "A"}},
        },
        2: {
            "id": 2,
            "modifyDate": "2026-10-01 10:00:00",
            "subject": "Alt 2",
            "keywords": ["rot"],
            "metadataFields": {"4711": {"id": 4711, "value": "A"}},
        },
    }
    FakeFiles.script = []
    FakeFiles.ignore_writes = False
    FakeFiles.job_id = None
    FakeJobs.reply = {"success": True}


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pixxio_client.files.File", FakeFiles)
    monkeypatch.setattr("pixxio_client.jobs.Job", FakeJobs)


@pytest.fixture
def box(master_key: str) -> Any:
    from app.crypto import SecretBox

    return SecretBox(master_key)


@pytest.fixture
def owner(session: Session) -> AppUser:
    return create_user(session, username="schreiber", password="Schreiber-Passwort-2026")


@pytest.fixture
def profile(session: Session, box: Any, owner: AppUser) -> Profile:
    return create_profile(
        session,
        box,
        ProfileData(name="write", host="demo.px.media", api_key="api-key-mit-32-zeichen-laenge"),
        actor=owner,
    )


def _rows() -> list[AssetRow]:
    return [
        AssetRow(
            file_id=index,
            modify_date="2026-10-01 10:00:00",
            values={"std:subject": f"Alt {index}", "custom:4711": "A", "std:keywords": ["rot"]},
        )
        for index in (1, 2)
    ]


@pytest.fixture
def workspace(session: Session, owner: AppUser, profile: Profile) -> Workspace:
    created = create_workspace(session, owner=owner, profile=profile, name="Write")
    store_snapshot(session, created, _rows())
    return created


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
        )
    )


def _plan(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    *,
    value: str = "Neu",
    file_ids: tuple[int, ...] = (1, 2),
) -> tuple[WritePlan, Any]:
    for file_id in file_ids:
        set_change(session, workspace, file_id=file_id, column=SUBJECT, value=value)
    preview = build_preview(session, workspace, schema, None)
    plan = save_plan(session, workspace, preview, actor=owner, mode=RunMode.DRY_RUN)
    session.flush()
    return plan, preview


def test_live_schreibt_verifiziert_und_bucht_ab(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)

    report = execute(session, plan, preview, object(), [SUBJECT], actor=owner)
    session.flush()

    assert report.status is RunStatus.OK
    assert report.committed == 2
    assert plan.status is PlanStatus.COMPLETED
    assert FakeFiles.store[1]["subject"] == "Neu"
    assert FakeFiles.store[2]["subject"] == "Neu"
    assert changed_count(session, workspace.id) == 0
    assert snapshot_value(session, workspace.id, 1, "std:subject") == "Neu"

    logs = session.scalars(select(ChangeLog).where(ChangeLog.run_id == report.run_id)).all()
    assert {log.status for log in logs} == {ChangeStatus.OK}
    run = session.get(Run, report.run_id)
    assert run is not None
    assert run.kind is RunKind.WRITE
    assert run.mode is RunMode.LIVE
    assert run.status is RunStatus.OK


def test_dry_run_schreibt_nicht(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)

    report = dry_run(session, plan, preview, object(), [SUBJECT], actor=owner)
    session.flush()

    assert report.status is RunStatus.OK
    assert FakeFiles.store[1]["subject"] == "Alt 1"
    assert plan.status is PlanStatus.DRAFT
    assert changed_count(session, workspace.id) == 2
    logs = session.scalars(select(ChangeLog).where(ChangeLog.run_id == report.run_id)).all()
    assert {log.status for log in logs} == {ChangeStatus.PLANNED}
    run = session.get(Run, report.run_id)
    assert run is not None
    assert run.mode is RunMode.DRY_RUN


def test_veralteter_plan_wird_abgelehnt(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)
    set_change(session, workspace, file_id=1, column=SUBJECT, value="Anders")

    with pytest.raises(WriteError):
        execute(session, plan, preview, object(), [SUBJECT], actor=owner)


def test_konflikt_ohne_bestaetigung_blockiert(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)
    FakeFiles.store[1]["modifyDate"] = "2026-10-04 09:00:00"
    fresh = review(session, workspace, schema, [SUBJECT], object())

    assert fresh.conflict_files == [1]
    assert execution_blockers(session, plan, fresh, overwrite_confirmed=False)

    report = execute(
        session, plan, fresh, object(), [SUBJECT], actor=owner, overwrite_confirmed=True
    )
    assert report.status is RunStatus.OK
    assert report.late_conflicts == [1]


def test_fehlgeschlagener_job_wird_failed(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)
    FakeFiles.ignore_writes = True
    FakeFiles.job_id = 77
    FakeJobs.reply = {"success": False, "error": "Datei gesperrt"}

    report = execute(session, plan, preview, object(), [SUBJECT], actor=owner)
    session.flush()

    assert report.steps[0].status is StepStatus.FAILED
    assert report.steps[0].job_id == 77
    assert report.steps[0].error == "Datei gesperrt"
    assert report.status is RunStatus.FAILED
    assert plan.status is PlanStatus.FAILED


def test_unklarer_ausgang_ohne_wirkung_wird_unknown(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)
    FakeFiles.script = [TimeoutException(timeout_seconds=30.0)]

    report = execute(session, plan, preview, object(), [SUBJECT], actor=owner)
    session.flush()

    assert report.steps[0].status is StepStatus.UNKNOWN
    assert report.status is RunStatus.FAILED
    logs = session.scalars(select(ChangeLog).where(ChangeLog.run_id == report.run_id)).all()
    assert {log.status for log in logs} == {ChangeStatus.FAILED}


def test_unklarer_ausgang_mit_ruecklesung_ist_ok(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)
    FakeFiles.script = [TimeoutException(timeout_seconds=30.0)]

    class Applied(FakeFiles):
        def update(self, ids: Any = None, filter: Any = None, **payload: Any) -> Any:
            for file_id in ids:
                _apply(super().store[int(file_id)], payload)
            raise TimeoutException(timeout_seconds=30.0)

    import pixxio_client.files

    pixxio_client.files.File = Applied  # type: ignore[misc]

    report = execute(session, plan, preview, object(), [SUBJECT], actor=owner)
    session.flush()

    assert report.steps[0].status is StepStatus.OK
    assert report.steps[0].error is not None
    assert report.status is RunStatus.OK
    assert changed_count(session, workspace.id) == 0


def test_abweichende_ruecklesung_wird_partial(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    plan, preview = _plan(session, workspace, schema, owner)
    FakeFiles.ignore_writes = True

    report = execute(session, plan, preview, object(), [SUBJECT], actor=owner)
    session.flush()

    assert report.steps[0].status is StepStatus.PARTIAL
    assert report.steps[0].error == "Rücklesung weicht bei 2 Feld(ern) ab."
    assert report.status is RunStatus.FAILED
    assert changed_count(session, workspace.id) == 2


def test_systematischer_fehler_pausiert_weitere_schritte(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    set_change(session, workspace, file_id=1, column=SUBJECT, value="Eins")
    set_change(session, workspace, file_id=2, column=SUBJECT, value="Zwei")
    preview = build_preview(session, workspace, schema, None)
    plan = save_plan(session, workspace, preview, actor=owner)
    session.flush()
    FakeFiles.script = [UnauthorizedException("Key ungültig")]

    report = execute(session, plan, preview, object(), [SUBJECT], actor=owner)
    session.flush()

    statuses = [step.status for step in report.steps]
    assert statuses == [StepStatus.FAILED, StepStatus.SKIPPED]
    assert report.paused is True
    logs = session.scalars(select(ChangeLog).where(ChangeLog.run_id == report.run_id)).all()
    assert {log.status for log in logs} == {ChangeStatus.FAILED, ChangeStatus.SKIPPED}


def test_metadaten_und_schlagworte_werden_geschrieben(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    fake_client: None,
) -> None:
    set_change(session, workspace, file_id=1, column=CAMPAIGN, value="B")
    preview = build_preview(session, workspace, schema, None)
    plan = save_plan(session, workspace, preview, actor=owner)
    session.flush()

    report = execute(session, plan, preview, object(), [SUBJECT, CAMPAIGN], actor=owner)
    session.flush()

    assert report.status is RunStatus.OK
    assert FakeFiles.store[1]["metadataFields"]["4711"]["value"] == 12
    assert snapshot_value(session, workspace.id, 1, "custom:4711") == "B"


def test_ueberschneidung_auf_dem_selben_host_wird_gemeldet(
    session: Session,
    workspace: Workspace,
    owner: AppUser,
    profile: Profile,
) -> None:
    other = create_workspace(session, owner=owner, profile=profile, name="Anderer")
    session.add(
        Run(
            kind=RunKind.WRITE,
            mode=RunMode.LIVE,
            status=RunStatus.RUNNING,
            workspace_id=other.id,
            profile_id=profile.id,
        )
    )
    session.flush()

    warnings = overlap_warnings(session, workspace)

    assert len(warnings) == 1
    assert "Schreibauftrag" in warnings[0]


def test_ruecklesung_liest_aktuelle_werte(fake_client: None) -> None:
    values = read_files(object(), [SUBJECT, CAMPAIGN], [1, 2])

    assert values[1]["modifyDate"] == "2026-10-01 10:00:00"
    assert values[1]["values"]["std:subject"] == "Alt 1"
    assert values[1]["values"]["custom:4711"] == "A"
    assert read_files(object(), [SUBJECT], [99]) == {}


def _crashed_run(
    session: Session, plan: Any, workspace: Workspace, profile: Profile
) -> tuple[Run, list[ChangeLog]]:
    """Zustand nach einem Absturz mitten im Lauf."""
    run = Run(
        kind=RunKind.WRITE,
        mode=RunMode.LIVE,
        status=RunStatus.RUNNING,
        workspace_id=workspace.id,
        profile_id=profile.id,
        write_plan_id=plan.id,
    )
    session.add(run)
    session.flush()
    rows = []
    for item in json.loads(plan.plan_json)["changes"]:
        row = ChangeLog(
            run_id=run.id,
            file_id=int(item["file_id"]),
            field_key=str(item["key"]),
            old_value=str(item["old"]),
            new_value=str(item["new"]),
            status=ChangeStatus.PLANNED,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return run, rows


def test_reconcile_erkennt_uebernommene_schritte(
    session: Session,
    workspace: Workspace,
    schema: ProfileSchema,
    owner: AppUser,
    profile: Profile,
    fake_client: None,
) -> None:
    plan, _preview = _plan(session, workspace, schema, owner)
    run, rows = _crashed_run(session, plan, workspace, profile)
    for file_id in (1, 2):
        FakeFiles.store[file_id]["subject"] = "Neu"
    plan.steps[0].status = StepStatus.RUNNING
    session.flush()

    report = reconcile(session, plan, object(), [SUBJECT])

    assert report.steps[0].status is StepStatus.OK
    assert report.status is RunStatus.OK
    assert report.run_id == run.id
    assert plan.status is PlanStatus.COMPLETED
    assert report.committed == 2
    assert changed_count(session, workspace.id) == 0
    assert snapshot_value(session, workspace.id, 1, "std:subject") == "Neu"
    assert run.status is RunStatus.OK
    assert run.finished_at is not None
    assert {row.status for row in rows} == {ChangeStatus.OK}
