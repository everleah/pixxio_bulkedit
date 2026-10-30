"""Gemeinsame Basis der SQLAlchemy-Modelle."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import DateTime, MetaData
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """Aktueller Zeitpunkt in UTC."""
    return datetime.now(UTC)


def str_enum(enum_cls: type[PyEnum], name: str, *, length: int = 32) -> SAEnum:
    """Enum-Spalte, die die ``value``-Strings speichert und per CHECK absichert."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class Base(DeclarativeBase):
    """Declarative Base mit UTC-Zeitstempeln und stabilen Constraint-Namen."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: dict[Any, Any] = {datetime: DateTime(timezone=True)}
