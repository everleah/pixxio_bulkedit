"""Mitgelieferte Script-Vorlagen.

Die Vorlagen werden als ``is_template``-Scripts gepflegt und bei Bedarf angelegt.
Erlaubte Filter und Feldformen stammen aus der OpenAPI-Beschreibung der pixx.io-API
(Stand 30.10.2026); Kombinationen laufen ueber ``connectorAnd``/``connectorOr``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    name: str
    description: str
    source: str


COLLECTION = '''"""Alle Assets einer Collection."""

PARAMS = {
    "collection": {"type": "str", "label": "Collection (Name oder ID)", "required": True},
    "include_archived": {
        "type": "bool",
        "label": "Archivierte einbeziehen",
        "default": False,
    },
}

COLUMNS = ["std:subject", "std:description"]


def query(px, params):
    col = px.collection(params["collection"])
    px.log(f"Collection '{col['name']}' (ID {col['id']}), dynamisch: {col['isDynamic']}")
    return px.filters.collection(col["id"], include_archived=params["include_archived"])
'''

DIRECTORY = '''"""Alle Assets eines Verzeichnisses, optional mit Unterverzeichnissen."""

PARAMS = {
    "directory": {"type": "str", "label": "Verzeichnis (Name oder ID)", "required": True},
    "recursive": {
        "type": "bool",
        "label": "Unterverzeichnisse einbeziehen",
        "default": True,
    },
}


def query(px, params):
    folder = px.directory(params["directory"])
    px.log(f"Verzeichnis '{folder['name']}' (ID {folder['id']})")
    return px.filters.directory(folder["id"], include_subdirectories=params["recursive"])
'''

ID_LIST = '''"""Feste Liste von File-IDs."""

PARAMS = {
    "ids": {"type": "str", "label": "File-IDs (Komma getrennt)", "required": True},
}


def query(px, params):
    ids = [int(part) for part in params["ids"].replace(" ", ",").split(",") if part]
    px.log(f"{len(ids)} IDs uebergeben")
    return ids
'''

SEARCH = '''"""Volltextsuche mit Metadatenfeld-Filter."""

PARAMS = {
    "term": {"type": "str", "label": "Suchbegriff", "required": True},
    "field": {"type": "str", "label": "Metadatenfeld (Name, optional)"},
    "collection": {"type": "str", "label": "Collection (Name oder ID, optional)"},
}


def query(px, params):
    terms = [px.filters.search_term(params["term"])]
    if params["field"]:
        terms.append(px.filters.has_metadata_field(params["field"]))
    if params["collection"]:
        col = px.collection(params["collection"])
        terms.append(px.filters.collection(col["id"]))
    if len(terms) == 1:
        return terms[0]
    return px.filters.and_(*terms)
'''

TEMPLATES: tuple[Template, ...] = (
    Template("Collection", "Alle Assets einer Collection (Filter).", COLLECTION),
    Template("Verzeichnis", "Alle Assets eines Verzeichnisses (Filter).", DIRECTORY),
    Template("ID-Liste", "Feste Liste von File-IDs.", ID_LIST),
    Template("Suche", "Volltextsuche, optional mit Feld- und Collection-Filter.", SEARCH),
)


def find_template(name: str) -> Template | None:
    return next((item for item in TEMPLATES if item.name == name), None)


__all__ = ["TEMPLATES", "Template", "find_template"]
