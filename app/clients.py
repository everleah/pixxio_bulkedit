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
        self._lock = threading.RLock()

    def client_for(self, profile: Profile) -> Client:
        if profile.id is None:
            raise ValueError("Profil ohne ID kann keinen Client liefern.")
        with self._lock:
            client = self._clients.get(profile.id)
            if client is None:
                api_key = self._secret_box.decrypt(profile.api_key_enc)
                client = self._builder(api_key, profile.host, profile.max_retries)
                self._clients[profile.id] = client
            return client

    def invalidate(self, profile_id: int) -> None:
        with self._lock:
            self._clients.pop(profile_id, None)

    def clear(self) -> None:
        with self._lock:
            self._clients.clear()

    def cached_profile_ids(self) -> list[int]:
        with self._lock:
            return sorted(self._clients)
