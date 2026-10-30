"""``skipped`` für ChangeLog und ``partial`` für Schreibschritte ergänzen.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHANGE_VALUES = ("planned", "ok", "failed", "skipped", "skipped_conflict", "unknown")
CHANGE_PREVIOUS = ("planned", "ok", "failed", "skipped_conflict", "unknown")
STEP_VALUES = ("pending", "running", "ok", "partial", "failed", "unknown", "skipped")
STEP_PREVIOUS = ("pending", "running", "ok", "failed", "unknown", "skipped")


def _enum(values: Sequence[str], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _alter(table: str, values: Sequence[str], previous: Sequence[str], name: str) -> None:
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_enum(previous, name),
            type_=_enum(values, name),
            existing_nullable=False,
        )


def upgrade() -> None:
    _alter("change_log", CHANGE_VALUES, CHANGE_PREVIOUS, "change_status")
    _alter("write_plan_step", STEP_VALUES, STEP_PREVIOUS, "step_status")


def downgrade() -> None:
    op.execute("UPDATE change_log SET status = 'unknown' WHERE status = 'skipped'")
    op.execute("UPDATE write_plan_step SET status = 'unknown' WHERE status = 'partial'")
    _alter("change_log", CHANGE_PREVIOUS, CHANGE_VALUES, "change_status")
    _alter("write_plan_step", STEP_PREVIOUS, STEP_VALUES, "step_status")
