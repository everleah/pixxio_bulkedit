"""Schreibpruefungen gegen selbst angelegte Test-Assets.

Alle Schreibziele stammen aus dem lokalen Ledger und muessen zusaetzlich in der
freigegebenen Collection liegen; ohne ``PXTEST_IS_DEV=true`` wird nichts geschrieben.
Einzelne fachliche Fehler brechen den Lauf nicht ab: jede Pruefung liefert ein
eigenes Ergebnis.
"""

from __future__ import annotations

import secrets
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pixxio_client import Client
from pixxio_client.exceptions import PIXXIOException
from pixxio_client.files import File
from pixxio_client.metadata import MetadataValueBuilder

from app.spike.client import FILES_PAGE_SIZE
from app.spike.discovery import (
    as_dict,
    as_plain,
    collection_filter,
    fetch_custom_fields,
    fetch_standard_fields,
    file_count,
)
from app.spike.errors import SpikeError, WriteNotAllowedError
from app.spike.fixtures import probe_file_name, write_test_png
from app.spike.guard import assert_deletion_allowed, assert_write_allowed
from app.spike.ledger import Ledger, LedgerEntry
from app.spike.settings import SpikeSettings

JOB_TIMEOUT_SECONDS = 180
POLL_INTERVAL_SECONDS = 1.0
PROBE_TEXT = "bulkedit-probe text"
PROBE_SUBJECT = "bulkedit-probe subject"
PROBE_KEYWORD = "bulkedit-probe-keyword"
INVALID_FIELD_ID = 1
STANDARD_CANDIDATES = 12


@dataclass(frozen=True)
class ProbeResult:
    """Ergebnis einer einzelnen Schreibpruefung."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class ProbeFields:
    """Fuer die Pruefungen ausgewaehlte Custom-Felder."""

    text_id: int
    text_name: str
    selection_id: int
    selection_name: str
    selection_option: str
    multiselection_id: int
    multiselection_name: str
    multiselection_options: tuple[str, ...]


def _option_names(field: dict[str, Any]) -> list[str]:
    options = field.get("selectionOptions") or []
    names: list[str] = []
    for option in options:
        data = as_dict(option) if not isinstance(option, dict) else option
        name = data.get("name")
        if name:
            names.append(str(name))
    return names


def select_probe_fields(custom_fields: list[dict[str, Any]]) -> ProbeFields:
    """Waehlt je einen Vertreter der benoetigten editTypes aus."""

    def first_custom(edit_type: str, *, require_options: bool = False) -> dict[str, Any] | None:
        for field in custom_fields:
            if field.get("editType") != edit_type:
                continue
            if require_options and not _option_names(field):
                continue
            return field
        return None

    text = first_custom("text")
    selection = first_custom("selection", require_options=True) or first_custom("selection")
    multiselection = first_custom("multiselection", require_options=True)
    missing = [
        label
        for label, field in (
            ("Textfeld", text),
            ("Einfachauswahl", selection),
            ("Mehrfachauswahl mit Optionen", multiselection),
        )
        if field is None
    ]
    if text is None or selection is None or multiselection is None:
        raise SpikeError(
            "Fuer die Schreibpruefungen fehlen passende Custom-Felder: " + ", ".join(missing)
        )

    selection_options = _option_names(selection)
    return ProbeFields(
        text_id=int(text["id"]),
        text_name=str(text.get("name")),
        selection_id=int(selection["id"]),
        selection_name=str(selection.get("name")),
        selection_option=selection_options[0],
        multiselection_id=int(multiselection["id"]),
        multiselection_name=str(multiselection.get("name")),
        multiselection_options=tuple(_option_names(multiselection)[:2]),
    )


def build_metadata_entries(
    fields: list[dict[str, Any]], entries: Sequence[tuple[str, int, Any]]
) -> list[dict[str, Any]]:
    """Baut metadataCustom-/metadataStandard-Eintraege ueber den Client-Builder.

    Die Feldliste stammt aus dem bereits geladenen Schema, damit kein zweiter
    Schemaabruf noetig ist. ``CustomMetadataBuilder`` funktioniert ab
    pixxio-client 0.4.4 (vorher scheiterte er am pageSize-Limit von 50).
    """
    builder = MetadataValueBuilder([SimpleNamespace(**field) for field in fields])
    for action, field_id, value in entries:
        if action == "remove":
            builder.remove(field_id)
        else:
            builder.append(action, field_id, value)  # pyright: ignore[reportArgumentType]
    return builder.build()


def fetch_snapshot(client: Client, file_id: int) -> dict[str, Any]:
    """Liest eine einzelne Datei inklusive Metadatenwerten."""
    return _first_file(as_dict(File(client).get(id=file_id)))


def _first_file(response: dict[str, Any]) -> dict[str, Any]:
    files = response.get("files")
    if isinstance(files, list) and files:
        return as_dict(files[0])
    single = response.get("file")
    if single is not None:
        return as_dict(single)
    return response


def metadata_value(snapshot: dict[str, Any], field_id: int) -> Any:
    metadata = as_dict(snapshot.get("metadataFields") or {})
    entry = metadata.get(str(field_id))
    if entry is None:
        return None
    return as_plain(as_dict(entry).get("value"))


def matches(observed: Any, expected: str) -> bool:
    """Toleranter Vergleich, weil die API Werte unterschiedlich zurueckgibt."""
    if observed is None:
        return False
    return expected in str(as_plain(observed))


def _job_details(response: dict[str, Any]) -> str:
    is_job = "isFinished" in response or "jobType" in response
    if not is_job:
        return f"kein Job (direkte Antwort, success={response.get('success')})"
    return (
        f"Job {response.get('id')} {response.get('jobType')} "
        f"success={response.get('success')} error={as_plain(response.get('error'))}"
    )


def _update(client: Client, targets: Sequence[int], payload: dict[str, Any]) -> dict[str, Any]:
    response = File(client).update_and_wait(
        ids=list(targets),
        timeout=JOB_TIMEOUT_SECONDS,
        poll_interval=POLL_INTERVAL_SECONDS,
        **payload,
    )
    return as_dict(response)


def fetch_collection_ids(
    client: Client, collection_id: int, *, include_archived: bool = False
) -> set[int]:
    files = File(client).iter_all(
        page_size=FILES_PAGE_SIZE,
        filter=collection_filter(collection_id, include_archived=include_archived),
        responseFields=["id"],
    )
    return {int(as_dict(item)["id"]) for item in files}


def resolve_upload_directory_id(client: Client, collection_id: int) -> int:
    page = as_dict(File(client).get(pageSize=1, filter=collection_filter(collection_id)))
    items = page.get("files") or []
    if not items:
        raise SpikeError(
            "Die Collection enthaelt keine Datei; ein Zielverzeichnis fuer Testdaten ist "
            "nicht bestimmbar."
        )
    directory = as_dict(as_dict(items[0]).get("directory") or {})
    directory_id = directory.get("id")
    if directory_id is None:
        raise SpikeError("Die Beispieldatei nennt kein Verzeichnis; Upload nicht moeglich.")
    return int(directory_id)


def create_fixtures(
    client: Client,
    settings: SpikeSettings,
    ledger: Ledger,
    count: int,
) -> list[LedgerEntry]:
    """Legt eigene Testdateien in der Testcollection an und protokolliert sie."""
    if not settings.is_dev:
        raise WriteNotAllowedError("Testdaten duerfen nur bei PXTEST_IS_DEV=true angelegt werden.")
    if count < 1:
        raise SpikeError("Es muss mindestens eine Testdatei angelegt werden.")

    directory_id = resolve_upload_directory_id(client, settings.collection_id)
    files = File(client)
    created: list[LedgerEntry] = []
    with tempfile.TemporaryDirectory() as raw_directory:
        for _ in range(count):
            name = probe_file_name()
            path = Path(raw_directory) / name
            # Eindeutiger Inhalt: das Testsystem erkennt identische Dateien als Duplikat.
            write_test_png(path, seed=secrets.randbelow(1 << 16))
            result = as_dict(
                files.upload_and_wait(
                    str(path),
                    timeout=JOB_TIMEOUT_SECONDS,
                    poll_interval=POLL_INTERVAL_SECONDS,
                    collectionIDs=[settings.collection_id],
                    directoryID=directory_id,
                    # Ohne Endung: die API haengt die tatsaechliche Endung selbst an.
                    fileName=Path(name).stem,
                )
            )
            asset_id = (
                result.get("asset_id")
                or result.get("fileID")
                or result.get("fileId")
                or result.get("id")
            )
            if asset_id is None:
                raise SpikeError(
                    f"Upload von {name} lieferte keine Asset-ID; Antwortfelder: {sorted(result)}"
                )
            if result.get("isDuplicate") or result.get("duplicateInfo"):
                raise SpikeError(
                    f"Upload von {name} wurde als Duplikat erkannt (Asset {asset_id}); "
                    "es wird nichts beschrieben."
                )
            entry = LedgerEntry(
                asset_id=int(asset_id),
                file_name=name,
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            try:
                ledger.add(entry)
            except Exception:
                files.delete(ids=[entry.asset_id])
                raise
            created.append(entry)
    return created


def _id_list(value: Any) -> list[int]:
    return [int(item) for item in (as_plain(value) or []) if isinstance(item, int | str)]


def cleanup_fixtures(client: Client, settings: SpikeSettings, ledger: Ledger) -> list[int]:
    """Loescht die Assets aus dem Ledger und entfernt sie danach aus dem Ledger."""
    if not settings.is_dev:
        raise WriteNotAllowedError("Testdaten duerfen nur bei PXTEST_IS_DEV=true geloescht werden.")
    targets = sorted(ledger.ids())
    if not targets:
        return []
    assert_deletion_allowed(
        is_dev=settings.is_dev,
        ledger_ids=set(targets),
        targets=targets,
    )
    response = as_dict(
        File(client).delete_and_wait(
            ids=targets,
            timeout=JOB_TIMEOUT_SECONDS,
            poll_interval=POLL_INTERVAL_SECONDS,
        )
    )
    job_data = as_dict(response.get("finishedJobData") or {})
    if job_data:
        # Mehrere IDs: die API meldet die IDs im abgeschlossenen Job.
        deleted = _id_list(job_data.get("deletedFileIDs"))
        still_present = sorted(_id_list(job_data.get("notDeletedFileIDs")))
    else:
        # Eine ID: die API meldet nur success; Loeschung ueber die Collection pruefen.
        remaining = set(targets) & fetch_collection_ids(
            client, settings.collection_id, include_archived=True
        )
        deleted = [asset_id for asset_id in targets if asset_id not in remaining]
        still_present = sorted(remaining)

    for asset_id in deleted:
        ledger.remove(asset_id)
    if still_present:
        raise SpikeError(
            f"Noch vorhandene Assets bleiben im Ledger: {still_present}; "
            f"Antwortfelder: {sorted(response)}"
        )
    return deleted


def _check_multi_id_text(
    client: Client,
    targets: Sequence[int],
    chosen: ProbeFields,
    custom_fields: list[dict[str, Any]],
) -> ProbeResult:
    payload = {
        "metadataCustom": build_metadata_entries(
            custom_fields, [("replace", chosen.text_id, PROBE_TEXT)]
        )
    }
    before = fetch_snapshot(client, targets[0])
    response = _update(client, targets, payload)
    values = [
        metadata_value(fetch_snapshot(client, file_id), chosen.text_id) for file_id in targets
    ]
    after = fetch_snapshot(client, targets[0])
    return ProbeResult(
        name=f"Identischer Payload auf {len(targets)} IDs ({chosen.text_name})",
        ok=all(matches(value, PROBE_TEXT) for value in values),
        detail=(
            f"{_job_details(response)}; Werte {values}; "
            f"modifyDate {before.get('modifyDate')} -> {after.get('modifyDate')}"
        ),
    )


def _check_single_id_text(
    client: Client, target: int, chosen: ProbeFields, custom_fields: list[dict[str, Any]]
) -> ProbeResult:
    payload = {
        "metadataCustom": build_metadata_entries(
            custom_fields, [("replace", chosen.text_id, PROBE_TEXT)]
        )
    }
    response = _update(client, [target], payload)
    observed = metadata_value(fetch_snapshot(client, target), chosen.text_id)
    return ProbeResult(
        name="Einzelne ID: synchrone Antwort ohne Job?",
        ok=matches(observed, PROBE_TEXT),
        detail=f"{_job_details(response)}; Wert {observed!r}",
    )


def _check_selection(
    client: Client, target: int, chosen: ProbeFields, custom_fields: list[dict[str, Any]]
) -> ProbeResult:
    payload = {
        "metadataCustom": build_metadata_entries(
            custom_fields, [("replace", chosen.selection_id, chosen.selection_option)]
        )
    }
    response = _update(client, [target], payload)
    observed = metadata_value(fetch_snapshot(client, target), chosen.selection_id)
    return ProbeResult(
        name=f"Einfachauswahl setzen ({chosen.selection_name})",
        ok=matches(observed, chosen.selection_option),
        detail=f"{_job_details(response)}; Wert {observed!r}",
    )


def _check_multiselection(
    client: Client, target: int, chosen: ProbeFields, custom_fields: list[dict[str, Any]]
) -> ProbeResult:
    options = list(chosen.multiselection_options)
    payload = {
        "metadataCustom": build_metadata_entries(
            custom_fields, [("replace", chosen.multiselection_id, options)]
        )
    }
    response = _update(client, [target], payload)
    observed = metadata_value(fetch_snapshot(client, target), chosen.multiselection_id)
    return ProbeResult(
        name=f"Mehrfachauswahl setzen ({chosen.multiselection_name})",
        ok=bool(options) and all(matches(observed, option) for option in options),
        detail=(f"{_job_details(response)}; erwartet {options}, erhalten {observed!r}"),
    )


def _standard_candidates(
    standard_fields: list[dict[str, Any]], snapshot: dict[str, Any]
) -> list[dict[str, Any]]:
    """Kandidaten aus den im Asset aktiven Standardfeldern.

    Das Schema kennzeichnet keine Editierbarkeit. Sichtbar ist aber, welche
    Standardfelder das Asset ueberhaupt fuehrt; nur diese werden versucht.
    """
    metadata = as_dict(snapshot.get("metadataFields") or {})
    active_ids = {
        int(field_id)
        for field_id, raw in metadata.items()
        if as_dict(raw).get("type") != "custom" and str(field_id).isdigit()
    }
    candidates = [
        field
        for field in standard_fields
        if int(field["id"]) in active_ids and field.get("editType") in ("text", "number")
    ]
    if candidates:
        return candidates[:STANDARD_CANDIDATES]
    return [field for field in standard_fields if field.get("editType") in ("text", "number")][
        :STANDARD_CANDIDATES
    ]


def _check_standard_metadata(
    client: Client, target: int, standard_fields: list[dict[str, Any]]
) -> ProbeResult:
    """Sucht das erste schreibbare Standardfeld.

    Nicht alle Standardfelder sind editierbar; die API meldet sonst
    "The standard metadata field does not exist or is not editable."
    """
    candidates = _standard_candidates(standard_fields, fetch_snapshot(client, target))
    errors: list[str] = []
    for field in candidates:
        field_id = int(field["id"])
        value: str | int = 42 if field.get("editType") == "number" else "bulkedit-probe"
        try:
            response = _update(
                client,
                [target],
                {
                    "metadataStandard": build_metadata_entries(
                        standard_fields, [("replace", field_id, value)]
                    )
                },
            )
        except PIXXIOException as exc:
            errors.append(f"{field.get('name')}: {exc}")
            continue
        observed = metadata_value(fetch_snapshot(client, target), field_id)
        return ProbeResult(
            name="Standard-Metadaten schreiben",
            ok=matches(observed, str(value)),
            detail=(
                f"erstes editierbares Feld {field.get('name')} ({field_id}, "
                f"{field.get('editType')}): {_job_details(response)}; Wert {observed!r}; "
                f"vorher {len(errors)} nicht editierbar"
            ),
        )
    return ProbeResult(
        name="Standard-Metadaten schreiben",
        ok=False,
        detail=f"kein editierbares Standardfeld in {len(candidates)} Kandidaten: "
        + " | ".join(errors[:3]),
    )


def _check_remove_metadata(
    client: Client, target: int, chosen: ProbeFields, custom_fields: list[dict[str, Any]]
) -> ProbeResult:
    payload = {
        "metadataCustom": build_metadata_entries(custom_fields, [("remove", chosen.text_id, None)])
    }
    response = _update(client, [target], payload)
    observed = metadata_value(fetch_snapshot(client, target), chosen.text_id)
    return ProbeResult(
        name=f"Metadatenwert entfernen ({chosen.text_name})",
        ok=observed in (None, ""),
        detail=f"{_job_details(response)}; Wert {observed!r}",
    )


def _check_standard_attribute(client: Client, target: int) -> ProbeResult:
    response_set = _update(client, [target], {"subject": PROBE_SUBJECT})
    set_subject = fetch_snapshot(client, target).get("subject")
    response_clear = _update(client, [target], {"truncateSubject": True})
    cleared_subject = fetch_snapshot(client, target).get("subject")
    return ProbeResult(
        name="Standardattribut setzen und leeren (subject/truncateSubject)",
        ok=set_subject == PROBE_SUBJECT and cleared_subject in (None, ""),
        detail=(
            f"gesetzt {set_subject!r} ({_job_details(response_set)}), "
            f"geleert {cleared_subject!r} ({_job_details(response_clear)})"
        ),
    )


def _check_keywords(client: Client, target: int) -> ProbeResult:
    _update(client, [target], {"keywordsToAdd": [PROBE_KEYWORD]})
    with_keyword = as_plain(fetch_snapshot(client, target).get("keywords"))
    response = _update(client, [target], {"keywordsToRemove": [PROBE_KEYWORD]})
    without_keyword = as_plain(fetch_snapshot(client, target).get("keywords"))
    return ProbeResult(
        name="Keywords hinzufuegen und entfernen",
        ok=PROBE_KEYWORD in str(with_keyword) and PROBE_KEYWORD not in str(without_keyword),
        detail=(f"mit Keyword {with_keyword}, danach {without_keyword}; {_job_details(response)}"),
    )


def _check_invalid_field(client: Client, target: int) -> ProbeResult:
    try:
        response = _update(
            client,
            [target],
            {"metadataCustom": [{"action": "replace", "id": INVALID_FIELD_ID, "value": "x"}]},
        )
    except PIXXIOException as exc:
        return ProbeResult(
            name="Fehlerdetails bei unbekanntem Feld",
            ok=True,
            detail=f"{type(exc).__name__}: {exc}",
        )
    return ProbeResult(
        name="Fehlerdetails bei unbekanntem Feld",
        ok=False,
        detail=f"kein Fehler gemeldet: {_job_details(response)}",
    )


def run_write_checks(
    client: Client,
    settings: SpikeSettings,
    ledger: Ledger,
) -> list[ProbeResult]:
    """Fuehrt die Schreibpruefungen aus und liefert je Pruefung ein Ergebnis."""
    targets = sorted(ledger.ids())
    if not targets:
        raise SpikeError(
            "Das Ledger ist leer. Zuerst "
            "'python -m app.spike fixtures create --count 2' ausfuehren."
        )
    members = fetch_collection_ids(client, settings.collection_id)
    assert_write_allowed(
        is_dev=settings.is_dev,
        ledger_ids=set(targets),
        collection_ids=members,
        targets=targets,
    )

    custom_fields = fetch_custom_fields(client)
    standard_fields = fetch_standard_fields(client)
    chosen = select_probe_fields(custom_fields)
    anchor = targets[0]
    pair = targets[:2]

    checks: list[tuple[str, Callable[[], ProbeResult]]] = [
        (
            f"Identischer Payload auf {len(pair)} IDs ({chosen.text_name})",
            lambda: _check_multi_id_text(client, pair, chosen, custom_fields),
        ),
        (
            "Einzelne ID: synchrone Antwort ohne Job?",
            lambda: _check_single_id_text(client, anchor, chosen, custom_fields),
        ),
        (
            f"Einfachauswahl setzen ({chosen.selection_name})",
            lambda: _check_selection(client, anchor, chosen, custom_fields),
        ),
        (
            f"Mehrfachauswahl setzen ({chosen.multiselection_name})",
            lambda: _check_multiselection(client, anchor, chosen, custom_fields),
        ),
        (
            "Standard-Metadaten schreiben",
            lambda: _check_standard_metadata(client, anchor, standard_fields),
        ),
        (
            f"Metadatenwert entfernen ({chosen.text_name})",
            lambda: _check_remove_metadata(client, anchor, chosen, custom_fields),
        ),
        (
            "Standardattribut setzen und leeren (subject/truncateSubject)",
            lambda: _check_standard_attribute(client, anchor),
        ),
        ("Keywords hinzufuegen und entfernen", lambda: _check_keywords(client, anchor)),
        ("Fehlerdetails bei unbekanntem Feld", lambda: _check_invalid_field(client, anchor)),
    ]

    results: list[ProbeResult] = []
    for name, check in checks:
        try:
            results.append(check())
        except PIXXIOException as exc:
            results.append(ProbeResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}"))
    return results


def count_collection_files(client: Client, collection_id: int) -> int:
    return file_count(
        as_dict(File(client).get(pageSize=1, filter=collection_filter(collection_id)))
    )
