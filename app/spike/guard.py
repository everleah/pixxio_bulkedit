"""Schutzgrenze fuer Schreibzugriffe im API-Spike.

Geschrieben werden darf ausschliesslich auf Assets, die der Spike selbst angelegt
hat, und nur auf einem Testsystem.
"""

from __future__ import annotations

from collections.abc import Sequence, Set

from app.spike.errors import WriteNotAllowedError


def assert_write_allowed(
    *,
    is_dev: bool,
    ledger_ids: Set[int],
    collection_ids: Set[int],
    targets: Sequence[int],
) -> None:
    """Prueft alle Ziel-IDs gegen Testsystem, Ledger und Collection."""
    if not is_dev:
        raise WriteNotAllowedError(
            "PXTEST_IS_DEV=true fehlt; Schreibpruefungen sind ausschliesslich auf "
            "einem Testsystem erlaubt."
        )
    if not targets:
        raise WriteNotAllowedError("Es wurden keine Ziel-IDs angegeben.")

    unknown = sorted(set(targets) - ledger_ids)
    if unknown:
        raise WriteNotAllowedError(
            f"Ziel-IDs stehen nicht im Ledger der selbst angelegten Assets: {unknown}."
        )

    outside = sorted(set(targets) - collection_ids)
    if outside:
        raise WriteNotAllowedError(
            f"Ziel-IDs liegen nicht in der freigegebenen Collection: {outside}."
        )


def assert_deletion_allowed(
    *,
    is_dev: bool,
    ledger_ids: Set[int],
    targets: Sequence[int],
) -> None:
    """Prueft Loeschziele: Testsystem und Ledger.

    Die Collection-Mitgliedschaft wird bewusst nicht verlangt: ein bereits
    geloeschtes Asset ist kein Mitglied mehr. Fremde Assets bleiben trotzdem
    geschuetzt, weil nur Ledger-IDs geloescht werden.
    """
    if not is_dev:
        raise WriteNotAllowedError(
            "PXTEST_IS_DEV=true fehlt; Loeschungen sind ausschliesslich auf einem "
            "Testsystem erlaubt."
        )
    if not targets:
        raise WriteNotAllowedError("Es wurden keine Ziel-IDs angegeben.")

    unknown = sorted(set(targets) - ledger_ids)
    if unknown:
        raise WriteNotAllowedError(
            f"Ziel-IDs stehen nicht im Ledger der selbst angelegten Assets: {unknown}."
        )
