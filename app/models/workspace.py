"""Arbeitsbestand, Snapshot und ChangeSet.

Der Entwurfszustand (Sicherungsstand, Ablaufdatum, Bearbeitungsversion) liegt direkt
am Arbeitsbestand: ein Arbeitsbestand ist der dauerhaft gespeicherte private Entwurf.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum, utc_now
from app.models.enums import WorkspaceStatus

FIELD_KEY_MAX_LENGTH = 120


class Workspace(Base):
    """Dauerhafter Arbeitsbestand eines Benutzers."""

    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="RESTRICT"))
    script_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("query_script_version.id", ondelete="SET NULL"), default=None
    )
    params_json: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[WorkspaceStatus] = mapped_column(
        str_enum(WorkspaceStatus, "workspace_status"), default=WorkspaceStatus.LOADING
    )
    row_count: Mapped[int] = mapped_column(default=0)
    # Erhoeht sich bei jeder Aenderung; erkennt mehrere Tabs auf demselben Entwurf.
    edit_revision: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
    last_activity_at: Mapped[datetime] = mapped_column(default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)

    assets: Mapped[list[WorkspaceAsset]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    changes: Mapped[list[WorkspaceChange]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Workspace(id={self.id!r}, status={self.status.value!r})"


class WorkspaceAsset(Base):
    """Snapshot: geladene Werte und Aenderungszeitpunkt je Asset."""

    __tablename__ = "workspace_asset"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), primary_key=True
    )
    file_id: Mapped[int] = mapped_column(primary_key=True)
    modify_date: Mapped[str | None] = mapped_column(String(32), default=None)
    # JSON-Objekt Feldkennung -> Wert in Schreibnormalform.
    values_json: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0)

    workspace: Mapped[Workspace] = relationship(back_populates="assets")


class WorkspaceChange(Base):
    """ChangeSet: ausstehende Aenderung einer Zelle."""

    __tablename__ = "workspace_change"
    __table_args__ = (
        UniqueConstraint("workspace_id", "file_id", "field_key"),
        Index("ix_workspace_change_workspace_id_field_key", "workspace_id", "field_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id", ondelete="CASCADE"))
    file_id: Mapped[int]
    field_key: Mapped[str] = mapped_column(String(FIELD_KEY_MAX_LENGTH))
    old_value: Mapped[str | None] = mapped_column(Text, default=None)
    new_value: Mapped[str | None] = mapped_column(Text, default=None)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    workspace: Mapped[Workspace] = relationship(back_populates="changes")
