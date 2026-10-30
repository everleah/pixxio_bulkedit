"""Zentrale Farbdefinitionen (Meadow-Farbprofil).

Status wird zusaetzlich durch Text oder Symbole vermittelt, damit Farbe allein
keine Information traegt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """Meadow-Farbprofil plus kontraststarke Textvarianten.

    Die Flaechenfarben entsprechen dem freigegebenen Plan. Fuer Text und gefuellte
    Schaltflaechen sind sie zu hell (WCAG AA verlangt 4.5:1); deshalb gibt es
    abgeleitete, dunklere Varianten.
    """

    primary: str = "#16a34a"
    success: str = "#22c55e"
    surface_success: str = "#dcfce7"
    info: str = "#0ea5e9"
    info_dark: str = "#0891b2"
    warning: str = "#d97706"
    warning_light: str = "#f59e0b"
    error: str = "#dc2626"
    text: str = "#1e293b"
    page_background: str = "#f1f5f9"
    header_start: str = "#2d5f4f"
    header_end: str = "#4a7c59"
    action: str = "#15803d"
    text_success: str = "#15803d"
    text_warning: str = "#b45309"
    text_error: str = "#b91c1c"
    text_info: str = "#0369a1"
    text_muted: str = "#475569"

    @property
    def header_gradient(self) -> str:
        return f"linear-gradient(135deg, {self.header_start} 0%, {self.header_end} 100%)"


PALETTE = Palette()

TEXT_STYLE: dict[str, str] = {
    "success": f"color: {PALETTE.text_success}",
    "warning": f"color: {PALETTE.text_warning}",
    "error": f"color: {PALETTE.text_error}",
    "info": f"color: {PALETTE.text_info}",
    "muted": f"color: {PALETTE.text_muted}",
}

# Sichtbarer Fokus fuer Tastaturnutzung; die Farbe ist nie das einzige Merkmal.
FOCUS_CSS = f"""
<style>
  .q-field--focused .q-field__control:after {{ border-color: {PALETTE.primary}; }}
  :where(a, button, [role="button"], input, select, textarea, [tabindex]):focus-visible {{
    outline: 3px solid {PALETTE.primary};
    outline-offset: 2px;
    border-radius: 4px;
  }}
  .ag-cell:focus-visible, .ag-cell-focus {{
    outline: 2px solid {PALETTE.primary};
    outline-offset: -2px;
  }}
</style>
"""


def text_style(kind: str) -> str:
    """CSS-Stil fuer Status- oder Hinweistext (kontraststark auf hellem Grund)."""
    return TEXT_STYLE.get(kind, TEXT_STYLE["muted"])


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Erwartet wird ein Farbwert wie #16a34a, erhalten: {color!r}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _relative_luminance(color: str) -> float:
    def channel(raw: int) -> float:
        srgb = raw / 255
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(value) for value in hex_to_rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG-Kontrastverhaeltnis zweier Farben (1.0 bis 21.0)."""
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)
