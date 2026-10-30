"""Verwaltung von Profilen und Benutzern (nur Superuser).

Der API-Key ist write-only: die Oberflaeche zeigt nur den Hint und setzt ihn nie
zurueck ins Eingabefeld. Jede Seite prueft die Rolle serverseitig.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from nicegui import run, ui
from pixxio_client.exceptions import PIXXIOException
from sqlalchemy import select

from app.auth import (
    AuthError,
    LastSuperuserError,
    create_user,
    reset_password,
    set_active,
    set_role,
)
from app.clients import ClientFactory, current_user_name
from app.crypto import SecretBox, UndecryptableApiKeyError
from app.db import SessionFactory, session_scope
from app.models import AppUser, Profile, Role
from app.profiles import (
    ProfileData,
    ProfileError,
    create_profile,
    record_connection_check,
    update_profile,
)
from app.ui.guard import current_user, is_superuser, redirect_to_login
from app.ui.shell import apply_palette, page_header

ROLE_LABELS: dict[Role, str] = {
    Role.SUPERUSER: "Superuser",
    Role.EDITOR: "Editor",
    Role.VIEWER: "Viewer",
}
ROW_CLASSES = "w-full items-center gap-3 border-b py-1 text-sm"


def _action_button(icon: str, label: str, handler: Any) -> None:
    button = ui.button(on_click=handler, icon=icon).props("flat round dense color=primary")
    button.tooltip(label)
    button.props(f'aria-label="{label}"')


def _check_label(profile: Profile) -> str:
    if profile.last_check_at is None:
        return "noch nicht geprueft"
    stamp = profile.last_check_at.strftime("%d.%m.%Y %H:%M")
    if profile.last_check_ok:
        return f"OK: {profile.last_check_user or 'unbekannt'} ({stamp})"
    return f"Fehler ({stamp})"


def _authenticated(session_factory: SessionFactory, title: str) -> AppUser | None:
    apply_palette()
    user = current_user(session_factory)
    if user is None:
        redirect_to_login()
        return None
    page_header(title, user)
    if not is_superuser(user):
        ui.label("Kein Zugriff: diese Seite verwaltet nur ein Superuser.").classes(
            "text-negative font-medium"
        )
        return None
    return user


def register_admin_pages(
    session_factory: SessionFactory,
    secret_box: SecretBox,
    client_factory: ClientFactory,
) -> None:
    @ui.page("/admin/profiles")
    def profiles_page() -> None:  # pyright: ignore[reportUnusedFunction]
        user = _authenticated(session_factory, "Profile")
        if user is None:
            return

        editing: dict[str, int | None] = {"id": None}
        status = ui.label("").classes("text-sm")
        list_container = ui.column().classes("w-full gap-1")
        form_container = ui.column().classes("w-full max-w-4xl gap-2")

        with form_container:
            ui.label("Profil anlegen oder bearbeiten").classes("font-semibold mt-4")
            name_input = ui.input("Name").props("outlined dense").classes("w-80")
            host_input = ui.input("Host").props("outlined dense").classes("w-80")
            key_input = (
                ui.input("API-Key", password=True, password_toggle_button=True)
                .props("outlined dense")
                .classes("w-96")
            )
            ui.label("Leer lassen, um den gespeicherten Key zu behalten.").classes("text-xs")
            with ui.row().classes("gap-4"):
                retries_input = ui.number("max_retries", value=3, min=0, max=10).props(
                    "outlined dense"
                )
                rows_input = ui.number("max_rows", value=5_000, min=1, max=50_000).props(
                    "outlined dense"
                )
            with ui.row().classes("gap-4"):
                write_switch = ui.switch("Schreiben erlaubt", value=True)
                active_switch = ui.switch("aktiv", value=True)
            buttons = ui.row().classes("gap-2")

        @ui.refreshable
        def profile_rows() -> None:
            with session_scope(session_factory) as session:
                rows = [
                    {
                        "id": profile.id,
                        "name": profile.name,
                        "host": profile.host,
                        "hint": profile.api_key_hint,
                        "max_rows": profile.max_rows,
                        "allow_write": profile.allow_write,
                        "active": profile.is_active,
                        "check": _check_label(profile),
                    }
                    for profile in session.scalars(select(Profile).order_by(Profile.name))
                ]
            if not rows:
                ui.label("Noch keine Profile angelegt.").classes("text-sm")
                return
            for row in rows:
                with ui.row().classes(ROW_CLASSES):
                    ui.label(row["name"]).classes("w-40 font-medium")
                    ui.label(row["host"]).classes("w-44")
                    ui.label(str(row["hint"])).classes("w-24")
                    ui.label(f"max. {row['max_rows']}").classes("w-24")
                    ui.label("Schreiben" if row["allow_write"] else "nur lesen").classes("w-24")
                    ui.label("aktiv" if row["active"] else "inaktiv").classes("w-16")
                    ui.label(str(row["check"])).classes("w-56 text-xs")
                    _action_button("edit", "Bearbeiten", partial(load, int(row["id"])))
                    _action_button(
                        "network_check", "Verbindung testen", partial(check, int(row["id"]))
                    )

        def load(profile_id: int) -> None:
            with session_scope(session_factory) as session:
                profile = session.get(Profile, profile_id)
                if profile is None:
                    return
                editing["id"] = profile.id
                name_input.value = profile.name
                host_input.value = profile.host
                key_input.value = ""
                retries_input.value = profile.max_retries
                rows_input.value = profile.max_rows
                write_switch.value = profile.allow_write
                active_switch.value = profile.is_active
            status.set_text("Profil geladen - Key bleibt unveraendert, solange das Feld leer ist.")

        def clear_form() -> None:
            editing["id"] = None
            name_input.value = ""
            host_input.value = ""
            key_input.value = ""
            retries_input.value = 3
            rows_input.value = 5_000
            write_switch.value = True
            active_switch.value = True
            status.set_text("Neues Profil")

        def save() -> None:
            data = ProfileData(
                name=name_input.value or "",
                host=host_input.value or "",
                api_key=key_input.value or None,
                max_retries=int(retries_input.value or 0),
                max_rows=int(rows_input.value or 0),
                allow_write=bool(write_switch.value),
                is_active=bool(active_switch.value),
            )
            try:
                with session_scope(session_factory) as session:
                    actor = session.get(AppUser, user.id)
                    if editing["id"] is None:
                        profile = create_profile(session, secret_box, data, actor=actor)
                    else:
                        existing = session.get(Profile, editing["id"])
                        if existing is None:
                            raise ProfileError("Profil nicht gefunden.")
                        profile = update_profile(session, secret_box, existing, data, actor=actor)
                    profile_id = profile.id
                    profile_name = profile.name
            except ProfileError as exc:
                status.set_text(f"Fehler: {exc}")
                return
            client_factory.invalidate(profile_id)
            key_input.value = ""
            status.set_text(f"Profil {profile_name!r} gespeichert.")
            profile_rows.refresh()

        async def check(profile_id: int) -> None:
            with session_scope(session_factory) as session:
                profile = session.get(Profile, profile_id)
                if profile is None:
                    return
                client = client_factory.client_for(profile)
            try:
                pixxio_user = await run.io_bound(partial(current_user_name, client))
                ok = True
                message = f"Verbindung OK als {pixxio_user or 'unbekannt'}."
            except (PIXXIOException, UndecryptableApiKeyError) as exc:
                ok = False
                pixxio_user = None
                message = f"Verbindung fehlgeschlagen: {exc}"
            with session_scope(session_factory) as session:
                profile = session.get(Profile, profile_id)
                actor = session.get(AppUser, user.id)
                if profile is not None:
                    record_connection_check(
                        session, profile, ok=ok, pixxio_user=pixxio_user, actor=actor
                    )
            status.set_text(message)
            profile_rows.refresh()

        with buttons:
            ui.button("Speichern", on_click=save).props("dense")
            ui.button("Neu", on_click=clear_form).props("dense flat")

        with list_container:
            ui.label("Vorhandene Profile").classes("font-semibold mt-2")
            profile_rows()

    @ui.page("/admin/users")
    def users_page() -> None:  # pyright: ignore[reportUnusedFunction]
        user = _authenticated(session_factory, "Benutzer")
        if user is None:
            return

        editing: dict[str, int | None] = {"id": None}
        status = ui.label("").classes("text-sm")
        list_container = ui.column().classes("w-full gap-1")
        form_container = ui.column().classes("w-full max-w-4xl gap-2")

        with session_scope(session_factory) as session:
            profile_options = {
                profile.id: profile.name
                for profile in session.scalars(select(Profile).order_by(Profile.name))
            }

        with form_container:
            ui.label("Benutzer anlegen oder bearbeiten").classes("font-semibold mt-4")
            username_input = ui.input("Benutzername").props("outlined dense").classes("w-72")
            password_input = (
                ui.input("Passwort", password=True, password_toggle_button=True)
                .props("outlined dense")
                .classes("w-72")
            )
            ui.label("Beim Bearbeiten leer lassen, um das Passwort zu behalten.").classes("text-xs")
            role_select = ui.select(
                {role: label for role, label in ROLE_LABELS.items()},
                value=Role.VIEWER,
                label="Rolle",
            ).props("outlined dense")
            script_switch = ui.switch("darf Scripts bearbeiten", value=False)
            profile_select = (
                ui.select(profile_options, multiple=True, label="Profile")
                .props("outlined dense")
                .classes("w-96")
            )
            buttons = ui.row().classes("gap-2")

        @ui.refreshable
        def user_rows() -> None:
            with session_scope(session_factory) as session:
                names = {
                    profile.id: profile.name
                    for profile in session.scalars(select(Profile).order_by(Profile.name))
                }
                rows = [
                    {
                        "id": account.id,
                        "username": account.username,
                        "role": ROLE_LABELS[account.role],
                        "scripts": account.can_edit_scripts,
                        "active": account.is_active,
                        "profiles": ", ".join(
                            names.get(profile.id, "?") for profile in account.profiles
                        ),
                    }
                    for account in session.scalars(select(AppUser).order_by(AppUser.username))
                ]
            for row in rows:
                with ui.row().classes(ROW_CLASSES):
                    ui.label(row["username"]).classes("w-40 font-medium")
                    ui.label(row["role"]).classes("w-28")
                    ui.label("Script-Recht" if row["scripts"] else "-").classes("w-28")
                    ui.label("aktiv" if row["active"] else "inaktiv").classes("w-16")
                    ui.label(row["profiles"] or "-").classes("w-64 text-xs")
                    _action_button("edit", "Bearbeiten", partial(load, int(row["id"])))
                    if row["active"]:
                        _action_button(
                            "block", "Deaktivieren", partial(toggle, int(row["id"]), False)
                        )
                    else:
                        _action_button(
                            "check_circle", "Aktivieren", partial(toggle, int(row["id"]), True)
                        )

        def load(account_id: int) -> None:
            with session_scope(session_factory) as session:
                account = session.get(AppUser, account_id)
                if account is None:
                    return
                editing["id"] = account.id
                username_input.value = account.username
                password_input.value = ""
                role_select.value = account.role
                script_switch.value = account.can_edit_scripts
                profile_select.value = [profile.id for profile in account.profiles]
            status.set_text("Benutzer geladen")

        def clear_form() -> None:
            editing["id"] = None
            username_input.value = ""
            password_input.value = ""
            role_select.value = Role.VIEWER
            script_switch.value = False
            profile_select.value = []
            status.set_text("Neuer Benutzer")

        def save() -> None:
            try:
                with session_scope(session_factory) as session:
                    if editing["id"] is None:
                        account = create_user(
                            session,
                            username=username_input.value or "",
                            password=password_input.value or "",
                            role=role_select.value,
                            can_edit_scripts=bool(script_switch.value),
                        )
                    else:
                        account = session.get(AppUser, editing["id"])
                        if account is None:
                            raise AuthError("Benutzer nicht gefunden.")
                        if account.role is not role_select.value:
                            set_role(session, account, role_select.value)
                        account.can_edit_scripts = bool(script_switch.value)
                        if password_input.value:
                            reset_password(session, account, password_input.value)
                    chosen = profile_select.value or []
                    account.profiles = list(
                        session.scalars(select(Profile).where(Profile.id.in_(chosen)))
                    )
                    username = account.username
            except (AuthError, LastSuperuserError) as exc:
                status.set_text(f"Fehler: {exc}")
                return
            password_input.value = ""
            status.set_text(f"Benutzer {username!r} gespeichert.")
            user_rows.refresh()

        def toggle(account_id: int, active: bool) -> None:
            try:
                with session_scope(session_factory) as session:
                    account = session.get(AppUser, account_id)
                    if account is None:
                        return
                    set_active(session, account, active)
                    username = account.username
            except LastSuperuserError as exc:
                status.set_text(f"Fehler: {exc}")
                return
            status.set_text(f"Benutzer {username!r} {'aktiviert' if active else 'deaktiviert'}.")
            user_rows.refresh()

        with buttons:
            ui.button("Speichern", on_click=save).props("dense")
            ui.button("Neu", on_click=clear_form).props("dense flat")

        with list_container:
            ui.label("Vorhandene Benutzer").classes("font-semibold mt-2")
            user_rows()
