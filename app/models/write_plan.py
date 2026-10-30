"""Schreibplan und Auftragsschritte.

Ein Schreibplan ist unveraenderlich: Dry Run und Live-Lauf verwenden denselben Plan.
Aendert sich das ChangeSet, verliert der Plan seine Gueltigkeit (``change_digest``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum, utc_now
from app.models.enums import PlanStatus, RunMode, StepStatus


class WritePlan(Base):
    """Bestaetigbarer, unveraenderlicher Plan aus einem ChangeSet."""

    __tablename__ = "write_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="SET NULL"), default=None
    )
    mode: Mapped[RunMode] = mapped_column(str_enum(RunMode, "write_mode"), default=RunMode.DRY_RUN)
    status: Mapped[PlanStatus] = mapped_column(
        str_enum(PlanStatus, "plan_status"), default=PlanStatus.DRAFT
    )
    change_digest: Mapped[str] = mapped_column(String(64))
    plan_json: Mapped[str] = mapped_column(Text)
    step_count: Mapped[int] = mapped_column(default=0)
    overwrite_confirmed: Mapped[bool] = mapped_column(default=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    approved_at: Mapped[datetime | None] = mapped_column(default=None)

    steps: Mapped[list[WritePlanStep]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="WritePlanStep.step_no",
    )

    def __repr__(self) -> str:
        return f"WritePlan(id={self.id!r}, status={self.status.value!r}, steps={self.step_count!r})"


class WritePlanStep(Base):
    """Auftragsschritt: Ziel-IDs, Payload, Job-ID und Verifikation."""

    __tablename__ = "write_plan_step"
    __table_args__ = (UniqueConstraint("plan_id", "step_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("write_plan.id", ondelete="CASCADE"))
    step_no: Mapped[int]
    ids_json: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[StepStatus] = mapped_column(
        str_enum(StepStatus, "step_status"), default=StepStatus.PENDING
    )
    job_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    verification_json: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    plan: Mapped[WritePlan] = relationship(back_populates="steps")
