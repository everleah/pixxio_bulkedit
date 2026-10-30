"""Verschluesselung der pixx.io-API-Keys.

Der Master-Key kommt ausschliesslich aus ``BULKEDIT_MASTER_KEY``. Ohne gueltigen
Master-Key startet die Anwendung nicht; geht er verloren, muessen die API-Keys neu
erfasst werden, die uebrigen Daten bleiben nutzbar.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

HINT_VISIBLE_CHARS = 4
HINT_MASK = "\N{BULLET}" * 4
MASTER_KEY_MIN_CHARS = 32


class UndecryptableApiKeyError(Exception):
    """Der gespeicherte API-Key passt nicht zum aktuellen Master-Key."""


def generate_master_key() -> str:
    """Erzeugt einen neuen, fuer Fernet gueltigen Master-Key."""
    return Fernet.generate_key().decode("ascii")


def assert_valid_master_key(master_key: str) -> None:
    """Wirft ``ValueError``, wenn der Schluessel kein gueltiger Fernet-Key ist."""
    if len(master_key) < MASTER_KEY_MIN_CHARS:
        raise ValueError(
            "BULKEDIT_MASTER_KEY muss ein Fernet-Key sein "
            f"(mindestens {MASTER_KEY_MIN_CHARS} Zeichen, erzeugbar ueber "
            "'python -m app generate-master-key')"
        )
    try:
        Fernet(master_key.encode("ascii"))
    except (UnicodeEncodeError, TypeError, ValueError) as exc:
        raise ValueError(
            "BULKEDIT_MASTER_KEY ist kein gueltiger Fernet-Key "
            "(erzeugbar ueber 'python -m app generate-master-key')"
        ) from exc


def api_key_hint(api_key: str) -> str:
    """Anzeigeform eines API-Keys, z. B. ``****abcd``."""
    visible = api_key[-HINT_VISIBLE_CHARS:] if len(api_key) >= HINT_VISIBLE_CHARS else ""
    return f"{HINT_MASK}{visible}"


class SecretBox:
    """Ver- und entschluesselt API-Keys mit dem Master-Key."""

    def __init__(self, master_key: str) -> None:
        assert_valid_master_key(master_key)
        self._fernet = Fernet(master_key.encode("ascii"))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:
            raise UndecryptableApiKeyError(
                "API-Key kann mit dem aktuellen Master-Key nicht entschluesselt werden"
            ) from exc

    @classmethod
    def from_master_key(cls, master_key: SecretStr) -> SecretBox:
        return cls(master_key.get_secret_value())
