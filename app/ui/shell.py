"""Gemeinsamer Seitenrahmen mit Palette, Navigation und Abmeldung."""

from __future__ import annotations

from nicegui import ui

from app.colors import PALETTE
from app.models import AppUser, Role
from app.ui.guard import logout


def apply_palette() -> None:
    ui.colors(
        primary=PALETTE.primary,
        secondary=PALETTE.info_dark,
        negative=PALETTE.error,
        warning=PALETTE.warning,
        positive=PALETTE.success,
    )


def page_header(title: str, user: AppUser) -> None:
    """Kopfzeile mit Navigation; Admin-Links nur fuer Superuser."""
    with (
        ui.row()
        .classes("w-full items-center gap-4 rounded p-3")
        .style(f"background: {PALETTE.header_gradient}; color: #ffffff")
    ):
        ui.label(title).classes("text-lg font-semibold")
        ui.link("Start", "/").classes("text-white")
        ui.link("Scripts", "/scripts").classes("text-white")
        if user.role is Role.SUPERUSER:
            ui.link("Profile", "/admin/profiles").classes("text-white")
            ui.link("Benutzer", "/admin/users").classes("text-white")
        ui.label(f"{user.username} ({user.role.value})").classes("ml-auto text-sm")
        ui.button("Abmelden", on_click=logout).props("flat dense color=white")
