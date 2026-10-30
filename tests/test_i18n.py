"""Tests der zweisprachigen Oberflächentexte."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.i18n import (
    DEFAULT_LOCALE,
    EN_TRANSLATIONS,
    LOCALES,
    describe_error,
    get_locale,
    missing_translations,
    normalize_locale,
    set_locale,
    t,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
UI_MODULES = sorted((APP_ROOT / "ui").glob("*.py")) + [APP_ROOT / "main.py"]
GERMAN_UMLAUTS = set("äöüÄÖÜ")


def used_keys() -> set[str]:
    """Sammelt alle mit ``t("...")`` verwendeten Quelltexte."""
    keys: set[str] = set()
    for path in UI_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "t"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
    return keys


@pytest.fixture(autouse=True)
def _reset_locale() -> Iterator[None]:
    previous = get_locale()
    yield
    set_locale(previous)


def test_jeder_text_ist_uebersetzt() -> None:
    keys = used_keys()
    assert keys, "es wurden keine Texte gefunden"
    assert missing_translations(keys) == []


def test_uebersetzungen_sind_gefuellt() -> None:
    empty = [key for key, value in EN_TRANSLATIONS.items() if not value.strip()]
    assert empty == []


def test_englische_texte_ohne_umlaute() -> None:
    offenders = [key for key, value in EN_TRANSLATIONS.items() if GERMAN_UMLAUTS & set(value)]
    assert offenders == []


def test_deutsch_ist_standard() -> None:
    set_locale(None)
    assert get_locale() == DEFAULT_LOCALE
    assert t("Arbeitsbestände") == "Arbeitsbestände"


def test_englische_ausgabe_und_platzhalter() -> None:
    set_locale("en")
    assert t("Arbeitsbestände") == "Workspaces"
    assert t("{count} Zeilen", count=4) == "4 rows"
    assert t("Benutzer '{name}' gespeichert.", name="admin") == "User 'admin' saved."


def test_unbekannter_text_faellt_auf_deutsch_zurueck() -> None:
    set_locale("en")
    assert t("Nicht katalogisiert") == "Nicht katalogisiert"
    assert t("Nicht katalogisiert {value}", value=1) == "Nicht katalogisiert 1"


def test_sprachwerte_werden_normalisiert() -> None:
    assert normalize_locale("EN") == "en"
    assert normalize_locale("de-CH") == "de"
    assert normalize_locale(None) == "de"
    assert set(LOCALES) == {"de", "en"}


def test_fehlertexte_werden_uebersetzt() -> None:
    class FakeError(Exception):
        translation_key = "{count} Änderungen verworfen."

    set_locale("de")
    assert describe_error(FakeError("Kaputt")) == "Kaputt"
    set_locale("en")
    assert describe_error(FakeError("Kaputt")) == "{count} changes discarded."
    assert describe_error(ValueError("plain")) == "plain"
