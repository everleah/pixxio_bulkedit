"""Tests der API-Key-Verschluesselung."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.crypto import (
    SecretBox,
    UndecryptableApiKeyError,
    api_key_hint,
    assert_valid_master_key,
    generate_master_key,
)


def test_roundtrip_mit_gleichem_schluessel(master_key: str) -> None:
    box = SecretBox(master_key)
    token = box.encrypt("geheimer-api-key")
    assert token != b"geheimer-api-key"
    assert SecretBox(master_key).decrypt(token) == "geheimer-api-key"


def test_fremder_schluessel_kann_nicht_entschluesseln(master_key: str) -> None:
    token = SecretBox(master_key).encrypt("geheimer-api-key")
    with pytest.raises(UndecryptableApiKeyError):
        SecretBox(Fernet.generate_key().decode("ascii")).decrypt(token)


def test_hint_zeigt_nur_die_letzten_zeichen() -> None:
    assert api_key_hint("abcdefgh").endswith("efgh")
    assert "abcd" not in api_key_hint("abcdefgh")[:4]
    assert api_key_hint("ab") == "\N{BULLET}" * 4


def test_generierter_schluessel_ist_gueltig() -> None:
    assert_valid_master_key(generate_master_key())


def test_ungueltiger_schluessel_meldet_hinweis() -> None:
    with pytest.raises(ValueError, match="generate-master-key"):
        assert_valid_master_key("zu-kurz")
