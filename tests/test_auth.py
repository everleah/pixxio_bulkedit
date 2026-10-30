"""Tests von Anmeldung, Rollen und Benutzerverwaltung."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth import (
    AuthenticationError,
    LastSuperuserError,
    LoginThrottle,
    UsernameTakenError,
    WeakPasswordError,
    authenticate,
    change_password,
    count_active_superusers,
    create_user,
    hash_password,
    normalize_username,
    permissions_for,
    reset_password,
    session_is_expired,
    session_payload,
    set_active,
    set_role,
    validate_password_strength,
    verify_password,
    write_allowed,
)
from app.db import create_session_factory, session_scope
from app.models import AppUser, Profile, Role

PASSWORD = "ein-sehr-langes-passwort"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_passwort_hash_ist_argon2id() -> None:
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("falsches-passwort", hashed)


def test_ungueltiger_hash_verifiziert_nicht() -> None:
    assert not verify_password(PASSWORD, "kein-hash")


def test_zu_kurzes_passwort_wird_abgelehnt() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength("kurz")
    with pytest.raises(WeakPasswordError):
        validate_password_strength(" " * 20)


def test_benutzername_wird_normalisiert() -> None:
    assert normalize_username("  Admin ") == "admin"


def test_create_user_legt_normalisierten_benutzer_an(session: Session) -> None:
    user = create_user(session, username="  Admin ", password=PASSWORD, role=Role.EDITOR)
    assert user.username == "admin"
    assert user.role is Role.EDITOR
    assert user.is_active


def test_doppelter_benutzername_wird_abgelehnt(session: Session) -> None:
    create_user(session, username="admin", password=PASSWORD, role=Role.EDITOR)
    with pytest.raises(UsernameTakenError):
        create_user(session, username="ADMIN", password=PASSWORD)


def test_authenticate_setzt_letzten_login(session: Session) -> None:
    user = create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER)
    assert user.last_login_at is None
    authenticated = authenticate(session, " Admin ", PASSWORD)
    assert authenticated.id == user.id
    assert authenticated.last_login_at is not None


def test_authenticate_lehnt_unbekannten_benutzer_ab(session: Session) -> None:
    with pytest.raises(AuthenticationError):
        authenticate(session, "unbekannt", PASSWORD)


def test_authenticate_lehnt_deaktivierten_benutzer_ab(session: Session) -> None:
    create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER)
    create_user(session, username="gast", password=PASSWORD, role=Role.VIEWER)
    guest = authenticate(session, "gast", PASSWORD)
    set_active(session, guest, False)
    session.flush()
    with pytest.raises(AuthenticationError):
        authenticate(session, "gast", PASSWORD)


def test_falsches_passwort_wird_abgelehnt(session: Session) -> None:
    create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER)
    with pytest.raises(AuthenticationError):
        authenticate(session, "admin", "anderes-langes-passwort")


def test_letzter_superuser_bleibt_geschuetzt(session: Session) -> None:
    admin = create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER)
    assert count_active_superusers(session) == 1
    with pytest.raises(LastSuperuserError):
        set_role(session, admin, Role.EDITOR)
    with pytest.raises(LastSuperuserError):
        set_active(session, admin, False)

    create_user(session, username="zweiter", password=PASSWORD, role=Role.SUPERUSER)
    assert count_active_superusers(session) == 2
    set_role(session, admin, Role.EDITOR)
    assert admin.role is Role.EDITOR


def test_passwortwechsel_verlangt_aktuelles_passwort(session: Session) -> None:
    user = create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER)
    with pytest.raises(AuthenticationError):
        change_password(session, user, "falsch-falsch-falsch", "noch-ein-langes-passwort")
    change_password(session, user, PASSWORD, "noch-ein-langes-passwort")
    assert verify_password("noch-ein-langes-passwort", user.password_hash)


def test_reset_password_prueft_regeln(session: Session) -> None:
    user = create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER)
    with pytest.raises(WeakPasswordError):
        reset_password(session, user, "kurz")


def test_rechte_je_rolle(session: Session) -> None:
    superuser = create_user(session, username="su", password=PASSWORD, role=Role.SUPERUSER)
    editor = create_user(session, username="ed", password=PASSWORD, role=Role.EDITOR)
    viewer = create_user(session, username="vi", password=PASSWORD, role=Role.VIEWER)

    assert permissions_for(superuser).edit_scripts
    assert permissions_for(superuser).manage_users
    assert not permissions_for(editor).edit_scripts
    assert editor.can_edit_scripts is False

    editor.can_edit_scripts = True
    assert permissions_for(editor).edit_scripts
    assert not permissions_for(editor).manage_users
    assert not permissions_for(viewer).write_assets
    assert permissions_for(viewer).export_xlsx
    assert not permissions_for(viewer).import_xlsx


def test_schreiben_verlangt_freigabe_des_profils(session: Session) -> None:
    editor = create_user(session, username="ed", password=PASSWORD, role=Role.EDITOR)
    profile = Profile(
        name="prod",
        host="pixx.io",
        api_key_enc=b"token",
        api_key_hint="abcd",
        allow_write=False,
    )
    assert not write_allowed(editor, profile)
    profile.allow_write = True
    assert write_allowed(editor, profile)


def test_login_drosselung_blockiert_und_gibt_wieder_frei() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_attempts=2, window_seconds=60, clock=clock)
    assert not throttle.is_blocked("admin")
    throttle.register_failure("admin")
    throttle.register_failure("admin")
    assert throttle.is_blocked("admin")
    assert not throttle.is_blocked("anderer")

    clock.advance(61)
    assert not throttle.is_blocked("admin")
    assert throttle.attempt_count("admin") == 0


def test_login_drosselung_vergisst_erfolg() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_attempts=3, window_seconds=60, clock=clock)
    throttle.register_failure("admin")
    throttle.register_success("admin")
    assert throttle.attempt_count("admin") == 0


def test_session_laeuft_ab(session: Session) -> None:
    user = create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER)
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    payload = session_payload(user, timedelta(minutes=30), now=now)
    assert payload["user_id"] == user.id
    assert not session_is_expired(payload, now=now + timedelta(minutes=29))
    assert session_is_expired(payload, now=now + timedelta(minutes=30))
    assert session_is_expired({}, now=now)
    assert session_is_expired({"expires_at": "kein-datum"}, now=now)


def test_benutzer_bleibt_nach_session_ende_lesbar(engine: Engine) -> None:
    """Die Seitenleser nutzen Benutzerdaten nach dem Schliessen der Session."""
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        user_id = create_user(session, username="admin", password=PASSWORD, role=Role.SUPERUSER).id

    with session_scope(factory) as session:
        user = session.get(AppUser, user_id)

    assert user is not None
    assert user.username == "admin"
    assert user.role is Role.SUPERUSER
    assert user.is_active
