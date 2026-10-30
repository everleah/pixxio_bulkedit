"""Client-Aufbau und Grenzen des pixx.io-Testsystems."""

from __future__ import annotations

from pixxio_client import Client

from app.spike.settings import SpikeSettings

# Die API akzeptiert hoechstens 50 Eintraege pro Seite; der Client-Default von 100
# wird mit "pageSize maximum requirement of parameter value not met" abgelehnt.
PAGE_SIZE = 50

# Der Client wiederholt GET/PUT/DELETE bei 429/503, POST nie. Fuer Lesezugriffe ist
# eine Wiederholung unkritisch.
READ_RETRIES = 1


def build_client(settings: SpikeSettings) -> Client:
    return Client.create_client(
        settings.api_key.get_secret_value(),
        settings.host,
        max_retries=READ_RETRIES,
    )
