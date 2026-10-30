"""ClientFactory: pixx.io-Client je Profil, mit Cache und Invalidierung.

Der API-Key wird ausschliesslich hier entschluesselt und verlaesst den Server nicht.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pixxio_client import Client
from pixxio_client.users import User

from app.crypto import SecretBox
from app.models import Profile

ClientBuilder = Callable[[str, str, int], Client]


def response_mapping(value: object) -> dict[str, Any]:
    """Wandelt Client-Antworten (Dict oder ResponseData) in ein Dict."""
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, dict):
            return dict(result)
    if isinstance(value, dict):
        return dict(value)
    return {}


def plain(value: object) -> Any:
    """Wandelt Client-Antworten vollstaendig in einfache Python-Werte."""
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return plain(to_dict())
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def current_user_name(client: Client) -> str | None:
    """Liest den Anzeigenamen des API-Benutzers fuer den Verbindungstest."""
    response = response_mapping(User(client).get_current())
    name = response_mapping(response.get("user")).get("displayName")
    return str(name) if name else None


def _default_builder(api_key: str, host: str, max_retries: int) -> Client:
    return Client.create_client(api_key, host, max_retries=max_retries)


class ClientFactory:
    """Haelt je Profil einen Client und verwirft ihn bei Aenderungen."""

    def __init__(self, secret_box: SecretBox, builder: ClientBuilder = _default_builder) -> None:
        self._secret_box = secret_box
        self._builder = builder
        self._clients: dict[int, Client] = {}
        self._writers: dict[int, Client] = {}
        self._lock = threading.RLock()

    def client_for(self, profile: Profile) -> Client:
        if profile.id is None:
            raise ValueError("Profil ohne ID kann keinen Client liefern.")
        with self._lock:
            client = self._clients.get(profile.id)
            if client is None:
                client = self._build(profile, profile.max_retries)
                self._clients[profile.id] = client
            return client

    def writer_client_for(self, profile: Profile) -> Client:
        """Client ohne automatische Wiederholungen fuer Schreibzugriffe.

        Der Writer sendet nichts blind erneut: unklare Ergebnisse werden
        zurueckgelesen und als unklar ausgewiesen.
        """
        if profile.id is None:
            raise ValueError("Profil ohne ID kann keinen Client liefern.")
        with self._lock:
            client = self._writers.get(profile.id)
            if client is None:
                client = self._build(profile, 0)
                self._writers[profile.id] = client
            return client

    def _build(self, profile: Profile, max_retries: int) -> Client:
        api_key = self._secret_box.decrypt(profile.api_key_enc)
        return self._builder(api_key, profile.host, max_retries)

    def invalidate(self, profile_id: int) -> None:
        with self._lock:
            self._clients.pop(profile_id, None)
            self._writers.pop(profile_id, None)

    def clear(self) -> None:
        with self._lock:
            self._clients.clear()
            self._writers.clear()

    def cached_profile_ids(self) -> list[int]:
        with self._lock:
            return sorted(set(self._clients) | set(self._writers))
