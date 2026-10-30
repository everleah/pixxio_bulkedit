"""NiceGUI-Start mit Anmeldung ueber die Anwendungsdatenbank.

Die Fachseiten (Profile, Scripts, Grid, Review) folgen in den naechsten
Meilensteinen. Diese Datei etabliert Start, Migrationslauf, Anmeldung und
Session-Ablauf.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from nicegui import app, ui

from app.auth import (
    AuthenticationError,
    LoginThrottle,
    authenticate,
    normalize_username,
    session_payload,
)
from app.clients import ClientFactory
from app.crypto import SecretBox
from app.db import (
    SessionFactory,
    create_engine_for,
    create_session_factory,
    run_migrations,
    session_scope,
)
from app.models import AppUser, Role
from app.schema import SchemaCache
from app.scripts.runner import ScriptRunner
from app.settings import get_settings
from app.ui.admin import register_admin_pages
from app.ui.guard import current_user, logout
from app.ui.scripts import register_script_pages
from app.ui.shell import apply_palette
from app.ui.workspaces import register_workspace_pages

logger = logging.getLogger(__name__)

APP_TITLE = "pixx.io Bulk-Editor"


def _login_view(
    session_factory: SessionFactory,
    throttle: LoginThrottle,
    timeout: timedelta,
) -> None:
    def submit() -> None:
        key = normalize_username(username.value or "")
        if throttle.is_blocked(key):
            message.set_text("Zu viele Fehlversuche. Bitte spaeter erneut versuchen.")
            return
        with session_scope(session_factory) as session:
            try:
                user = authenticate(session, key, password.value or "")
            except AuthenticationError:
                throttle.register_failure(key)
                message.set_text("Anmeldung fehlgeschlagen.")
                return
            app.storage.user.update(session_payload(user, timeout))
        throttle.register_success(key)
        ui.navigate.reload()

    with ui.card().classes("absolute-center w-80 gap-2"):
        ui.label(APP_TITLE).classes("text-lg font-semibold")
        username = ui.input("Benutzername").props("outlined dense autofocus").classes("w-full")
        password = (
            ui.input("Passwort", password=True, password_toggle_button=True)
            .props("outlined dense")
            .classes("w-full")
        )
        message = ui.label().classes("text-negative text-sm")
        ui.button("Anmelden", on_click=submit).props("unelevated").classes("w-full")
        password.on("keydown.enter", lambda _: submit())


def _home_view(user: AppUser, timeout: timedelta) -> None:
    apply_palette()
    with ui.column().classes("absolute-center items-center gap-2"):
        ui.label(APP_TITLE).classes("text-2xl font-semibold")
        ui.label(f"Angemeldet als {user.username} ({user.role.value})")
        if user.role is Role.SUPERUSER:
            with ui.row().classes("gap-2"):
                ui.button("Arbeitsbestaende", on_click=lambda: ui.navigate.to("/workspaces")).props(
                    "outline dense"
                )
                ui.button("Scripts", on_click=lambda: ui.navigate.to("/scripts")).props(
                    "outline dense"
                )
                ui.button("Profile", on_click=lambda: ui.navigate.to("/admin/profiles")).props(
                    "outline dense"
                )
                ui.button("Benutzer", on_click=lambda: ui.navigate.to("/admin/users")).props(
                    "outline dense"
                )
        else:
            ui.button("Arbeitsbestaende", on_click=lambda: ui.navigate.to("/workspaces")).props(
                "outline dense"
            )
            if user.can_edit_scripts:
                ui.button("Scripts", on_click=lambda: ui.navigate.to("/scripts")).props(
                    "outline dense"
                )
        ui.label("Review und Schreiben folgen in den naechsten Meilensteinen.").classes("text-sm")
        ui.label(f"Sitzung laeuft nach {timeout.total_seconds() // 60:.0f} Minuten ab.").classes(
            "text-xs"
        )
        ui.button("Abmelden", on_click=logout).props("flat")


def main() -> None:
    """Startet die Weboberflaeche; ohne gueltige Konfiguration startet sie nicht."""
    settings = get_settings()
    run_migrations(settings)
    engine = create_engine_for(settings)
    session_factory = create_session_factory(engine)
    secret_box = SecretBox.from_master_key(settings.master_key)
    client_factory = ClientFactory(secret_box)
    schema_cache = SchemaCache(secret_box)
    runner = ScriptRunner(
        timeout_seconds=settings.script_timeout_seconds,
        max_output_chars=settings.script_max_output_chars,
    )
    throttle = LoginThrottle(settings.login_max_attempts, settings.login_window_seconds)
    timeout = timedelta(minutes=settings.session_timeout_minutes)

    @ui.page("/")
    def index() -> None:
        apply_palette()
        user = current_user(session_factory)
        if user is None:
            _login_view(session_factory, throttle, timeout)
        else:
            _home_view(user, timeout)

    register_admin_pages(session_factory, secret_box, client_factory)
    register_script_pages(session_factory, secret_box, runner)
    register_workspace_pages(session_factory, secret_box, schema_cache, client_factory, runner)

    ui.run(
        title=APP_TITLE,
        favicon="\N{HERB}",
        storage_secret=settings.storage_secret.get_secret_value(),
        reload=False,
        show=False,
    )
