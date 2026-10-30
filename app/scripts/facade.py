"""Read-only Fassade ``px`` fuer Scripts.

Alle Methoden lesen ausschliesslich, liefern einfache Dicts und begrenzen die
Ergebnismenge auf ``max_rows``. Filter werden gegen die Feldtabelle der API geprueft
und Metadatenfelder vor dem Senden von Namen in IDs aufgeloest.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from pixxio_client import Client
from pixxio_client.collections import Collection
from pixxio_client.directories import Directory
from pixxio_client.exceptions import PIXXIOException
from pixxio_client.files import File
from pixxio_client.metadata import CustomMetadata, StandardMetadata

from app.scripts.contract import ScriptResult, validate_filter
from app.scripts.errors import ScriptContractError, ScriptExecutionError

FILES_PAGE_SIZE = 500
METADATA_PAGE_SIZE = 50
# Die directories-API akzeptiert hoechstens 20 Eintraege pro Seite.
DIRECTORY_PAGE_SIZE = 20
# Das Schema ist unabhaengig vom Zeilenlimit des Profils vollstaendig zu laden.
METADATA_FIELD_LIMIT = 5_000
COLLECTION_FIELDS = ["id", "name", "isDynamic", "filesQuantity"]
DIRECTORY_FIELDS = ["id", "name", "parentID", "quantity", "hasChildren"]
FIELD_FIELDS = ["id", "name", "editType", "selectionOptions"]
MAX_CALLS = 1_000
METADATA_FILTER_TYPES = frozenset(
    {"metadataFieldText", "metadataFieldSelection", "metadataFieldDate", "hasMetadataField"}
)
FIELD_REF_KEYS = ("metadataFieldID", "customMetadataFieldID", "standardMetadataFieldID")


def plain(value: object) -> Any:
    """Wandelt Client-Antworten in einfache Python-Werte."""
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return plain(to_dict())
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def single(response: object, key: str) -> dict[str, Any]:
    """Holt das Objekt aus einer Einzelantwort (z.B. ``response.collection``)."""
    payload = plain(response)
    if isinstance(payload, dict):
        inner = payload.get(key)
        if isinstance(inner, dict):
            return inner
        return payload
    raise ScriptExecutionError(f"Unerwartete Antwort der API ({type(response).__name__}).")


class Filters:
    """Baut Filter-Dicts gemaess OpenAPI-Schema der pixx.io-API."""

    def all(self) -> dict[str, Any]:
        return {"filterType": "all"}

    def collection(self, collection_id: int, include_archived: bool = False) -> dict[str, Any]:
        return {
            "filterType": "collection",
            "collectionID": int(collection_id),
            "includeArchived": bool(include_archived),
        }

    def directory(self, directory_id: int, include_subdirectories: bool = False) -> dict[str, Any]:
        return {
            "filterType": "directory",
            "directoryID": int(directory_id),
            "includeSubdirectories": bool(include_subdirectories),
        }

    def files(self, ids: Iterable[int]) -> dict[str, Any]:
        return {"filterType": "files", "fileIDs": [int(item) for item in ids]}

    def _term(
        self, filter_type: str, term: str, exact: bool = False, use_synonyms: bool = False
    ) -> dict[str, Any]:
        return {
            "filterType": filter_type,
            "term": str(term),
            "exactMatch": bool(exact),
            "useSynonyms": bool(use_synonyms),
        }

    def file_name(self, term: str, exact: bool = False) -> dict[str, Any]:
        return self._term("fileName", term, exact)

    def creator(self, term: str, exact: bool = False) -> dict[str, Any]:
        return self._term("creator", term, exact)

    def description(self, term: str, exact: bool = False) -> dict[str, Any]:
        return self._term("description", term, exact)

    def subject(self, term: str, exact: bool = False) -> dict[str, Any]:
        return self._term("subject", term, exact)

    def keyword(self, term: str, exact: bool = False) -> dict[str, Any]:
        return self._term("keyword", term, exact)

    def search_term(self, term: str, exact: bool = False) -> dict[str, Any]:
        return self._term("searchTerm", term, exact)

    def file_extension(self, extension: str) -> dict[str, Any]:
        return {"filterType": "fileExtension", "fileExtension": str(extension)}

    def rating(self, value: int) -> dict[str, Any]:
        return {"filterType": "rating", "rating": int(value)}

    def file_state(self, file_state_id: int) -> dict[str, Any]:
        return {"filterType": "fileState", "fileStateID": int(file_state_id)}

    def upload_date(
        self, date_min: str | None = None, date_max: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"filterType": "uploadDate"}
        if date_min:
            payload["dateMin"] = str(date_min)
        if date_max:
            payload["dateMax"] = str(date_max)
        return payload

    def modify_date(
        self, date_min: str | None = None, date_max: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"filterType": "modifyDate"}
        if date_min:
            payload["dateMin"] = str(date_min)
        if date_max:
            payload["dateMax"] = str(date_max)
        return payload

    def create_date(
        self, date_min: str | None = None, date_max: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"filterType": "createDate"}
        if date_min:
            payload["dateMin"] = str(date_min)
        if date_max:
            payload["dateMax"] = str(date_max)
        return payload

    def is_archived(self, archived: bool = True) -> dict[str, Any]:
        return {"filterType": "isArchived", "inverted": not archived}

    def is_trash(self, in_trash: bool = True) -> dict[str, Any]:
        return {"filterType": "isTrash", "inverted": not in_trash}

    def has_keywords(self, present: bool = True) -> dict[str, Any]:
        return {"filterType": "hasKeywords", "inverted": not present}

    def has_rating(self, present: bool = True) -> dict[str, Any]:
        return {"filterType": "hasRating", "inverted": not present}

    def metadata_text(self, field: int | str, term: str, exact: bool = False) -> dict[str, Any]:
        return {
            "filterType": "metadataFieldText",
            "metadataFieldID": field,
            "term": str(term),
            "exactMatch": bool(exact),
            "useSynonyms": False,
        }

    def metadata_selection(self, field: int | str, selection_option_id: int) -> dict[str, Any]:
        return {
            "filterType": "metadataFieldSelection",
            "metadataFieldID": field,
            "selectionOptionID": int(selection_option_id),
        }

    def metadata_date(
        self, field: int | str, date_min: str | None = None, date_max: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"filterType": "metadataFieldDate", "metadataFieldID": field}
        if date_min:
            payload["dateMin"] = str(date_min)
        if date_max:
            payload["dateMax"] = str(date_max)
        return payload

    def has_metadata_field(self, field: int | str, present: bool = True) -> dict[str, Any]:
        return {
            "filterType": "hasMetadataField",
            "metadataFieldID": field,
            "inverted": not present,
        }

    def and_(self, *filters: dict[str, Any]) -> dict[str, Any]:
        return {"filterType": "connectorAnd", "filters": list(filters)}

    def or_(self, *filters: dict[str, Any]) -> dict[str, Any]:
        return {"filterType": "connectorOr", "filters": list(filters)}

    def not_(self, filter_obj: dict[str, Any]) -> dict[str, Any]:
        inverted = dict(filter_obj)
        inverted["inverted"] = not bool(inverted.get("inverted", False))
        return inverted


class Facade:
    """Das ``px``-Objekt eines Scripts."""

    def __init__(
        self,
        client_provider: Callable[[], Client],
        *,
        max_rows: int,
        log: Callable[[str], None] | None = None,
        max_calls: int = MAX_CALLS,
    ) -> None:
        self._client_provider = client_provider
        self._client: Client | None = None
        self._metadata_cache: list[dict[str, Any]] | None = None
        self._calls = 0
        self._max_calls = max_calls
        self._log = log
        self.max_rows = int(max_rows)
        self.filters = Filters()

    # -- interne Helfer -------------------------------------------------
    def _client_instance(self) -> Client:
        if self._client is None:
            self._client = self._client_provider()
        return self._client

    def _count_call(self, name: str) -> None:
        self._calls += 1
        if self._calls > self._max_calls:
            raise ScriptExecutionError(
                f"Das Script hat mehr als {self._max_calls} API-Aufrufe ausgeloest (bei {name})."
            )

    def _guard(self, name: str, func: Callable[[], Any]) -> Any:
        self._count_call(name)
        try:
            return func()
        except PIXXIOException as exc:
            raise ScriptExecutionError(f"pixx.io meldet bei {name}: {exc}") from exc

    # -- Protokoll ------------------------------------------------------
    def log(self, message: object) -> None:
        if self._log is not None:
            self._log(str(message))

    # -- Stammdaten -----------------------------------------------------
    def collection(self, name_or_id: int | str) -> dict[str, Any]:
        client = self._client_instance()

        def load() -> dict[str, Any]:
            resource = Collection(client)
            resource.set_response_fields(COLLECTION_FIELDS)
            text = str(name_or_id).strip()
            if isinstance(name_or_id, int) or text.isdigit():
                return single(resource.get(int(text)), "collection")
            hits = [
                plain(item)
                for item in resource.iter_all(
                    page_size=METADATA_PAGE_SIZE, max_items=self.max_rows, searchTerm=text
                )
            ]
            exact = [hit for hit in hits if str(hit.get("name")) == text]
            if len(exact) != 1:
                raise ScriptExecutionError(
                    f"{len(exact)} Collections mit dem Namen {text!r} gefunden; bitte ID angeben."
                )
            return exact[0]

        return self._guard("collection", load)

    def collections(self, search: str | None = None) -> list[dict[str, Any]]:
        client = self._client_instance()

        def load() -> list[dict[str, Any]]:
            resource = Collection(client)
            resource.set_response_fields(COLLECTION_FIELDS)
            params: dict[str, Any] = {"page_size": METADATA_PAGE_SIZE, "max_items": self.max_rows}
            if search:
                params["searchTerm"] = search
            return [plain(item) for item in resource.iter_all(**params)]

        return self._guard("collections", load)

    def directory(self, name_or_id: int | str) -> dict[str, Any]:
        client = self._client_instance()

        def load() -> dict[str, Any]:
            resource = Directory(client)
            resource.set_response_fields(DIRECTORY_FIELDS)
            text = str(name_or_id).strip()
            if isinstance(name_or_id, int) or text.isdigit():
                return single(resource.get(int(text)), "directory")
            hits = [
                plain(item)
                for item in resource.iter_all(
                    page_size=DIRECTORY_PAGE_SIZE, max_items=self.max_rows
                )
            ]
            exact = [hit for hit in hits if str(hit.get("name")) == text]
            if len(exact) != 1:
                raise ScriptExecutionError(
                    f"{len(exact)} Verzeichnisse mit dem Namen {text!r} gefunden; bitte ID angeben."
                )
            return exact[0]

        return self._guard("directory", load)

    def directories(self, search: str | None = None) -> list[dict[str, Any]]:
        client = self._client_instance()

        def load() -> list[dict[str, Any]]:
            resource = Directory(client)
            resource.set_response_fields(DIRECTORY_FIELDS)
            items = [
                plain(item)
                for item in resource.iter_all(
                    page_size=DIRECTORY_PAGE_SIZE, max_items=self.max_rows
                )
            ]
            if search:
                needle = search.lower()
                items = [item for item in items if needle in str(item.get("name", "")).lower()]
            return items

        return self._guard("directories", load)

    def metadata_fields(self) -> list[dict[str, Any]]:
        if self._metadata_cache is not None:
            return list(self._metadata_cache)

        def load() -> list[dict[str, Any]]:
            client = self._client_instance()
            custom = CustomMetadata(client)
            custom.set_response_fields(FIELD_FIELDS)
            fields = [
                {"kind": "custom", **plain(item)}
                for item in custom.iter_all(
                    page_size=METADATA_PAGE_SIZE, max_items=METADATA_FIELD_LIMIT
                )
            ]
            standard = StandardMetadata(client)
            standard.set_response_fields(["id", "name", "editType"])
            fields.extend(
                {"kind": "standard", **plain(item)}
                for item in standard.iter_all(
                    page_size=METADATA_PAGE_SIZE, max_items=METADATA_FIELD_LIMIT
                )
            )
            return fields

        fields = self._guard("metadata_fields", load)
        self._metadata_cache = fields
        return list(fields)

    # -- Suche ----------------------------------------------------------
    def count(self, filter_obj: dict[str, Any]) -> int:
        prepared = self._prepare(filter_obj)

        def load() -> int:
            response = File(self._client_instance()).get(filter=prepared, pageSize=1)
            quantity = getattr(response, "quantity", None)
            return int(quantity or 0)

        return int(self._guard("count", load))

    def find_ids(self, filter_obj: dict[str, Any], max_items: int | None = None) -> list[int]:
        prepared = self._prepare(filter_obj)
        limit = self.max_rows if max_items is None else min(int(max_items), self.max_rows)
        if limit <= 0:
            raise ScriptContractError("max_items muss groesser als 0 sein.")

        def load() -> list[int]:
            resource = File(self._client_instance())
            resource.set_response_fields(["id"])
            return [
                int(item.id)
                for item in resource.iter_all(
                    page_size=FILES_PAGE_SIZE, max_items=limit, filter=prepared
                )
            ]

        return list(self._guard("find_ids", load))

    def file(self, file_id: int) -> dict[str, Any]:
        def load() -> dict[str, Any]:
            response = File(self._client_instance()).get(id=int(file_id))
            return single(response, "file")

        return self._guard("file", load)

    # -- Ergebnis -------------------------------------------------------
    def result(
        self,
        filter: dict[str, Any] | None = None,  # noqa: A002 - Name des Script-Vertrags
        ids: Iterable[int] | None = None,
        columns: Iterable[str] | None = None,
        note: str | None = None,
    ) -> ScriptResult:
        if (filter is None) == (ids is None):
            raise ScriptContractError("px.result braucht entweder filter oder ids.")
        if ids is not None:
            values = list(ids)
            if len(values) > self.max_rows:
                raise ScriptContractError(
                    f"px.result: {len(values)} IDs ueberschreiten das Limit von {self.max_rows}."
                )
            return ScriptResult(
                ids=[int(item) for item in values],
                columns=list(columns) if columns else None,
                note=note,
            )
        return ScriptResult(
            filter=validate_filter(filter),
            columns=list(columns) if columns else None,
            note=note,
        )

    # -- Filteraufbereitung --------------------------------------------
    def _prepare(self, filter_obj: object) -> dict[str, Any]:
        validated = validate_filter(filter_obj)
        return self._resolve(validated)

    def _resolve(self, filter_obj: dict[str, Any]) -> dict[str, Any]:
        filter_type = str(filter_obj.get("filterType"))
        resolved = dict(filter_obj)
        if filter_type in {"connectorAnd", "connectorOr"}:
            resolved["filters"] = [self._resolve(item) for item in filter_obj.get("filters") or []]
        elif filter_type in METADATA_FILTER_TYPES:
            resolved = {
                key: value for key, value in filter_obj.items() if key not in FIELD_REF_KEYS
            }
            resolved.update(self._resolve_field_ref(filter_obj))
        return resolved

    def _resolve_field_ref(self, filter_obj: dict[str, Any]) -> dict[str, Any]:
        explicit = {
            key: filter_obj[key]
            for key in ("customMetadataFieldID", "standardMetadataFieldID")
            if key in filter_obj
        }
        if explicit:
            return {key: int(self._field(value)["id"]) for key, value in explicit.items()}
        generic = filter_obj.get("metadataFieldID")
        if generic is None:
            return {}
        field = self._field(generic)
        return {f"{field['kind']}MetadataFieldID": int(field["id"])}

    def _field(self, field: int | str) -> dict[str, Any]:
        fields = self.metadata_fields()
        if isinstance(field, int):
            matches = [item for item in fields if int(item.get("id", 0)) == field]
            if not matches:
                raise ScriptContractError(f"Metadatenfeld mit ID {field} ist unbekannt.")
            return matches[0]
        needle = str(field).strip().lower()
        matches = [item for item in fields if str(item.get("name", "")).lower() == needle]
        if len(matches) != 1:
            raise ScriptContractError(
                f"{len(matches)} Metadatenfelder mit dem Namen {field!r} gefunden."
            )
        return matches[0]


__all__ = ["Facade", "Filters", "plain", "single"]
