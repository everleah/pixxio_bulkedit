"""Runs, Change-Log und Admin-Audit."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum, utc_now
from app.models.enums import ChangeStatus, RunKind, RunMode, RunSource, RunStatus


class Run(Base):
    """Ein Abfrage- oder Schreiblauf, auch als Dry Run."""

    __tablename__ = "run"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[RunKind] = mapped_column(str_enum(RunKind, "run_kind"), default=RunKind.QUERY)
    mode: Mapped[RunMode] = mapped_column(str_enum(RunMode, "run_mode"), default=RunMode.DRY_RUN)
    source: Mapped[RunSource] = mapped_column(
        str_enum(RunSource, "run_source"), default=RunSource.GRID
    )
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "run_status"), default=RunStatus.RUNNING
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profile.id", ondelete="SET NULL"), default=None
    )
    script_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("query_script_version.id", ondelete="SET NULL"), default=None
    )
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="SET NULL"), default=None
    )
    write_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("write_plan.id", ondelete="SET NULL"), default=None
    )
    params_json: Mapped[str | None] = mapped_column(Text, default=None)
    plan_json: Mapped[str | None] = mapped_column(Text, default=None)
    stats_json: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    changes: Mapped[list[ChangeLog]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Run(id={self.id!r}, kind={self.kind.value!r}, status={self.status.value!r})"


class ChangeLog(Base):
    """Feldbezogene Alt-/Neuwerte eines Laufs."""

    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id", ondelete="CASCADE"))
    file_id: Mapped[int]
    field_key: Mapped[str] = mapped_column(String(120))
    old_value: Mapped[str | None] = mapped_column(Text, default=None)
    new_value: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[ChangeStatus] = mapped_column(
        str_enum(ChangeStatus, "change_status"), default=ChangeStatus.PLANNED
    )
    job_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    run: Mapped[Run] = relationship(back_populates="changes")


class AdminAudit(Base):
    """Protokoll der Benutzer- und Profilaenderungen (ohne Schluessel)."""

    __tablename__ = "admin_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(200), default=None)
    details_json: Mapped[str | None] = mapped_column(Text, default=None)
    at: Mapped[datetime] = mapped_column(default=utc_now)
