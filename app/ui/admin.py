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
from app.colors import TEXT_STYLE
from app.crypto import SecretBox, UndecryptableApiKeyError
from app.db import SessionFactory, session_scope
from app.i18n import describe_error, t
from app.models import AppUser, Profile, Role
from app.profiles import (
    ProfileData,
    ProfileError,
    create_profile,
    delete_profile,
    profile_usage_overview,
    record_connection_check,
    update_profile,
)
from app.ui.guard import current_user, is_superuser, redirect_to_login
from app.ui.shell import apply_locale, apply_palette, page_header
from app.ui.widgets import action_button

ROLE_LABELS: dict[Role, str] = {
    Role.SUPERUSER: "Superuser",
    Role.EDITOR: "Editor",
    Role.VIEWER: "Viewer",
}
ROW_CLASSES = "w-full items-center gap-3 border-b py-1 text-sm"


def _check_label(profile: Profile) -> str:
    if profile.last_check_at is None:
        return t("noch nicht geprüft")
    stamp = profile.last_check_at.strftime("%d.%m.%Y %H:%M")
    if profile.last_check_ok:
        return t(
            "OK: {user} ({stamp})", user=profile.last_check_user or t("unbekannt"), stamp=stamp
        )
    return t("Fehler ({stamp})", stamp=stamp)


def _authenticated(session_factory: SessionFactory, title: str) -> AppUser | None:
    apply_palette()
    apply_locale()
    user = current_user(session_factory)
    if user is None:
        redirect_to_login()
        return None
    page_header(title, user)
    if not is_superuser(user):
        ui.label(t("Kein Zugriff: Diese Seite verwaltet nur ein Superuser.")).classes(
            "font-medium"
        ).style(TEXT_STYLE["error"])
        return None
    return user


def register_admin_pages(
    session_factory: SessionFactory,
    secret_box: SecretBox,
    client_factory: ClientFactory,
) -> None:
    @ui.page("/admin/profiles")
    def profiles_page() -> None:  # pyright: ignore[reportUnusedFunction]
        user = _authenticated(session_factory, t("Profile"))
        if user is None:
            return

        editing: dict[str, int | None] = {"id": None}
        status = ui.label("").classes("text-sm")
        list_container = ui.column().classes("w-full gap-1")
        form_container = ui.column().classes("w-full max-w-4xl gap-2")

        with form_container:
            ui.label(t("Profil anlegen oder bearbeiten")).classes("font-semibold mt-4")
            name_input = ui.input(t("Name")).props("outlined dense").classes("w-80")
            host_input = ui.input(t("Host")).props("outlined dense").classes("w-80")
            key_input = (
                ui.input(t("API-Key"), password=True, password_toggle_button=True)
                .props("outlined dense")
                .classes("w-96")
            )
            ui.label(t("Leer lassen, um den gespeicherten Key zu behalten.")).classes("text-xs")
            with ui.row().classes("gap-4"):
                retries_input = ui.number(t("max. Wiederholungen"), value=3, min=0, max=10).props(
                    "outlined dense"
                )
                rows_input = ui.number(t("max. Zeilen"), value=5_000, min=1, max=50_000).props(
                    "outlined dense"
                )
            with ui.row().classes("gap-4"):
                write_switch = ui.switch(t("Schreiben erlaubt"), value=True)
                active_switch = ui.switch(t("aktiv"), value=True)
            buttons = ui.row().classes("gap-1")

            profile_pending: dict[str, Any] = {"delete": None}

            with ui.dialog() as profile_delete_dialog, ui.card().classes("w-[440px] gap-2"):
                profile_delete_text = ui.label("").classes("text-sm")
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button(t("Abbrechen"), on_click=profile_delete_dialog.close).props(
                        "flat dense"
                    )
                    profile_delete_confirm = ui.button(t("Löschen")).props(
                        "unelevated dense color=negative"
                    )

            def _ask_delete_profile(profile_id: int, name: str) -> None:
                profile_pending["delete"] = profile_id
                profile_delete_text.set_text(
                    t(
                        "Profil '{name}' endgültig löschen? API-Key und Zuordnungen entfallen.",
                        name=name,
                    )
                )
                profile_delete_dialog.open()

            def _delete_profile_now() -> None:
                profile_id = profile_pending["delete"]
                if not isinstance(profile_id, int):
                    return
                with session_scope(session_factory) as session:
                    profile = session.get(Profile, profile_id)
                    actor = session.get(AppUser, user.id)
                    if profile is None:
                        profile_delete_dialog.close()
                        return
                    name = profile.name
                    try:
                        delete_profile(session, profile, actor=actor)
                    except ProfileError as exc:
                        profile_delete_dialog.close()
                        status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                        return
                profile_pending["delete"] = None
                profile_delete_dialog.close()
                client_factory.invalidate(profile_id)
                status.set_text(t("Profil '{name}' gelöscht.", name=name))
                if editing["id"] == profile_id:
                    clear_form()
                profile_rows.refresh()

            profile_delete_confirm.on_click(_delete_profile_now)

            @ui.refreshable
            def profile_rows() -> None:
                with session_scope(session_factory) as session:
                    usage = profile_usage_overview(session)
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
                            "workspaces": usage.get(profile.id, (0, 0))[0],
                            "runs": usage.get(profile.id, (0, 0))[1],
                        }
                        for profile in session.scalars(select(Profile).order_by(Profile.name))
                    ]
                if not rows:
                    ui.label(t("Noch keine Profile angelegt.")).classes("text-sm")
                    return
                for row in rows:
                    used = bool(row["workspaces"] or row["runs"])
                    with ui.row().classes(ROW_CLASSES):
                        ui.label(row["name"]).classes("w-40 font-medium")
                        ui.label(row["host"]).classes("w-44")
                        ui.label(str(row["hint"])).classes("w-24")
                        ui.label(t("max. {rows}", rows=row["max_rows"])).classes("w-24")
                        ui.label(t("Schreiben") if row["allow_write"] else t("nur lesen")).classes(
                            "w-24"
                        )
                        ui.label(t("aktiv") if row["active"] else t("inaktiv")).classes("w-16")
                        usage_text = (
                            t(
                                "{workspaces} Bestände, {runs} Läufe",
                                workspaces=row["workspaces"],
                                runs=row["runs"],
                            )
                            if used
                            else t("unbenutzt")
                        )
                        ui.label(usage_text).classes("w-40 text-xs")
                        ui.label(str(row["check"])).classes("w-56 text-xs")
                        action_button("edit", t("Bearbeiten"), partial(load, int(row["id"])))
                        action_button(
                            "network_check",
                            t("Verbindung testen"),
                            partial(check, int(row["id"])),
                        )
                        if not used:
                            action_button(
                                "delete",
                                t("Profil löschen"),
                                partial(_ask_delete_profile, int(row["id"]), str(row["name"])),
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
            status.set_text(
                t("Profil geladen – der Key bleibt unverändert, solange das Feld leer ist.")
            )

        def clear_form() -> None:
            editing["id"] = None
            name_input.value = ""
            host_input.value = ""
            key_input.value = ""
            retries_input.value = 3
            rows_input.value = 5_000
            write_switch.value = True
            active_switch.value = True
            status.set_text(t("Neues Profil"))

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
                            raise ProfileError(t("Das Profil wurde nicht gefunden."))
                        profile = update_profile(session, secret_box, existing, data, actor=actor)
                    profile_id = profile.id
                    profile_name = profile.name
            except ProfileError as exc:
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            client_factory.invalidate(profile_id)
            key_input.value = ""
            status.set_text(t("Profil '{name}' gespeichert.", name=profile_name))
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
                message = t("Verbindung OK als {user}.", user=pixxio_user or t("unbekannt"))
            except (PIXXIOException, UndecryptableApiKeyError) as exc:
                ok = False
                pixxio_user = None
                message = t("Verbindung fehlgeschlagen: {message}", message=exc)
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
            action_button("save", t("Speichern"), save)
            action_button("restart_alt", t("Neues Profil anlegen"), clear_form)

        with list_container:
            ui.label(t("Vorhandene Profile")).classes("font-semibold mt-2")
            profile_rows()

    @ui.page("/admin/users")
    def users_page() -> None:  # pyright: ignore[reportUnusedFunction]
        user = _authenticated(session_factory, t("Benutzer"))
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
            ui.label(t("Benutzer anlegen oder bearbeiten")).classes("font-semibold mt-4")
            username_input = ui.input(t("Benutzername")).props("outlined dense").classes("w-72")
            password_input = (
                ui.input(t("Passwort"), password=True, password_toggle_button=True)
                .props("outlined dense")
                .classes("w-72")
            )
            ui.label(t("Beim Bearbeiten leer lassen, um das Passwort zu behalten.")).classes(
                "text-xs"
            )
            role_select = ui.select(
                {role: label for role, label in ROLE_LABELS.items()},
                value=Role.VIEWER,
                label=t("Rolle"),
            ).props("outlined dense")
            script_switch = ui.switch(t("darf Scripts bearbeiten"), value=False)
            profile_select = (
                ui.select(profile_options, multiple=True, label=t("Profile"))
                .props("outlined dense")
                .classes("w-96")
            )
            buttons = ui.row().classes("gap-1")

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
                    ui.label(t("Script-Recht") if row["scripts"] else "-").classes("w-28")
                    ui.label(t("aktiv") if row["active"] else t("inaktiv")).classes("w-16")
                    ui.label(row["profiles"] or "-").classes("w-64 text-xs")
                    action_button("edit", t("Bearbeiten"), partial(load, int(row["id"])))
                    if row["active"]:
                        action_button(
                            "block",
                            t("Deaktivieren"),
                            partial(toggle, int(row["id"]), False),
                        )
                    else:
                        action_button(
                            "check_circle",
                            t("Aktivieren"),
                            partial(toggle, int(row["id"]), True),
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
            status.set_text(t("Benutzer geladen"))

        def clear_form() -> None:
            editing["id"] = None
            username_input.value = ""
            password_input.value = ""
            role_select.value = Role.VIEWER
            script_switch.value = False
            profile_select.value = []
            status.set_text(t("Neuer Benutzer"))

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
                            raise AuthError(t("Benutzer nicht gefunden."))
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
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            password_input.value = ""
            status.set_text(t("Benutzer '{name}' gespeichert.", name=username))
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
                status.set_text(t("Fehler: {message}", message=describe_error(exc)))
                return
            status.set_text(
                t("Benutzer '{name}' aktiviert.", name=username)
                if active
                else t("Benutzer '{name}' deaktiviert.", name=username)
            )
            user_rows.refresh()

        with buttons:
            action_button("save", t("Speichern"), save)
            action_button("restart_alt", t("Neuen Benutzer anlegen"), clear_form)

        with list_container:
            ui.label(t("Vorhandene Benutzer")).classes("font-semibold mt-2")
            user_rows()
