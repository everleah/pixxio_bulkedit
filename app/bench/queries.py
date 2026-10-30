"""SQL fuer Abfragen auf dem effektiven Arbeitsstand.

Der effektive Wert ist der ChangeSet-Eintrag, sonst der Snapshot. Ein vorhandener
Eintrag mit ``NULL`` bedeutet ausdruecklich "geleert" und darf nicht auf den
Snapshot zurueckfallen.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

from app.bench.synthetic import json_path

EFFECTIVE_VALUE = (
    "CASE WHEN chg.id IS NOT NULL THEN chg.new_value "
    "ELSE json_extract(asset.values_json, :json_path) END"
)

JOIN_CHANGES = (
    "LEFT JOIN workspace_change AS chg"
    " ON chg.workspace_id = asset.workspace_id"
    " AND chg.file_id = asset.file_id"
    " AND chg.field_key = :field_key"
)

# Filter greift auf einer eigenen Spalte, unabhaengig von der Sortierspalte.
FILTER_VALUE = (
    "CASE WHEN fchg.id IS NOT NULL THEN fchg.new_value "
    "ELSE json_extract(asset.values_json, :filter_json_path) END"
)

FILTER_JOIN = (
    "LEFT JOIN workspace_change AS fchg"
    " ON fchg.workspace_id = asset.workspace_id"
    " AND fchg.file_id = asset.file_id"
    " AND fchg.field_key = :filter_field_key"
)


def page_query() -> TextClause:
    """Erster bzw. beliebiger Tabellenblock aus dem Snapshot."""
    return text(
        "SELECT asset.file_id, asset.values_json "
        "FROM workspace_asset AS asset "
        "WHERE asset.workspace_id = :workspace_id "
        "ORDER BY asset.position "
        "LIMIT :limit OFFSET :offset"
    )


def equality_count_query() -> TextClause:
    """Anzahl Treffer einer exakten Wertsuche im effektiven Stand."""
    return text(
        "SELECT COUNT(*) FROM workspace_asset AS asset "
        f"{JOIN_CHANGES} "
        "WHERE asset.workspace_id = :workspace_id "
        f"AND {EFFECTIVE_VALUE} = :value"
    )


def range_sorted_query() -> TextClause:
    """Bereichsfilter plus Sortierung im effektiven Stand."""
    return text(
        "SELECT asset.file_id FROM workspace_asset AS asset "
        f"{JOIN_CHANGES} "
        "WHERE asset.workspace_id = :workspace_id "
        f"AND CAST({EFFECTIVE_VALUE} AS REAL) >= :minimum "
        f"ORDER BY CAST({EFFECTIVE_VALUE} AS REAL) "
        "LIMIT :limit"
    )


def json_parameters(field_key: str) -> dict[str, str]:
    return {"field_key": field_key, "json_path": json_path(field_key)}


def filter_parameters(field_key: str) -> dict[str, str]:
    return {"filter_field_key": field_key, "filter_json_path": json_path(field_key)}


def rows_query(descending: bool) -> TextClause:
    """Blockabruf fuer das Grid inklusive Filter und Sortierung im effektiven Stand."""
    direction = "DESC" if descending else "ASC"
    return text(
        "SELECT asset.file_id, asset.values_json FROM workspace_asset AS asset "
        f"{JOIN_CHANGES} {FILTER_JOIN} "
        "WHERE asset.workspace_id = :workspace_id "
        "AND (:filter IS NULL OR " + FILTER_VALUE + " LIKE :filter) "
        f"ORDER BY {EFFECTIVE_VALUE} {direction}, asset.file_id {direction} "
        "LIMIT :limit OFFSET :offset"
    )


def filtered_count_query() -> TextClause:
    """Trefferzahl zum gesetzten Filter."""
    return text(
        "SELECT COUNT(*) FROM workspace_asset AS asset "
        f"{FILTER_JOIN} "
        "WHERE asset.workspace_id = :workspace_id "
        "AND (:filter IS NULL OR " + FILTER_VALUE + " LIKE :filter)"
    )
