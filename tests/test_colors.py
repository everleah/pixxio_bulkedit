"""Tests der zentralen Farbdefinitionen (Meadow-Farbprofil)."""

from __future__ import annotations

import pytest

from app.colors import (
    FOCUS_CSS,
    PALETTE,
    TEXT_STYLE,
    contrast_ratio,
    hex_to_rgb,
    text_style,
)

PLAN_FARBEN = {
    "primary": "#16a34a",
    "success": "#22c55e",
    "info": "#0ea5e9",
    "info_dark": "#0891b2",
    "warning": "#d97706",
    "warning_light": "#f59e0b",
    "error": "#dc2626",
    "text": "#1e293b",
    "page_background": "#f1f5f9",
    "header_start": "#2d5f4f",
    "header_end": "#4a7c59",
}


def test_palette_entspricht_dem_plan() -> None:
    for name, color in PLAN_FARBEN.items():
        assert getattr(PALETTE, name) == color, name


def test_text_hat_ausreichenden_kontrast_zum_hintergrund() -> None:
    assert contrast_ratio(PALETTE.text, PALETTE.page_background) >= 4.5


def test_headerverlauf_ist_mit_weisser_schrift_lesbar() -> None:
    assert contrast_ratio("#ffffff", PALETTE.header_start) >= 4.5
    assert contrast_ratio("#ffffff", PALETTE.header_end) >= 4.5


def test_primaerfarbe_ist_als_flaeche_erkennbar() -> None:
    assert contrast_ratio("#ffffff", PALETTE.primary) >= 3.0
    assert contrast_ratio(PALETTE.error, PALETTE.page_background) >= 3.0


@pytest.mark.parametrize("kind", ["success", "warning", "error", "info", "muted"])
def test_statustexte_sind_lesbar(kind: str) -> None:
    color = TEXT_STYLE[kind].split(": ", 1)[1]
    assert contrast_ratio(color, PALETTE.page_background) >= 4.5


def test_gefuellte_schaltflaechen_sind_lesbar() -> None:
    """Weisse Schrift auf der Aktionsfarbe muss 4.5:1 erreichen."""
    assert contrast_ratio("#ffffff", PALETTE.action) >= 4.5


def test_fokusrahmen_ist_sichtbar() -> None:
    assert contrast_ratio(PALETTE.primary, PALETTE.page_background) >= 3.0
    assert PALETTE.primary in FOCUS_CSS
    assert "focus-visible" in FOCUS_CSS


def test_statusfarbe_ist_nie_das_einzige_merkmal() -> None:
    """Stile liefern nur die Farbe; den Status zeigt immer zusätzlich Text."""
    for value in TEXT_STYLE.values():
        assert value.startswith("color: #")
    assert text_style("unbekannt") == TEXT_STYLE["muted"]


def test_header_gradient_enthaelt_beide_farben() -> None:
    gradient = PALETTE.header_gradient
    assert PALETTE.header_start in gradient
    assert PALETTE.header_end in gradient


def test_ungueltige_farbe_wird_abgelehnt() -> None:
    with pytest.raises(ValueError, match="#16a34a"):
        hex_to_rgb("gruen")
    assert hex_to_rgb("#16a34a") == (22, 163, 74)
