"""Anmeldung, Rollen, Rechte und Benutzerverwaltung."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppUser, Profile, Role, utc_now

MIN_PASSWORD_LENGTH: Final = 12
SESSION_KEYS: Final = ("user_id", "expires_at")

_hasher = PasswordHasher()


class AuthError(Exception):
    """Oberklasse aller fachlichen Anmelde- und Rechtefehler."""


class WeakPasswordError(AuthError):
    pass


class AuthenticationError(AuthError):
    pass


class UsernameTakenError(AuthError):
    pass


class LastSuperuserError(AuthError):
    """Der letzte aktive Superuser darf nicht herabgestuft oder deaktiviert werden."""


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben."
        )
    if not password.strip():
        raise WeakPasswordError("Das Passwort darf nicht nur aus Leerzeichen bestehen.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except InvalidHashError, VerificationError, VerifyMismatchError:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@lru_cache(maxsize=1)
def _timing_dummy_hash() -> str:
    """Hash fuer konstante Antwortzeit bei unbekanntem Benutzernamen."""
    return hash_password("nicht-vergebenes-passwort")


def authenticate(session: Session, username: str, password: str) -> AppUser:
    """Prueft die Zugangsdaten und aktualisiert ``last_login_at``."""
    user = session.scalar(select(AppUser).where(AppUser.username == normalize_username(username)))
    if user is None:
        verify_password(password, _timing_dummy_hash())
        raise AuthenticationError("Anmeldung fehlgeschlagen.")
    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Anmeldung fehlgeschlagen.")
    if not user.is_active:
        raise AuthenticationError("Anmeldung fehlgeschlagen.")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utc_now()
    return user


@dataclass(frozen=True)
class Permissions:
    """Effektive Rechte eines Benutzers."""

    manage_users: bool = False
    manage_profiles: bool = False
    edit_scripts: bool = False
    export_xlsx: bool = False
    import_xlsx: bool = False
    write_assets: bool = False
    run_scripts: bool = True


ROLE_PERMISSIONS: Final[dict[Role, Permissions]] = {
    Role.SUPERUSER: Permissions(
        manage_users=True,
        manage_profiles=True,
        edit_scripts=True,
        export_xlsx=True,
        import_xlsx=True,
        write_assets=True,
    ),
    Role.EDITOR: Permissions(export_xlsx=True, import_xlsx=True, write_assets=True),
    Role.VIEWER: Permissions(export_xlsx=True),
}


def permissions_for(user: AppUser) -> Permissions:
    base = ROLE_PERMISSIONS[user.role]
    if user.role is Role.SUPERUSER or user.can_edit_scripts:
        return replace(base, edit_scripts=True)
    return base


def write_allowed(user: AppUser, profile: Profile) -> bool:
    """Schreiben verlangt Schreibrecht der Rolle und Freigabe des Profils."""
    return user.is_active and profile.allow_write and permissions_for(user).write_assets


class LoginThrottle:
    """Begrenzt Anmeldeversuche je Schluessel innerhalb eines Zeitfensters."""

    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts muss mindestens 1 sein")
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> None:
        timestamps = self._attempts.get(key)
        if timestamps is None:
            return
        cutoff = now - self._window_seconds
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if not timestamps:
            del self._attempts[key]

    def attempt_count(self, key: str) -> int:
        self._prune(key, self._clock())
        return len(self._attempts.get(key, ()))

    def is_blocked(self, key: str) -> bool:
        return self.attempt_count(key) >= self._max_attempts

    def register_failure(self, key: str) -> None:
        now = self._clock()
        self._prune(key, now)
        self._attempts.setdefault(key, deque()).append(now)

    def register_success(self, key: str) -> None:
        self._attempts.pop(key, None)


def session_payload(
    user: AppUser, timeout: timedelta, now: datetime | None = None
) -> dict[str, str | int]:
    """Werte fuer ``app.storage.user``; der API-Key gehoert nie dazu."""
    started = now or utc_now()
    return {"user_id": user.id, "expires_at": (started + timeout).isoformat()}


def session_is_expired(payload: Mapping[str, object], now: datetime | None = None) -> bool:
    expires_at = payload.get("expires_at")
    if not isinstance(expires_at, str):
        return True
    try:
        deadline = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    return deadline <= (now or utc_now())


def count_active_superusers(session: Session, *, exclude_user_id: int | None = None) -> int:
    statement = (
        select(func.count())
        .select_from(AppUser)
        .where(
            AppUser.role == Role.SUPERUSER,
            AppUser.is_active.is_(True),
        )
    )
    if exclude_user_id is not None:
        statement = statement.where(AppUser.id != exclude_user_id)
    return session.scalar(statement) or 0


def _assert_not_last_active_superuser(session: Session, user: AppUser) -> None:
    if user.role is not Role.SUPERUSER or not user.is_active:
        return
    if count_active_superusers(session, exclude_user_id=user.id) == 0:
        raise LastSuperuserError(
            "Der letzte aktive Superuser kann weder herabgestuft noch deaktiviert werden."
        )


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: Role = Role.VIEWER,
    can_edit_scripts: bool = False,
) -> AppUser:
    name = normalize_username(username)
    if not name:
        raise AuthError("Benutzername darf nicht leer sein.")
    validate_password_strength(password)
    if session.scalar(select(AppUser.id).where(AppUser.username == name)) is not None:
        raise UsernameTakenError(f"Der Benutzername {name!r} ist bereits vergeben.")
    user = AppUser(
        username=name,
        password_hash=hash_password(password),
        role=role,
        can_edit_scripts=can_edit_scripts,
    )
    session.add(user)
    session.flush()
    return user


def set_role(session: Session, user: AppUser, role: Role) -> None:
    if user.role is not role:
        _assert_not_last_active_superuser(session, user)
    user.role = role


def set_active(session: Session, user: AppUser, is_active: bool) -> None:
    if user.is_active and not is_active:
        _assert_not_last_active_superuser(session, user)
    user.is_active = is_active


def reset_password(session: Session, user: AppUser, password: str) -> None:
    validate_password_strength(password)
    user.password_hash = hash_password(password)


def change_password(
    session: Session, user: AppUser, current_password: str, new_password: str
) -> None:
    """Passwortwechsel durch den Benutzer selbst."""
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Das aktuelle Passwort ist falsch.")
    reset_password(session, user, new_password)


def assign_profile(session: Session, user: AppUser, profile: Profile) -> None:
    if profile not in user.profiles:
        user.profiles.append(profile)


def unassign_profile(session: Session, user: AppUser, profile: Profile) -> None:
    if profile in user.profiles:
        user.profiles.remove(profile)
