"""Client-Aufbau und Grenzen des pixx.io-Testsystems."""

from __future__ import annotations

from pixxio_client import Client

from app.spike.settings import SpikeSettings

# Die files-API akzeptiert bis zu 500 Eintraege pro Seite; darueber antwortet sie mit
# "pageSize maximum requirement of parameter value not met".
FILES_PAGE_SIZE = 500

# Die customMetadata-API ist auf 50 begrenzt; 100 (Client-Default) wird abgelehnt.
# standardMetadata akzeptiert gar kein pageSize (nicht gepaged).
METADATA_PAGE_SIZE = 50

# Der Client wiederholt GET/PUT/DELETE bei 429/503, POST nie. Fuer Lesezugriffe ist
# eine Wiederholung unkritisch.
READ_RETRIES = 1


def build_client(settings: SpikeSettings) -> Client:
    return Client.create_client(
        settings.api_key.get_secret_value(),
        settings.host,
        max_retries=READ_RETRIES,
    )
