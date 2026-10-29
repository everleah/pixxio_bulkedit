import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "pixxio_client",
        "nicegui",
        "pydantic",
        "pydantic_settings",
        "sqlalchemy",
        "alembic",
        "cryptography.fernet",
        "argon2",
        "RestrictedPython",
        "openpyxl",
        "defusedxml",
        "python_multipart",
    ],
)
def test_planned_dependency_is_importable(module_name: str) -> None:
    importlib.import_module(module_name)
