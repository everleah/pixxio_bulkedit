"""Kommandozeile der Phase-1-Pruefungen.

Lesezugriffe sind immer erlaubt. Schreibzugriffe (``fixtures``, ``probe``) laufen
ausschliesslich auf Assets aus dem lokalen Ledger und nur bei ``PXTEST_IS_DEV=true``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from pixxio_client.exceptions import PIXXIOException
from pydantic import ValidationError

from app.spike.client import FILES_PAGE_SIZE, METADATA_PAGE_SIZE, build_client
from app.spike.discovery import (
    fetch_collection,
    fetch_collection_list,
    fetch_custom_fields,
    fetch_files_page,
    fetch_pages,
    fetch_standard_fields,
    fetch_user,
    file_count,
    summarize_collection,
    summarize_collections,
    summarize_files,
    summarize_schema,
    summarize_user,
)
from app.spike.errors import SpikeError
from app.spike.ledger import Ledger
from app.spike.probe import cleanup_fixtures, create_fixtures, run_write_checks
from app.spike.settings import SpikeSettings, get_spike_settings

DEFAULT_FILE_LIMIT = 5
DEFAULT_FIXTURE_COUNT = 2


def _load_settings() -> SpikeSettings:
    try:
        return get_spike_settings()
    except ValidationError as exc:
        details = "; ".join(str(error["msg"]) for error in exc.errors())
        raise SpikeError(
            "PXTEST_HOST, PXTEST_API_KEY und PXTEST_COLLECTION_ID muessen gesetzt sein "
            f"({details})."
        ) from exc


def _ledger(settings: SpikeSettings) -> Ledger:
    return Ledger(settings.ledger_path)


def _emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for line in lines:
        print(line)


def _seconds(started: float) -> str:
    return f"{time.perf_counter() - started:.2f}s"


def command_whoami(args: argparse.Namespace) -> int:
    client = build_client(_load_settings())
    user = summarize_user(fetch_user(client))
    lines = [f"API-User: {user['displayName']} (id {user['id']})"]
    _emit({"user": user}, args.json, lines)
    return 0


def _collection_id(args: argparse.Namespace, settings: SpikeSettings) -> int:
    configured = getattr(args, "collection_id", None)
    return int(configured) if configured else settings.collection_id


def command_collection(args: argparse.Namespace) -> int:
    settings = _load_settings()
    client = build_client(settings)
    collection_id = _collection_id(args, settings)
    collection = summarize_collection(fetch_collection(client, collection_id))
    quantity = file_count(fetch_files_page(client, collection_id, 1))
    lines = [
        f"Host: {settings.host}",
        f"Collection: {collection['name']} (id {collection['id']})",
        f"isDynamic: {collection['isDynamic']} | filesQuantity: {collection['filesQuantity']}",
        f"Treffer laut Dateiliste: {quantity}",
        f"pageSize-Maximum: files {FILES_PAGE_SIZE}, customMetadata {METADATA_PAGE_SIZE}",
    ]
    payload = {
        "host": settings.host,
        "collection": collection,
        "quantity": quantity,
    }
    _emit(payload, args.json, lines)
    return 0


def command_schema(args: argparse.Namespace) -> int:
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
    return 0


def command_files(args: argparse.Namespace) -> int:
    settings = _load_settings()
    client = build_client(settings)
    collection_id = _collection_id(args, settings)
    page = fetch_files_page(client, collection_id, args.limit)
    rows = summarize_files(page)
    lines = [f"{file_count(page)} Treffer, gezeigt: {len(rows)}"]
    for row in rows:
        lines.append(
            f"- {row['id']} {row['fileName']} | modifyDate {row['modifyDate']} "
            f"| subject {row['subject']!r} | rating {row['rating']!r}"
        )
        if row["customFilled"]:
            lines.append(f"    gefuellte Custom-Felder: {row['customFilled']}")
    payload = {"collection_id": collection_id, "files": rows}
    _emit(payload, args.json, lines)
    return 0


def command_report(args: argparse.Namespace) -> int:
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
        "files_page_size_max": FILES_PAGE_SIZE,
        "metadata_page_size_max": METADATA_PAGE_SIZE,
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
    return 0


def command_collections(args: argparse.Namespace) -> int:
    client = build_client(_load_settings())
    summary = summarize_collections(fetch_collection_list(client))
    lines = [
        f"Collections: {summary['count']} ({summary['dynamic_count']} dynamisch, "
        f"{summary['count'] - summary['dynamic_count']} statisch)"
    ]
    for row in summary["collections"]:
        kind = "dynamisch" if row.get("isDynamic") else "statisch"
        lines.append(
            f"- {row['id']} {row['name']} | {kind} | filesQuantity {row.get('filesQuantity')}"
        )
    _emit(summary, args.json, lines)
    return 0


def command_paging(args: argparse.Namespace) -> int:
    settings = _load_settings()
    client = build_client(settings)
    collection_id = _collection_id(args, settings)
    pages = fetch_pages(client, collection_id, args.page_size)
    total = sum(page["count"] for page in pages)
    quantity = pages[0]["quantity"] if pages else None
    lines = [
        f"pageSize {args.page_size}: {len(pages)} Seite(n), {total} Eintraege, quantity {quantity}"
    ]
    for page in pages:
        lines.append(
            f"- Seite {page['page']}: {page['count']} Eintraege | "
            f"quantity {page['quantity']} | cursor {page['has_cursor']}"
        )
    payload = {"page_size": args.page_size, "quantity": quantity, "pages": pages}
    _emit(payload, args.json, lines)
    return 0


def command_status(args: argparse.Namespace) -> int:
    settings = _load_settings()
    ledger = _ledger(settings)
    entries = ledger.load()
    lines = [
        f"Ledger: {ledger.path}",
        f"Eigene Test-Assets: {len(entries)}",
    ]
    for entry in entries:
        lines.append(f"- {entry.asset_id} {entry.file_name} ({entry.created_at})")
    payload = {"ledger": str(ledger.path), "entries": [asdict(entry) for entry in entries]}
    _emit(payload, args.json, lines)
    return 0


def command_fixtures_create(args: argparse.Namespace) -> int:
    settings = _load_settings()
    client = build_client(settings)
    entries = create_fixtures(client, settings, _ledger(settings), args.count)
    lines = [f"Angelegt: {len(entries)} Testdateien"]
    for entry in entries:
        lines.append(f"- {entry.asset_id} {entry.file_name}")
    payload = {"created": [asdict(entry) for entry in entries]}
    _emit(payload, args.json, lines)
    return 0


def command_fixtures_delete(args: argparse.Namespace) -> int:
    settings = _load_settings()
    client = build_client(settings)
    deleted = cleanup_fixtures(client, settings, _ledger(settings))
    if not deleted:
        lines = ["Keine eigenen Test-Assets im Ledger."]
    else:
        lines = [f"Geloescht: {deleted}"]
    _emit({"deleted": deleted}, args.json, lines)
    return 0


def command_probe(args: argparse.Namespace) -> int:
    settings = _load_settings()
    client = build_client(settings)
    results = run_write_checks(client, settings, _ledger(settings))
    failures = [result for result in results if not result.ok]
    lines = [f"Schreibpruefungen: {len(results) - len(failures)}/{len(results)} ohne Abweichung"]
    for result in results:
        status = "OK" if result.ok else "ABWEICHUNG"
        lines.append(f"- [{status}] {result.name}: {result.detail}")
    _emit({"results": [asdict(result) for result in results]}, args.json, lines)
    return 0 if not failures else 1


def _json_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.spike",
        description="Phase-1-Pruefungen gegen ein pixx.io-Testsystem",
    )
    json_parent = _json_parent()
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str, handler: Any) -> argparse.ArgumentParser:
        subparser = subparsers.add_parser(name, help=help_text, parents=[json_parent])
        subparser.set_defaults(handler=handler)
        return subparser

    add("whoami", "API-Benutzer des Keys anzeigen", command_whoami)
    collection_parser = add("collection", "Collection und Trefferzahl anzeigen", command_collection)
    collection_parser.add_argument("--collection-id", type=int, default=None)
    add("collections", "Alle Collections mit Typ und Anzahl anzeigen", command_collections)
    add("schema", "Metadatenfelder und editTypes anzeigen", command_schema)
    files_parser = add("files", "Beispieldateien mit Werten anzeigen", command_files)
    files_parser.add_argument("--collection-id", type=int, default=None)
    files_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_FILE_LIMIT,
        help=f"Anzahl Beispieldateien (maximal {FILES_PAGE_SIZE})",
    )
    add("report", "Alle Lesepruefungen mit Laufzeiten", command_report)
    paging_parser = add("paging", "Seitenweises Laden der Collection pruefen", command_paging)
    paging_parser.add_argument("--collection-id", type=int, default=None)
    paging_parser.add_argument("--page-size", type=int, default=3)
    add("status", "Ledger der eigenen Test-Assets anzeigen", command_status)
    add("probe", "Schreibpruefungen auf eigenen Test-Assets ausfuehren", command_probe)

    fixtures_parser = subparsers.add_parser(
        "fixtures", help="Eigene Testdateien anlegen und entfernen"
    )
    fixture_commands = fixtures_parser.add_subparsers(dest="fixture_command", required=True)
    create_parser = fixture_commands.add_parser(
        "create", help="Testdateien anlegen", parents=[json_parent]
    )
    create_parser.add_argument("--count", type=int, default=DEFAULT_FIXTURE_COUNT)
    create_parser.set_defaults(handler=command_fixtures_create)
    delete_parser = fixture_commands.add_parser(
        "delete", help="Alle Assets aus dem Ledger loeschen", parents=[json_parent]
    )
    delete_parser.set_defaults(handler=command_fixtures_delete)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outcome = args.handler(args)
    except SpikeError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except PIXXIOException as exc:
        print(f"API-Fehler: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return int(outcome or 0)
