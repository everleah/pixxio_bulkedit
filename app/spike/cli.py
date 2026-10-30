"""Kommandozeile der Phase-1-Pruefungen.

Ausschliesslich lesend: es werden keine Dateien veraendert, angelegt oder geloescht.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from typing import Any

from pixxio_client.exceptions import PIXXIOException
from pydantic import ValidationError

from app.spike.client import PAGE_SIZE, build_client
from app.spike.discovery import (
    fetch_collection,
    fetch_custom_fields,
    fetch_files_page,
    fetch_standard_fields,
    fetch_user,
    file_count,
    summarize_collection,
    summarize_files,
    summarize_schema,
    summarize_user,
)
from app.spike.settings import SpikeSettings, get_spike_settings

DEFAULT_FILE_LIMIT = 5


class SpikeError(Exception):
    """Fachlicher Abbruch einer Spikepruefung."""


def _load_settings() -> SpikeSettings:
    try:
        return get_spike_settings()
    except ValidationError as exc:
        details = "; ".join(str(error["msg"]) for error in exc.errors())
        raise SpikeError(
            "PXTEST_HOST, PXTEST_API_KEY und PXTEST_COLLECTION_ID muessen gesetzt sein "
            f"({details})."
        ) from exc


def _emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for line in lines:
        print(line)


def _seconds(started: float) -> str:
    return f"{time.perf_counter() - started:.2f}s"


def command_whoami(args: argparse.Namespace) -> None:
    client = build_client(_load_settings())
    user = summarize_user(fetch_user(client))
    lines = [f"API-User: {user['displayName']} (id {user['id']})"]
    _emit({"user": user}, args.json, lines)


def command_collection(args: argparse.Namespace) -> None:
    settings = _load_settings()
    client = build_client(settings)
    collection = summarize_collection(fetch_collection(client, settings.collection_id))
    quantity = file_count(fetch_files_page(client, settings.collection_id, 1))
    lines = [
        f"Host: {settings.host}",
        f"Collection: {collection['name']} (id {collection['id']})",
        f"isDynamic: {collection['isDynamic']} | filesQuantity: {collection['filesQuantity']}",
        f"Treffer laut Dateiliste: {quantity} | pageSize-Maximum: {PAGE_SIZE}",
    ]
    payload = {"host": settings.host, "collection": collection, "quantity": quantity}
    _emit(payload, args.json, lines)


def command_schema(args: argparse.Namespace) -> None:
    client = build_client(_load_settings())
    custom_fields = fetch_custom_fields(client)
    standard_fields = fetch_standard_fields(client)
    schema = summarize_schema(custom_fields, standard_fields)
    lines = [
        f"Custom-Metadaten: {schema['custom']['count']} Felder "
        f"({schema['custom']['with_selection_options']} mit Auswahloptionen)",
        f"  editTypes: {schema['custom']['edit_types']}",
        f"Standard-Metadaten: {schema['standard']['count']} Felder",
        f"  editTypes: {schema['standard']['edit_types']}",
    ]
    payload = {"schema": schema, "custom_fields": custom_fields}
    _emit(payload, args.json, lines)


def command_files(args: argparse.Namespace) -> None:
    settings = _load_settings()
    client = build_client(settings)
    page = fetch_files_page(client, settings.collection_id, args.limit)
    rows = summarize_files(page)
    lines = [f"{file_count(page)} Treffer, gezeigt: {len(rows)}"]
    for row in rows:
        lines.append(
            f"- {row['id']} {row['fileName']} | modifyDate {row['modifyDate']} "
            f"| subject {row['subject']!r} | rating {row['rating']!r}"
        )
        if row["customFilled"]:
            lines.append(f"    gefuellte Custom-Felder: {row['customFilled']}")
    payload = {"collection_id": settings.collection_id, "files": rows}
    _emit(payload, args.json, lines)


def command_report(args: argparse.Namespace) -> None:
    settings = _load_settings()
    client = build_client(settings)
    lines = [
        f"Test-System: {settings.host} | is_dev={settings.is_dev} "
        f"| Collection {settings.collection_id}",
    ]
    payload: dict[str, Any] = {
        "host": settings.host,
        "collection_id": settings.collection_id,
        "is_dev": settings.is_dev,
        "page_size_max": PAGE_SIZE,
    }

    started = time.perf_counter()
    user = summarize_user(fetch_user(client))
    lines.append(f"[{_seconds(started)}] API-User: {user['displayName']} (id {user['id']})")
    payload["user"] = user

    started = time.perf_counter()
    collection = summarize_collection(fetch_collection(client, settings.collection_id))
    page = fetch_files_page(client, settings.collection_id, DEFAULT_FILE_LIMIT)
    lines.append(
        f"[{_seconds(started)}] Collection {collection['name']!r}: "
        f"{file_count(page)} Treffer, isDynamic={collection['isDynamic']}"
    )
    payload["collection"] = collection
    payload["quantity"] = file_count(page)

    started = time.perf_counter()
    custom_fields = fetch_custom_fields(client)
    standard_fields = fetch_standard_fields(client)
    schema = summarize_schema(custom_fields, standard_fields)
    lines.append(
        f"[{_seconds(started)}] Schema: {schema['custom']['count']} Custom-, "
        f"{schema['standard']['count']} Standard-Felder"
    )
    payload["schema"] = schema

    rows = summarize_files(page)
    lines.append(f"Beispieldateien: {len(rows)}")
    for row in rows:
        lines.append(
            f"- {row['id']} {row['fileName']} | modifyDate {row['modifyDate']} "
            f"| Custom-Felder {row['customFieldCount']}, gefuellt {len(row['customFilled'])}"
        )
    payload["files"] = rows
    _emit(payload, args.json, lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.spike",
        description="Phase-1-Pruefungen gegen ein pixx.io-Testsystem (nur lesend)",
    )
    parser.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("whoami", help="API-Benutzer des Keys anzeigen").set_defaults(
        handler=command_whoami
    )
    subparsers.add_parser("collection", help="Collection und Trefferzahl anzeigen").set_defaults(
        handler=command_collection
    )
    subparsers.add_parser("schema", help="Metadatenfelder und editTypes anzeigen").set_defaults(
        handler=command_schema
    )
    files_parser = subparsers.add_parser("files", help="Beispieldateien mit Werten anzeigen")
    files_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_FILE_LIMIT,
        help=f"Anzahl Beispieldateien (maximal {PAGE_SIZE})",
    )
    files_parser.set_defaults(handler=command_files)
    subparsers.add_parser("report", help="Alle Lesepruefungen mit Laufzeiten").set_defaults(
        handler=command_report
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except SpikeError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except PIXXIOException as exc:
        print(f"API-Fehler: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0
