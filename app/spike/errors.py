"""Fehlerarten der Phase-1-Pruefungen."""

from __future__ import annotations


class SpikeError(Exception):
    """Fachlicher Abbruch einer Spikepruefung."""


class LedgerError(SpikeError):
    """Das lokale Ledger ist unlesbar oder inkonsistent."""


class WriteNotAllowedError(SpikeError):
    """Eine Schreiboperation wurde durch die Schutzgrenze abgelehnt."""
