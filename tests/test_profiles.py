"""Tests der Profilverwaltung und der ClientFactory (offline)."""

from __future__ import annotations

from typing import Any, cast

import pytest
from pixxio_client import Client
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import ClientFactory, current_user_name, response_mapping
from app.crypto import SecretBox
from app.models import AdminAudit, AppUser, Profile, Role
from app.profiles import (
    InvalidHostError,
    ProfileData,
    ProfileError,
    ProfileNameTakenError,
    create_profile,
    normalize_host,
    record_connection_check,
    update_profile,
)

API_KEY = "geheimer-test-key-123456"


@pytest.fixture
def actor(session: Session) -> AppUser:
    user = AppUser(username="admin", password_hash="x", role=Role.SUPERUSER)
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def box(master_key: str) -> SecretBox:
    return SecretBox(master_key)


def _data(**overrides: Any) -> ProfileData:
    values: dict[str, Any] = {
        "name": "Testsystem",
        "host": "demo.px.media",
        "api_key": API_KEY,
    }
    values.update(overrides)
    return ProfileData(**values)


def test_host_wird_normalisiert() -> None:
    assert normalize_host("  Demo.PX.Media/ ") == "demo.px.media"


def test_host_mit_protokoll_wird_abgelehnt() -> None:
    with pytest.raises(InvalidHostError, match="ohne Protokoll"):
        normalize_host("https://demo.px.media")
    with pytest.raises(InvalidHostError):
        normalize_host("   ")


def test_profil_verschluesselt_den_key(session: Session, box: SecretBox, actor: AppUser) -> None:
    profile = create_profile(session, box, _data(), actor=actor)

    assert profile.name == "Testsystem"
    assert profile.host == "demo.px.media"
    assert profile.api_key_enc != API_KEY.encode()
    assert box.decrypt(profile.api_key_enc) == API_KEY
    assert profile.api_key_hint.endswith("3456")
    assert profile.allow_write is True
    assert profile.max_rows == 5_000

    audit = session.scalar(select(AdminAudit).where(AdminAudit.action == "profile.create"))
    assert audit is not None
    assert audit.user_id == actor.id
    assert API_KEY not in (audit.details_json or "")
    assert "api_key" not in (audit.details_json or "")


def test_doppelter_profilname_wird_abgelehnt(
    session: Session, box: SecretBox, actor: AppUser
) -> None:
    create_profile(session, box, _data(), actor=actor)
    with pytest.raises(ProfileNameTakenError):
        create_profile(session, box, _data(), actor=actor)


def test_fehlender_key_wird_abgelehnt(session: Session, box: SecretBox, actor: AppUser) -> None:
    with pytest.raises(ProfileError, match="API-Key"):
        create_profile(session, box, _data(api_key=None), actor=actor)
    with pytest.raises(ProfileError, match="zu kurz"):
        create_profile(session, box, _data(api_key="kurz"), actor=actor)


def test_update_ohne_key_behaelt_den_key(session: Session, box: SecretBox, actor: AppUser) -> None:
    profile = create_profile(session, box, _data(), actor=actor)
    original = profile.api_key_enc

    update_profile(
        session,
        box,
        profile,
        _data(api_key=None, max_rows=1_000, allow_write=False),
        actor=actor,
    )

    assert profile.api_key_enc == original
    assert profile.max_rows == 1_000
    assert profile.allow_write is False
    audit = session.scalar(
        select(AdminAudit)
        .where(AdminAudit.action == "profile.update")
        .order_by(AdminAudit.id.desc())
    )
    assert audit is not None
    assert "max_rows" in (audit.details_json or "")
    assert "api_key" not in (audit.details_json or "")


def test_update_mit_key_ersetzt_ihn(session: Session, box: SecretBox, actor: AppUser) -> None:
    profile = create_profile(session, box, _data(), actor=actor)
    update_profile(session, box, profile, _data(api_key="neuer-key-abcdef"), actor=actor)

    assert box.decrypt(profile.api_key_enc) == "neuer-key-abcdef"
    assert profile.api_key_hint.endswith("cdef")


def test_update_prueft_namen(session: Session, box: SecretBox, actor: AppUser) -> None:
    create_profile(session, box, _data(), actor=actor)
    second = create_profile(session, box, _data(name="Zweites"), actor=actor)
    with pytest.raises(ProfileNameTakenError):
        update_profile(session, box, second, _data(name="Testsystem"), actor=actor)


def test_verbindungstest_wird_protokolliert(
    session: Session, box: SecretBox, actor: AppUser
) -> None:
    profile = create_profile(session, box, _data(), actor=actor)
    record_connection_check(session, profile, ok=True, pixxio_user="Claudius", actor=actor)

    assert profile.last_check_ok is True
    assert profile.last_check_user == "Claudius"
    assert profile.last_check_at is not None
    audit = session.scalar(select(AdminAudit).where(AdminAudit.action == "profile.check"))
    assert audit is not None


def test_unbenutztes_profil_wird_geloescht(
    session: Session, box: SecretBox, actor: AppUser
) -> None:
    from app.models import UserProfile
    from app.profiles import delete_profile, profile_usage

    profile = create_profile(session, box, _data(), actor=actor)
    session.add(UserProfile(user_id=actor.id, profile_id=profile.id))
    session.flush()
    profile_id = profile.id
    assert profile_usage(session, profile) == {"workspaces": 0, "runs": 0}

    delete_profile(session, profile, actor=actor)

    assert session.get(Profile, profile_id) is None
    assert session.scalar(select(UserProfile).where(UserProfile.profile_id == profile_id)) is None
    audit = session.scalar(
        select(AdminAudit)
        .where(AdminAudit.action == "profile.delete")
        .order_by(AdminAudit.id.desc())
    )
    assert audit is not None
    assert audit.target == "Testsystem"


def test_benutztes_profil_wird_nicht_geloescht(
    session: Session, box: SecretBox, actor: AppUser
) -> None:
    from app.models import Run
    from app.models.enums import RunKind, RunMode, RunSource, RunStatus
    from app.profiles import delete_profile, profile_usage
    from app.workspaces import create_workspace

    profile = create_profile(session, box, _data(), actor=actor)
    create_workspace(session, owner=actor, profile=profile, name="Bestand")
    assert profile_usage(session, profile)["workspaces"] == 1
    with pytest.raises(ProfileError, match="Arbeitsbestaende|Arbeitsbestände"):
        delete_profile(session, profile, actor=actor)
    assert session.get(Profile, profile.id) is not None

    second = create_profile(session, box, _data(name="Zweites"), actor=actor)
    session.add(
        Run(
            kind=RunKind.QUERY,
            mode=RunMode.DRY_RUN,
            source=RunSource.GRID,
            status=RunStatus.OK,
            profile_id=second.id,
        )
    )
    session.flush()
    assert profile_usage(session, second)["runs"] == 1
    with pytest.raises(ProfileError):
        delete_profile(session, second, actor=actor)


def test_profil_loeschen_braucht_superuser(
    session: Session, box: SecretBox, actor: AppUser
) -> None:
    from app.profiles import delete_profile

    profile = create_profile(session, box, _data(), actor=actor)
    editor = AppUser(username="editor", password_hash="x", role=Role.EDITOR)
    session.add(editor)
    session.flush()
    with pytest.raises(ProfileError, match="Superuser"):
        delete_profile(session, profile, actor=editor)
    assert session.get(Profile, profile.id) is not None


def test_client_factory_cached_und_invalidiert(
    box: SecretBox, session: Session, actor: AppUser
) -> None:
    profile = create_profile(session, box, _data(max_retries=5), actor=actor)
    calls: list[tuple[str, str, int]] = []

    def builder(api_key: str, host: str, max_retries: int) -> Client:
        calls.append((api_key, host, max_retries))
        return cast(Client, object())

    factory = ClientFactory(box, builder=builder)
    first = factory.client_for(profile)
    second = factory.client_for(profile)

    assert first is second
    assert calls == [(API_KEY, "demo.px.media", 5)]
    assert factory.cached_profile_ids() == [profile.id]

    factory.invalidate(profile.id)
    assert factory.cached_profile_ids() == []
    factory.client_for(profile)
    assert len(calls) == 2

    factory.clear()
    assert factory.cached_profile_ids() == []


def test_profil_ohne_id_wird_abgelehnt(box: SecretBox) -> None:
    factory = ClientFactory(box, builder=lambda key, host, retries: cast(Client, object()))
    with pytest.raises(ValueError):
        factory.client_for(Profile(name="x", host="h", api_key_enc=b"x", api_key_hint="x"))


def test_current_user_name_liest_anzeigenamen(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUserApi:
        def __init__(self, client: object) -> None:
            self.client = client

        def get_current(self) -> dict[str, Any]:
            return {"success": True, "user": {"id": 7, "displayName": "Claudius"}}

    monkeypatch.setattr("app.clients.User", FakeUserApi)
    assert current_user_name(cast(Client, object())) == "Claudius"


def test_current_user_name_ohne_namen(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUserApi:
        def __init__(self, client: object) -> None:
            self.client = client

        def get_current(self) -> dict[str, Any]:
            return {"success": True, "user": {}}

    monkeypatch.setattr("app.clients.User", FakeUserApi)
    assert current_user_name(cast(Client, object())) is None


def test_response_mapping_verkraftet_unbekannte_typen() -> None:
    assert response_mapping({"a": 1}) == {"a": 1}
    assert response_mapping(object()) == {}
