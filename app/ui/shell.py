"""Gemeinsamer Seitenrahmen mit Palette, Navigation, Sprache und Abmeldung."""

from __future__ import annotations

from nicegui import app, ui

from app.colors import FOCUS_CSS, PALETTE
from app.i18n import LOCALE_LABELS, LOCALE_STORAGE_KEY, get_locale, set_locale, t
from app.models import AppUser, Role
from app.ui.guard import logout
from app.ui.widgets import action_button, nav_link


def apply_palette() -> None:
    """Quasar-Farben setzen; gefuellte Flaechen nutzen die kontraststarke Variante."""
    ui.colors(
        primary=PALETTE.action,
        secondary=PALETTE.info_dark,
        negative=PALETTE.text_error,
        warning=PALETTE.text_warning,
        positive=PALETTE.text_success,
        info=PALETTE.text_info,
    )
    ui.add_head_html(FOCUS_CSS)


def apply_locale() -> str:
    """Sprache aus der Session übernehmen (Standard: Deutsch)."""
    try:
        stored = app.storage.user.get(LOCALE_STORAGE_KEY)
    except RuntimeError:  # pragma: no cover - kein Session-Kontext
        stored = None
    return set_locale(stored)


def store_locale(locale: str) -> None:
    resolved = set_locale(locale)
    try:
        app.storage.user[LOCALE_STORAGE_KEY] = resolved
    except RuntimeError:  # pragma: no cover - kein Session-Kontext
        pass


def page_header(title: str, user: AppUser) -> None:
    """Kopfzeile mit Navigation; Admin-Links nur für Superuser."""
    with (
        ui.row()
        .classes("w-full items-center gap-4 rounded p-3")
        .style(f"background: {PALETTE.header_gradient}; color: #ffffff")
    ):
        ui.label(title).classes("text-lg font-semibold")
        nav_link(t("Start"), "/")
        nav_link(t("Arbeitsbestände"), "/workspaces")
        nav_link(t("Läufe"), "/runs")
        nav_link(t("Scripts"), "/scripts")
        if user.role is Role.SUPERUSER:
            nav_link(t("Profile"), "/admin/profiles")
            nav_link(t("Benutzer"), "/admin/users")
        ui.label(f"{user.username} ({user.role.value})").classes("ml-auto text-sm")
        _locale_switch()
        action_button("logout", t("Abmelden"), logout, color="white")


def _locale_switch() -> None:
    """Sprachumschalter aus zwei Icon-Schaltflächen."""
    current = get_locale()
    with ui.row().classes("items-center gap-1"):
        for code, label in LOCALE_LABELS.items():
            button = ui.button(label).props("flat dense color=white")
            button.style(f"opacity: {1 if code == current else 0.45}")
            button.props(f'aria-label="{label}"')
            button.tooltip(t("Sprache wechseln"))
            button.on("click", lambda _event=None, value=code: _switch(value))


def _switch(locale: str) -> None:
    store_locale(locale)
    ui.navigate.reload()
