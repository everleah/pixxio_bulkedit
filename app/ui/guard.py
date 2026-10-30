"""Zugriffsschutz fuer Seiten.

Die Pruefung laeuft serverseitig bei jedem Seitenaufbau; ausgeblendete Bedienelemente
sind kein Ersatz dafuer.
"""

from __future__ import annotations

from nicegui import app, ui

from app.auth import session_is_expired
from app.db import SessionFactory, session_scope
from app.models import AppUser, Role


def current_user(session_factory: SessionFactory) -> AppUser | None:
    """Benutzer aus der signierten Session, sofern aktiv und nicht abgelaufen."""
    payload = app.storage.user
    if not payload or session_is_expired(payload):
        return None
    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        return None
    with session_scope(session_factory) as session:
        user = session.get(AppUser, user_id)
        if user is None or not user.is_active:
            return None
        return user


def is_superuser(user: AppUser | None) -> bool:
    return user is not None and user.is_active and user.role is Role.SUPERUSER


def logout() -> None:
    app.storage.user.clear()
    ui.navigate.to("/")


def redirect_to_login() -> None:
    ui.navigate.to("/")
