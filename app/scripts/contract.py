"""Vertrag der Abfrage-Scripts: ``PARAMS``, ``COLUMNS`` und Rueckgabewerte.

Die Feldtabelle der Filter stammt aus der OpenAPI-Beschreibung der pixx.io-API
(`openapi.json` im Client-Repository) und ist am 30.10.2026 gegen das Testsystem
geprueft worden.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass
from typing import Any

from app.scripts.errors import ScriptContractError

PARAM_TYPES = frozenset({"str", "int", "float", "bool"})
COLUMN_PATTERN = re.compile(r"^(std|custom|standard):[A-Za-z0-9_.\- ]+$")

# Feldarten der Filterwerte:
#   int, float, bool, str, int_list (Liste positiver IDs), filter_list (verschachtelt)
FILTER_TYPE_FIELDS: dict[str, dict[str, str]] = {
    "all": {},
    "collection": {"collectionID": "int", "includeArchived": "bool"},
    "colorspace": {"colorspace": "str"},
    "connectorAnd": {"filters": "filter_list"},
    "connectorOr": {"filters": "filter_list"},
    "createDate": {"dateMax": "str", "dateMin": "str"},
    "creator": {"exactMatch": "bool", "term": "str", "useSynonyms": "bool"},
    "description": {"exactMatch": "bool", "term": "str", "useSynonyms": "bool"},
    "directory": {"directoryID": "int", "includeSubdirectories": "bool"},
    "externalShare": {"externalShareID": "int"},
    "fileExtension": {"fileExtension": "str"},
    "fileName": {"exactMatch": "bool", "term": "str", "useSynonyms": "bool"},
    "fileState": {"fileStateID": "int"},
    "fileType": {"fileType": "str"},
    "files": {"fileIDs": "int_list"},
    "formatType": {"formatType": "str"},
    "hasCreateDate": {},
    "hasCreator": {},
    "hasDescription": {},
    "hasExpiredLicense": {},
    "hasExpiringLicense": {"days": "int"},
    "hasFileState": {},
    "hasKeywords": {},
    "hasLanguageCodes": {},
    "hasLicenseExpirationDate": {},
    "hasLicenseRelease": {},
    "hasLocation": {},
    "hasMetadataField": {
        "customMetadataFieldID": "field_ref",
        "metadataFieldID": "field_ref",
        "standardMetadataFieldID": "field_ref",
    },
    "hasModelRelease": {},
    "hasPropertyRelease": {},
    "hasRating": {},
    "hasUploadLink": {},
    "hasValidLicense": {},
    "hasVariantStack": {},
    "height": {"max": "int", "min": "int"},
    "isArchived": {},
    "isCheckedOut": {},
    "isConvertible": {},
    "isDownloadLocked": {},
    "isRotatable": {},
    "isSubversion": {},
    "isTrash": {},
    "keyword": {"exactMatch": "bool", "term": "str", "useSynonyms": "bool"},
    "languageCode": {"exactMatch": "bool", "languageCode": "str"},
    "licenseExpirationDate": {"dateMax": "str", "dateMin": "str"},
    "licenseRelease": {"licenseReleaseID": "int"},
    "location": {"location": "str"},
    "longSide": {"max": "int", "min": "int"},
    "markedUser": {"markedUserID": "int"},
    "metadataFieldDate": {
        "customMetadataFieldID": "field_ref",
        "dateMax": "str",
        "dateMin": "str",
        "metadataFieldID": "field_ref",
        "standardMetadataFieldID": "field_ref",
    },
    "metadataFieldLocation": {
        "customMetadataFieldID": "field_ref",
        "location": "str",
        "metadataFieldID": "field_ref",
        "standardMetadataFieldID": "field_ref",
    },
    "metadataFieldSelection": {
        "customMetadataFieldID": "field_ref",
        "selectionOptionID": "int",
        "standardMetadataFieldID": "field_ref",
    },
    "metadataFieldText": {
        "customMetadataFieldID": "field_ref",
        "exactMatch": "bool",
        "metadataFieldID": "field_ref",
        "standardMetadataFieldID": "field_ref",
        "term": "str",
        "useSynonyms": "bool",
    },
    "modelRelease": {"modelReleaseID": "int"},
    "modifyDate": {"dateMax": "str", "dateMin": "str"},
    "orientation": {"orientation": "str"},
    "person": {"personID": "int"},
    "pixel": {"max": "int", "min": "int"},
    "propertyRelease": {"propertyReleaseID": "int"},
    "rating": {"rating": "int"},
    "searchTerm": {"exactMatch": "bool", "term": "str", "useSynonyms": "bool"},
    "shortSide": {"max": "int", "min": "int"},
    "subject": {"exactMatch": "bool", "term": "str", "useSynonyms": "bool"},
    "uploadDate": {"dateMax": "str", "dateMin": "str"},
    "uploadLink": {"uploadLinkID": "int"},
    "uploadLinkGuestUserName": {"uploadLinkGuestUserName": "str"},
    "user": {"userID": "int"},
    "variantStack": {"variantStackID": "int"},
    "width": {"max": "int", "min": "int"},
}

# Filter ohne diese Felder lehnt die API mit einer Decoder-Meldung ab.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "collection": ("collectionID",),
    "directory": ("directoryID",),
    "files": ("fileIDs",),
    "connectorAnd": ("filters",),
    "connectorOr": ("filters",),
    "rating": ("rating",),
    "fileState": ("fileStateID",),
    "externalShare": ("externalShareID",),
    "licenseRelease": ("licenseReleaseID",),
    "modelRelease": ("modelReleaseID",),
    "propertyRelease": ("propertyReleaseID",),
    "markedUser": ("markedUserID",),
    "person": ("personID",),
    "uploadLink": ("uploadLinkID",),
    "user": ("userID",),
    "variantStack": ("variantStackID",),
    "fileExtension": ("fileExtension",),
    "fileType": ("fileType",),
    "formatType": ("formatType",),
    "colorspace": ("colorspace",),
    "orientation": ("orientation",),
    "fileName": ("term",),
    "creator": ("term",),
    "description": ("term",),
    "subject": ("term",),
    "keyword": ("term",),
    "searchTerm": ("term",),
    "metadataFieldText": ("term",),
    "metadataFieldSelection": ("selectionOptionID",),
    "metadataFieldLocation": ("location",),
    "languageCode": ("languageCode",),
}

ID_FIELDS = frozenset(
    {
        "collectionID",
        "directoryID",
        "fileIDs",
        "fileStateID",
        "externalShareID",
        "licenseReleaseID",
        "modelReleaseID",
        "propertyReleaseID",
        "markedUserID",
        "personID",
        "uploadLinkID",
        "userID",
        "variantStackID",
        "customMetadataFieldID",
        "standardMetadataFieldID",
        "metadataFieldID",
        "selectionOptionID",
    }
)

UNKNOWN_FIELD_HINT = "Erlaubte Filtertypen stehen in der Fassadendokumentation (px.filters)."


@dataclass(frozen=True)
class ParamSpec:
    """Ein Eingabeparameter aus ``PARAMS``."""

    name: str
    type: str = "str"
    label: str | None = None
    required: bool = False
    default: Any = None
    help: str | None = None

    @property
    def title(self) -> str:
        return self.label or self.name


@dataclass(frozen=True)
class ScriptResult:
    """Validierte Rueckgabe eines Scripts."""

    filter: dict[str, Any] | None = None
    ids: list[int] | None = None
    columns: list[str] | None = None
    note: str | None = None


def _fail(message: str) -> ScriptContractError:
    return ScriptContractError(message)


def _is_identifier(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name)


def parse_params(raw: object) -> dict[str, ParamSpec]:
    """Prueft ``PARAMS`` und liefert die Reihenfolge der Definition zurueck."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _fail("PARAMS muss ein dict sein.")
    specs: dict[str, ParamSpec] = {}
    for name, spec in raw.items():
        if not isinstance(name, str) or not _is_identifier(name):
            raise _fail(f"PARAMS: {name!r} ist kein gueltiger Parametername.")
        if not isinstance(spec, dict):
            raise _fail(f"PARAMS[{name!r}] muss ein dict sein.")
        unknown = set(spec) - {"type", "label", "required", "default", "help"}
        if unknown:
            raise _fail(f"PARAMS[{name!r}]: unbekannte Schluessel {sorted(unknown)}.")
        param_type = spec.get("type", "str")
        if param_type not in PARAM_TYPES:
            raise _fail(
                f"PARAMS[{name!r}]: Typ {param_type!r} wird nicht unterstuetzt "
                f"({', '.join(sorted(PARAM_TYPES))})."
            )
        default = spec.get("default")
        if default is not None:
            try:
                coerce_value(name, param_type, default)
            except ScriptContractError as exc:
                raise _fail(f"PARAMS[{name!r}]: Default passt nicht zum Typ: {exc}") from exc
        specs[name] = ParamSpec(
            name=name,
            type=param_type,
            label=spec.get("label"),
            required=bool(spec.get("required", False)),
            default=default,
            help=spec.get("help"),
        )
    return specs


def coerce_value(name: str, param_type: str, value: Any) -> Any:
    """Wandelt einen Formularwert in den deklarierten Typ."""
    if param_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "ja", "yes", "on"}:
                return True
            if lowered in {"", "0", "false", "nein", "no", "off"}:
                return False
        raise _fail(f"Parameter {name!r}: {value!r} ist kein Wahrheitswert.")
    if param_type == "int":
        if isinstance(value, bool):
            raise _fail(f"Parameter {name!r}: {value!r} ist keine ganze Zahl.")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError as exc:
                raise _fail(f"Parameter {name!r}: {value!r} ist keine ganze Zahl.") from exc
        raise _fail(f"Parameter {name!r}: {value!r} ist keine ganze Zahl.")
    if param_type == "float":
        if isinstance(value, bool):
            raise _fail(f"Parameter {name!r}: {value!r} ist keine Zahl.")
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip().replace(",", "."))
            except ValueError as exc:
                raise _fail(f"Parameter {name!r}: {value!r} ist keine Zahl.") from exc
        raise _fail(f"Parameter {name!r}: {value!r} ist keine Zahl.")
    if not isinstance(value, str):
        return str(value)
    return value


def coerce_params(specs: dict[str, ParamSpec], values: dict[str, Any] | None) -> dict[str, Any]:
    """Prueft Pflichtfelder und liefert die typisierten Parameter."""
    given = dict(values or {})
    unknown = set(given) - set(specs)
    if unknown:
        raise _fail(f"Unbekannte Parameter: {sorted(unknown)}.")
    result: dict[str, Any] = {}
    for name, spec in specs.items():
        raw = given.get(name)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if spec.required:
                raise _fail(f"Parameter {spec.title!r} ist erforderlich.")
            if spec.default is not None:
                result[name] = coerce_value(name, spec.type, spec.default)
            elif spec.type == "bool":
                result[name] = False
            else:
                result[name] = None
            continue
        result[name] = coerce_value(name, spec.type, raw)
    return result


def parse_columns(raw: object) -> list[str] | None:
    """Prueft ``COLUMNS``; Schluessel der Form ``std:subject`` oder ``custom:12``."""
    if raw is None:
        return None
    if not isinstance(raw, list | tuple) or not raw:
        raise _fail("COLUMNS muss eine nicht leere Liste sein.")
    columns: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not COLUMN_PATTERN.match(item.strip()):
            raise _fail(
                f"COLUMNS: {item!r} ist kein gueltiger Spaltenschluessel "
                "(erwartet z. B. 'std:subject' oder 'custom:Kampagne')."
            )
        columns.append(item.strip())
    return columns


def _check_kind(path: str, kind: str, value: object) -> None:
    if kind == "bool":
        if not isinstance(value, bool):
            raise _fail(f"{path}: {value!r} muss ein Wahrheitswert sein.")
        return
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _fail(f"{path}: {value!r} muss eine ganze Zahl sein.")
        return
    if kind == "float":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _fail(f"{path}: {value!r} muss eine Zahl sein.")
        return
    if kind == "str":
        if not isinstance(value, str) or not value.strip():
            raise _fail(f"{path}: erwartet wird ein nicht leerer Text.")
        return
    if kind == "field_ref":
        if isinstance(value, bool):
            raise _fail(f"{path}: erwartet wird eine Feld-ID oder ein Feldname.")
        if isinstance(value, int):
            if value <= 0:
                raise _fail(f"{path}: Feld-IDs muessen positiv sein.")
            return
        if isinstance(value, str) and value.strip():
            return
        raise _fail(f"{path}: erwartet wird eine Feld-ID oder ein Feldname.")
        return
    if kind == "int_list":
        if not isinstance(value, list | tuple) or not value:
            raise _fail(f"{path}: erwartet wird eine nicht leere Liste von IDs.")
        for item in value:
            if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
                raise _fail(f"{path}: {item!r} ist keine positive ID.")
        return
    if kind == "filter_list":
        if not isinstance(value, list | tuple) or not value:
            raise _fail(f"{path}: erwartet wird eine nicht leere Liste von Filtern.")
        for index, item in enumerate(value):
            validate_filter(item, path=f"{path}[{index}]")
        return
    raise _fail(f"{path}: unbekannte Feldart {kind!r}.")


def validate_filter(value: object, *, path: str = "filter") -> dict[str, Any]:
    """Prueft einen Filterbaum gegen die Feldtabelle der API."""
    if not isinstance(value, dict):
        raise _fail(f"{path}: erwartet wird ein dict, erhalten {type(value).__name__}.")
    filter_type = value.get("filterType")
    if not isinstance(filter_type, str):
        raise _fail(f"{path}: 'filterType' fehlt. {UNKNOWN_FIELD_HINT}")
    if filter_type not in FILTER_TYPE_FIELDS:
        raise _fail(f"{path}: unbekannter filterType {filter_type!r}. {UNKNOWN_FIELD_HINT}")
    allowed = FILTER_TYPE_FIELDS[filter_type]
    unknown = set(value) - set(allowed) - {"filterType", "inverted"}
    if unknown:
        raise _fail(f"{path}: unbekannte Felder fuer {filter_type!r}: {sorted(unknown)}.")
    if "inverted" in value and not isinstance(value["inverted"], bool):
        raise _fail(f"{path}: 'inverted' muss ein Wahrheitswert sein.")
    for field_name in REQUIRED_FIELDS.get(filter_type, ()):
        if value.get(field_name) is None:
            raise _fail(f"{path}: {filter_type!r} braucht das Feld {field_name!r}.")
    for field_name, kind in allowed.items():
        if field_name in value:
            _check_kind(f"{path}.{field_name}", kind, value[field_name])
            if field_name in ID_FIELDS:
                _check_positive_ids(f"{path}.{field_name}", kind, value[field_name])
    if filter_type == "metadataFieldDate" and not (value.get("dateMin") or value.get("dateMax")):
        raise _fail(f"{path}: 'metadataFieldDate' braucht dateMin oder dateMax.")
    if filter_type == "hasMetadataField" and not (
        value.get("customMetadataFieldID")
        or value.get("standardMetadataFieldID")
        or value.get("metadataFieldID")
    ):
        raise _fail(f"{path}: 'hasMetadataField' braucht eine Feld-ID.")
    return dict(value)


def _check_positive_ids(path: str, kind: str, value: object) -> None:
    if kind == "int":
        if isinstance(value, int) and not isinstance(value, bool) and value <= 0:
            raise _fail(f"{path}: IDs muessen positiv sein.")
    elif kind == "int_list":
        for item in value if isinstance(value, list | tuple) else []:
            if isinstance(item, int) and not isinstance(item, bool) and item <= 0:
                raise _fail(f"{path}: IDs muessen positiv sein.")


def normalize_result(value: object, *, max_rows: int) -> ScriptResult:
    """Prueft die Rueckgabe von ``query`` und begrenzt die Ergebnismenge."""
    if isinstance(value, ScriptResult):
        result = value
    elif isinstance(value, dict):
        result = ScriptResult(filter=validate_filter(value))
    elif isinstance(value, list | tuple):
        result = ScriptResult(ids=_normalize_ids(value, max_rows=max_rows))
    else:
        raise _fail(
            "query muss einen Filter (dict), eine Liste von IDs oder px.result(...) liefern, "
            f"erhalten: {type(value).__name__}."
        )
    if result.filter is not None:
        validate_filter(result.filter)
    if result.ids is not None:
        ids = _normalize_ids(result.ids, max_rows=max_rows)
        result = ScriptResult(
            filter=result.filter,
            ids=ids,
            columns=result.columns,
            note=result.note,
        )
    if result.columns is not None:
        parse_columns(list(result.columns))
    return result


def _normalize_ids(value: object, *, max_rows: int) -> list[int]:
    if not isinstance(value, list | tuple):
        raise _fail("Die ID-Liste muss eine Liste sein.")
    if not value:
        raise _fail("Die ID-Liste ist leer.")
    ids: list[int] = []
    seen: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise _fail(f"ID {item!r} ist keine positive ganze Zahl.")
        if item in seen:
            continue
        seen.add(item)
        ids.append(item)
    if len(ids) > max_rows:
        raise _fail(
            f"Die Ergebnismenge ({len(ids)}) ueberschreitet das Profillimit von {max_rows} Zeilen."
        )
    return ids


__all__ = [
    "COLUMN_PATTERN",
    "FILTER_TYPE_FIELDS",
    "ParamSpec",
    "ScriptResult",
    "coerce_params",
    "coerce_value",
    "normalize_result",
    "parse_columns",
    "parse_params",
    "validate_filter",
]
