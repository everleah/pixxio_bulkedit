"""Import-Smoke-Tests der Anwendungsmodule."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "app",
        "app.auth",
        "app.cli",
        "app.colors",
        "app.crypto",
        "app.db",
        "app.main",
        "app.models",
        "app.settings",
    ],
)
def test_modul_ist_importierbar(module_name: str) -> None:
    assert importlib.import_module(module_name)


def test_serverstart_ist_aufrufbar() -> None:
    from app.main import main

    assert callable(main)
