"""Tests der zentralen Farbdefinitionen."""

from __future__ import annotations

import pytest

from app.colors import PALETTE, contrast_ratio, hex_to_rgb


def test_text_hat_ausreichenden_kontrast_zum_hintergrund() -> None:
    assert contrast_ratio(PALETTE.text, PALETTE.page_background) >= 4.5


def test_headerverlauf_ist_mit_weisser_schrift_lesbar() -> None:
    assert contrast_ratio("#ffffff", PALETTE.header_start) >= 4.5
    assert contrast_ratio("#ffffff", PALETTE.header_end) >= 4.5


def test_primaerfarbe_ist_als_flaeche_erkennbar() -> None:
    assert contrast_ratio("#ffffff", PALETTE.primary) >= 3.0
    assert contrast_ratio(PALETTE.error, PALETTE.page_background) >= 3.0


def test_header_gradient_enthaelt_beide_farben() -> None:
    gradient = PALETTE.header_gradient
    assert PALETTE.header_start in gradient
    assert PALETTE.header_end in gradient


def test_ungueltige_farbe_wird_abgelehnt() -> None:
    with pytest.raises(ValueError, match="#16a34a"):
        hex_to_rgb("gruen")
    assert hex_to_rgb("#16a34a") == (22, 163, 74)
