"""Schema je Profil: Spalten, Feldkennungen und Typen.

Technische Feldkennungen sind durchgaengig ``std:<attribut>`` fuer Standardattribute
der Datei, ``custom:<feld-id>`` fuer Custom-Metadaten und ``standard:<feld-id>`` fuer
Standard-Metadaten. Namen aus ``COLUMNS`` werden hier zu IDs aufgeloest.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pixxio_client import Client
from pixxio_client.metadata import CustomMetadata, StandardMetadata

from app.crypto import SecretBox
from app.models import Profile
from app.scripts.errors import ScriptExecutionError

CUSTOM_PAGE_SIZE = 50
STANDARD_PAGE_SIZE = 100
FIELD_LIMIT = 5_000
FIELD_RESPONSE_FIELDS = ["id", "name", "editType", "selectionOptions"]
DEFAULT_TTL_SECONDS = 900

Source = Literal["file_attr", "custom", "standard"]

# Standardattribute, die direkt an der Datei haengen (filesPut-Felder).
FILE_ATTRS: dict[str, tuple[str, str]] = {
    "subject": ("Titel (Subject)", "text"),
    "description": ("Beschreibung", "text"),
    "creator": ("Urheber", "text"),
    "rating": ("Bewertung", "number"),
    "fileStateID": ("Dateistatus", "selection"),
    "createDate": ("Erstellungsdatum", "date"),
    "location": ("Standort", "text"),
    "fileName": ("Dateiname", "text"),
    "keywords": ("Schlagwoerter", "multiselection"),
}

# Diese Feldtypen sind im ersten Meilenstein nur lesbar (strukturierte Werte).
READ_ONLY_EDIT_TYPES = frozenset({"map", "focalpoint", "orientation"})


@dataclass(frozen=True)
class ColumnDef:
    """Eine Spalte des Arbeitsbestands."""

    key: str
    label: str
    source: Source
    edit_type: str
    field_id: int | None = None
    options: tuple[str, ...] = ()
    option_ids: tuple[tuple[int, str], ...] = ()
    editable: bool = True

    @property
    def multi_value(self) -> bool:
        return self.edit_type in {"multiselection", "language"} or self.key == "std:keywords"

    @property
    def writable(self) -> bool:
        return self.editable and self.key != "std:fileName"


@dataclass(frozen=True)
class MetadataField:
    """Ein Metadatenfeld aus der API."""

    kind: Literal["custom", "standard"]
    id: int
    name: str
    edit_type: str
    options: tuple[str, ...] = ()
    option_ids: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class ProfileSchema:
    """Alle Felder eines Profils."""

    custom: tuple[MetadataField, ...] = ()
    standard: tuple[MetadataField, ...] = ()
    file_attrs: tuple[str, ...] = field(default_factory=lambda: tuple(FILE_ATTRS))

    def by_key(self, key: str) -> ColumnDef | None:
        return next((column for column in self.columns() if column.key == key), None)

    def columns(self) -> list[ColumnDef]:
        columns = [
            ColumnDef(
                key=f"std:{name}",
                label=FILE_ATTRS[name][0],
                source="file_attr",
                edit_type=FILE_ATTRS[name][1],
            )
            for name in self.file_attrs
            if name in FILE_ATTRS
        ]
        columns.extend(
            ColumnDef(
                key=f"custom:{item.id}",
                label=item.name,
                source="custom",
                edit_type=item.edit_type,
                field_id=item.id,
                options=item.options,
                option_ids=item.option_ids,
                editable=item.edit_type not in READ_ONLY_EDIT_TYPES,
            )
            for item in self.custom
        )
        columns.extend(
            ColumnDef(
                key=f"standard:{item.id}",
                label=item.name,
                source="standard",
                edit_type=item.edit_type,
                field_id=item.id,
                options=item.options,
                option_ids=item.option_ids,
                editable=item.edit_type not in READ_ONLY_EDIT_TYPES,
            )
            for item in self.standard
        )
        return columns


def _options(field: dict[str, Any]) -> tuple[tuple[str, ...], tuple[tuple[int, str], ...]]:
    names: list[str] = []
    pairs: list[tuple[int, str]] = []
    for option in field.get("selectionOptions") or []:
        if isinstance(option, dict):
            option_id = option.get("id")
            name = str(option.get("name", "")).strip()
            if name:
                names.append(name)
            if isinstance(option_id, int):
                pairs.append((option_id, name))
    return tuple(names), tuple(pairs)


def _as_field(kind: Literal["custom", "standard"], payload: dict[str, Any]) -> MetadataField:
    names, pairs = _options(payload)
    field_id = payload.get("id")
    return MetadataField(
        kind=kind,
        id=int(field_id) if isinstance(field_id, int) else 0,
        name=str(payload.get("name", "")).strip(),
        edit_type=str(payload.get("editType") or "text"),
        options=names,
        option_ids=pairs,
    )


def fetch_metadata_fields(client: Client) -> list[dict[str, Any]]:
    """Liest Custom- und Standard-Metadatenfelder als einfache Dicts."""
    custom = CustomMetadata(client)
    custom.set_response_fields(FIELD_RESPONSE_FIELDS)
    fields = [
        {"kind": "custom", **_plain(item)}
        for item in custom.iter_all(page_size=CUSTOM_PAGE_SIZE, max_items=FIELD_LIMIT)
    ]
    standard = StandardMetadata(client)
    standard.set_response_fields(["id", "name", "editType"])
    fields.extend(
        {"kind": "standard", **_plain(item)}
        for item in standard.iter_all(page_size=STANDARD_PAGE_SIZE, max_items=FIELD_LIMIT)
    )
    return fields


def _plain(value: object) -> dict[str, Any]:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, dict):
            return dict(result)
    if isinstance(value, dict):
        return dict(value)
    return {}


def build_schema(fields: list[dict[str, Any]]) -> ProfileSchema:
    """Baut das Profilschema aus gelesenen Felddefinitionen."""
    custom = tuple(_as_field("custom", item) for item in fields if item.get("kind") == "custom")
    standard = tuple(
        _as_field("standard", item) for item in fields if item.get("kind") == "standard"
    )
    return ProfileSchema(custom=custom, standard=standard)


def resolve_columns(
    schema: ProfileSchema, keys: list[str] | tuple[str, ...]
) -> tuple[list[ColumnDef], list[str]]:
    """Loest Spaltenschluessel (IDs oder Namen) zu Spalten auf; meldet Unbekanntes."""
    resolved: list[ColumnDef] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in keys:
        text = str(raw).strip()
        if not text:
            continue
        prefix, _, value = text.partition(":")
        column = _resolve_one(schema, prefix, value)
        if column is None:
            unknown.append(text)
            continue
        if column.key not in seen:
            seen.add(column.key)
            resolved.append(column)
    return resolved, unknown


def _resolve_one(schema: ProfileSchema, prefix: str, value: str) -> ColumnDef | None:
    if prefix == "std":
        if value not in FILE_ATTRS:
            return None
        return ColumnDef(
            key=f"std:{value}",
            label=FILE_ATTRS[value][0],
            source="file_attr",
            edit_type=FILE_ATTRS[value][1],
        )
    if prefix not in {"custom", "standard"}:
        return None
    fields = schema.custom if prefix == "custom" else schema.standard
    field_id: int | None = None
    if value.isdigit():
        field_id = int(value)
        match = next((item for item in fields if item.id == field_id), None)
    else:
        match = next((item for item in fields if item.name == value), None)
    if match is None:
        return None
    return ColumnDef(
        key=f"{prefix}:{match.id}",
        label=match.name,
        source="custom" if prefix == "custom" else "standard",
        edit_type=match.edit_type,
        field_id=match.id,
        options=match.options,
        option_ids=match.option_ids,
        editable=match.edit_type not in READ_ONLY_EDIT_TYPES,
    )


class SchemaCache:
    """Haelt das Schema je Profil mit TTL; laedt nur bei Bedarf nach."""

    def __init__(
        self,
        secret_box: SecretBox,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        builder: Any = None,
    ) -> None:
        self._secret_box = secret_box
        self._ttl = float(ttl_seconds)
        self._builder = builder or _load_from_api
        self._entries: dict[int, tuple[float, ProfileSchema]] = {}
        self._lock = threading.RLock()

    def get(self, profile: Profile) -> ProfileSchema:
        if profile.id is None:
            raise ScriptExecutionError("Profil ohne ID hat kein Schema.")
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(profile.id)
            if cached is not None and now - cached[0] < self._ttl:
                return cached[1]
        api_key = self._secret_box.decrypt(profile.api_key_enc)
        schema = self._builder(profile, api_key)
        with self._lock:
            self._entries[profile.id] = (now, schema)
        return schema

    def invalidate(self, profile_id: int) -> None:
        with self._lock:
            self._entries.pop(profile_id, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def cached_profile_ids(self) -> list[int]:
        with self._lock:
            return sorted(self._entries)


def _load_from_api(profile: Profile, api_key: str) -> ProfileSchema:
    try:
        client = Client.create_client(api_key, profile.host, max_retries=profile.max_retries)
        return build_schema(fetch_metadata_fields(client))
    except Exception as exc:  # noqa: BLE001 - Clientfehler in ScriptError uebersetzen
        raise ScriptExecutionError(f"Schema konnte nicht geladen werden: {exc}") from exc


__all__ = [
    "FILE_ATTRS",
    "ColumnDef",
    "MetadataField",
    "ProfileSchema",
    "SchemaCache",
    "build_schema",
    "fetch_metadata_fields",
    "resolve_columns",
]
