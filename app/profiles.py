"""Profile: pixx.io-Zugaenge mit verschluesseltem API-Key.

Der API-Key wird nur verschluesselt gespeichert und ausschliesslich fuer den
Client-Aufbau entschluesselt. Jede Aenderung landet im Admin-Audit ohne Key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import SecretBox, api_key_hint
from app.models import AdminAudit, AppUser, Profile, utc_now

MIN_API_KEY_LENGTH = 8


class ProfileError(Exception):
    """Fachlicher Fehler bei der Profilverwaltung."""


class ProfileNameTakenError(ProfileError):
    pass


class InvalidHostError(ProfileError):
    pass


@dataclass(frozen=True)
class ProfileData:
    """Eingabewerte fuer Anlegen und Aendern; ``api_key=None`` laesst den Key stehen."""

    name: str
    host: str
    api_key: str | None = None
    max_retries: int = 3
    max_rows: int = 5_000
    allow_write: bool = True
    is_active: bool = True


def normalize_host(host: str) -> str:
    cleaned = host.strip().rstrip("/").lower()
    if not cleaned:
        raise InvalidHostError("Host darf nicht leer sein.")
    if "://" in cleaned:
        raise InvalidHostError("Host ohne Protokoll angeben, zum Beispiel 'firmenname.px.media'.")
    return cleaned


def _audit(
    session: Session,
    *,
    actor: AppUser | None,
    action: str,
    target: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AdminAudit(
            user_id=actor.id if actor is not None else None,
            action=action,
            target=target,
            details_json=json.dumps(details, ensure_ascii=False) if details else None,
        )
    )


def _check_name(session: Session, name: str, *, exclude_id: int | None = None) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ProfileError("Der Profilname darf nicht leer sein.")
    statement = select(Profile.id).where(Profile.name == cleaned)
    if exclude_id is not None:
        statement = statement.where(Profile.id != exclude_id)
    if session.scalar(statement) is not None:
        raise ProfileNameTakenError(f"Das Profil {cleaned!r} existiert bereits.")
    return cleaned


def create_profile(
    session: Session,
    secret_box: SecretBox,
    data: ProfileData,
    *,
    actor: AppUser | None,
) -> Profile:
    """Legt ein Profil an und verschluesselt den API-Key."""
    name = _check_name(session, data.name)
    host = normalize_host(data.host)
    api_key = (data.api_key or "").strip()
    if len(api_key) < MIN_API_KEY_LENGTH:
        raise ProfileError("Der API-Key fehlt oder ist zu kurz.")

    profile = Profile(
        name=name,
        host=host,
        api_key_enc=secret_box.encrypt(api_key),
        api_key_hint=api_key_hint(api_key),
        max_retries=data.max_retries,
        max_rows=data.max_rows,
        allow_write=data.allow_write,
        is_active=data.is_active,
        updated_by_id=actor.id if actor is not None else None,
    )
    session.add(profile)
    session.flush()
    _audit(
        session,
        actor=actor,
        action="profile.create",
        target=name,
        details={"host": host, "allow_write": data.allow_write, "max_rows": data.max_rows},
    )
    return profile


def update_profile(
    session: Session,
    secret_box: SecretBox,
    profile: Profile,
    data: ProfileData,
    *,
    actor: AppUser | None,
) -> Profile:
    """Aendert ein Profil; ein leerer API-Key behaelt den bisherigen."""
    changed: list[str] = []
    name = _check_name(session, data.name, exclude_id=profile.id)
    if name != profile.name:
        profile.name = name
        changed.append("name")
    host = normalize_host(data.host)
    if host != profile.host:
        profile.host = host
        changed.append("host")
    if data.max_retries != profile.max_retries:
        profile.max_retries = data.max_retries
        changed.append("max_retries")
    if data.max_rows != profile.max_rows:
        profile.max_rows = data.max_rows
        changed.append("max_rows")
    if data.allow_write != profile.allow_write:
        profile.allow_write = data.allow_write
        changed.append("allow_write")
    if data.is_active != profile.is_active:
        profile.is_active = data.is_active
        changed.append("is_active")

    api_key = (data.api_key or "").strip()
    if api_key:
        if len(api_key) < MIN_API_KEY_LENGTH:
            raise ProfileError("Der API-Key ist zu kurz.")
        profile.api_key_enc = secret_box.encrypt(api_key)
        profile.api_key_hint = api_key_hint(api_key)
        changed.append("api_key")

    profile.updated_by_id = actor.id if actor is not None else None
    profile.updated_at = utc_now()
    _audit(session, actor=actor, action="profile.update", target=name, details={"changed": changed})
    return profile


def record_connection_check(
    session: Session,
    profile: Profile,
    *,
    ok: bool,
    pixxio_user: str | None,
    actor: AppUser | None,
) -> None:
    """Haelt das Ergebnis eines Verbindungstests fest."""
    profile.last_check_at = utc_now()
    profile.last_check_ok = ok
    profile.last_check_user = pixxio_user
    _audit(
        session,
        actor=actor,
        action="profile.check",
        target=profile.name,
        details={"ok": ok, "user": pixxio_user},
    )
