"""Abfrage-Scripts mit unveraenderlichen Versionen."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now


class QueryScript(Base):
    """Benannte Abfrage; ausgefuehrt wird die veroeffentlichte Version."""

    __tablename__ = "query_script"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    is_shared: Mapped[bool] = mapped_column(default=True)
    is_template: Mapped[bool] = mapped_column(default=False)
    # Bewusst ohne Fremdschluessel: SQLite kann Constraints nicht nachtraeglich
    # hinzufuegen, und die Veroeffentlichung wird im Service geprueft.
    current_version_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    versions: Mapped[list[QueryScriptVersion]] = relationship(
        back_populates="script",
        cascade="all, delete-orphan",
        order_by="QueryScriptVersion.version_no",
    )

    def __repr__(self) -> str:
        return f"QueryScript(id={self.id!r}, name={self.name!r})"


class QueryScriptVersion(Base):
    """Unveraenderlicher Stand eines Scripts."""

    __tablename__ = "query_script_version"
    __table_args__ = (UniqueConstraint("script_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("query_script.id", ondelete="CASCADE"))
    version_no: Mapped[int]
    source: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    script: Mapped[QueryScript] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"QueryScriptVersion(id={self.id!r}, version_no={self.version_no!r})"
