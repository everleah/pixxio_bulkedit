"""Lesende Ermittlung von API-Verhalten, Schema und Beispielwerten.

Die ``fetch_*``-Funktionen sprechen die API an; die ``summarize_*``-Funktionen
arbeiten auf reinen Dicts und sind damit offline testbar.
"""

from __future__ import annotations

from typing import Any, cast

from pixxio_client import Client
from pixxio_client.collections import Collection
from pixxio_client.files import File
from pixxio_client.metadata import CustomMetadata, StandardMetadata
from pixxio_client.users import User

from app.spike.client import PAGE_SIZE

COLLECTION_FIELDS: list[str] = ["id", "name", "isDynamic", "filesQuantity"]
SCHEMA_FIELDS: list[str] = ["id", "name", "editType", "selectionOptions"]
STANDARD_SCHEMA_FIELDS: list[str] = ["id", "name", "editType"]
FILLED = (None, "", [], {})


def collection_filter(collection_id: int, include_archived: bool = False) -> dict[str, Any]:
    return {
        "filterType": "collection",
        "collectionID": collection_id,
        "includeArchived": include_archived,
    }


def as_dict(value: Any) -> dict[str, Any]:
    """Wandelt Client-Antwortobjekte in einfache Dicts."""
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(cast("dict[str, Any]", to_dict()))
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(f"Erwartet wird ein Dict oder Antwortobjekt, erhalten: {type(value).__name__}")


def as_plain(value: Any) -> Any:
    """Reduziert verschachtelte Antwortobjekte auf JSON-faehige Werte."""
    if isinstance(value, dict):
        return {key: as_plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [as_plain(item) for item in value]
    if hasattr(value, "to_dict"):
        return as_plain(as_dict(value))
    return value


def fetch_user(client: Client) -> dict[str, Any]:
    return as_dict(User(client).get_current())


def summarize_user(response: dict[str, Any]) -> dict[str, Any]:
    user = as_dict(response.get("user") or {})
    return {"id": user.get("id"), "displayName": user.get("displayName")}


def fetch_collection(client: Client, collection_id: int) -> dict[str, Any]:
    collections = Collection(client)
    collections.set_response_fields(COLLECTION_FIELDS)
    return as_dict(collections.get(collectionIDs=[collection_id], pageSize=1))


def summarize_collection(response: dict[str, Any]) -> dict[str, Any]:
    entries = response.get("collections") or []
    if entries:
        source = as_dict(entries[0])
    else:
        source = as_dict(response.get("collection") or {})
    return {field: source.get(field) for field in COLLECTION_FIELDS}


def fetch_custom_fields(client: Client) -> list[dict[str, Any]]:
    """Custom-Metadaten inklusive editType und Auswahloptionen."""
    custom = CustomMetadata(client)
    custom.set_response_fields(SCHEMA_FIELDS)
    return [as_dict(field) for field in custom.get_all(page_size=PAGE_SIZE)]


def fetch_standard_fields(client: Client) -> list[dict[str, Any]]:
    standard = StandardMetadata(client)
    standard.set_response_fields(STANDARD_SCHEMA_FIELDS)
    return [as_dict(field) for field in standard.get_all(page_size=PAGE_SIZE)]


def _count_by(fields: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in fields:
        name = str(field.get(key))
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def summarize_schema(
    custom_fields: list[dict[str, Any]], standard_fields: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "custom": {
            "count": len(custom_fields),
            "edit_types": _count_by(custom_fields, "editType"),
            "with_selection_options": sum(
                1 for field in custom_fields if field.get("selectionOptions")
            ),
        },
        "standard": {
            "count": len(standard_fields),
            "edit_types": _count_by(standard_fields, "editType"),
        },
    }


def fetch_files_page(client: Client, collection_id: int, limit: int) -> dict[str, Any]:
    page_size = max(1, min(limit, PAGE_SIZE))
    return as_dict(File(client).get(pageSize=page_size, filter=collection_filter(collection_id)))


def summarize_files(page: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in page.get("files") or []:
        data = as_dict(item)
        metadata = as_dict(data.get("metadataFields") or {})
        custom_values: dict[str, Any] = {}
        custom_total = 0
        for field_id, raw_field in metadata.items():
            field = as_dict(raw_field)
            if field.get("type") != "custom":
                continue
            custom_total += 1
            value = field.get("value")
            if value not in FILLED:
                custom_values[str(field.get("name") or field_id)] = as_plain(value)
        rows.append(
            {
                "id": data.get("id"),
                "fileName": data.get("fileName"),
                "modifyDate": data.get("modifyDate"),
                "subject": data.get("subject"),
                "rating": data.get("rating"),
                "keywords": as_plain(list(data.get("keywords") or [])),
                "customFieldCount": custom_total,
                "customFilled": custom_values,
            }
        )
    return rows


def file_count(page: dict[str, Any]) -> int:
    quantity = page.get("quantity")
    if isinstance(quantity, bool):
        return 0
    if isinstance(quantity, int):
        return quantity
    if isinstance(quantity, str) and quantity.isdigit():
        return int(quantity)
    return 0
