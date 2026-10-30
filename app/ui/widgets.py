"""Gemeinsame Bedienelemente der Oberfläche."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui


def action_button(
    icon: str,
    label: str,
    handler: Callable[..., Any] | None = None,
    *,
    color: str = "primary",
    dense: bool = True,
) -> Any:
    """Icon-Button mit Tooltip und ``aria-label``; Text erscheint nur als Tooltip."""
    button = ui.button(on_click=handler, icon=icon).props(
        f"flat round{' dense' if dense else ''} color={color}"
    )
    button.tooltip(label)
    button.props(f'aria-label="{label}"')
    return button


def nav_link(label: str, target: str) -> Any:
    """Navigationslink in der Kopfzeile."""
    link = ui.link(label, target).classes("text-white")
    link.props(f'aria-label="{label}"')
    return link


__all__ = ["action_button", "nav_link"]
