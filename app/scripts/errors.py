"""Fehlerarten des Script-Systems."""

from __future__ import annotations


class ScriptError(Exception):
    """Oberklasse aller Script-Fehler; die Meldung ist fuer die UI gedacht."""


class ScriptContractError(ScriptError):
    """Das Script verletzt den Vertrag (PARAMS, COLUMNS oder Rueckgabe)."""


class ScriptSecurityError(ScriptError):
    """RestrictedPython hat das Script abgelehnt."""


class ScriptTimeoutError(ScriptError):
    """Die Ausfuehrung hat das Zeitlimit ueberschritten."""


class ScriptExecutionError(ScriptError):
    """Das Script hat zur Laufzeit einen Fehler ausgeloest."""


__all__ = [
    "ScriptContractError",
    "ScriptError",
    "ScriptExecutionError",
    "ScriptSecurityError",
    "ScriptTimeoutError",
]
