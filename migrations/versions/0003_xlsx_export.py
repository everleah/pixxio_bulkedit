"""Tabelle ``xlsx_export`` und Rückverweis vom Lauf auf den Export.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "xlsx_export",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("columns_json", sa.Text(), nullable=False),
        sa.Column("snapshot_blob", sa.LargeBinary(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("had_pending_changes", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name="fk_xlsx_export_user_id_app_user", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profile.id"],
            name="fk_xlsx_export_profile_id_profile",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_xlsx_export_workspace_id_workspace",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_xlsx_export"),
    )
    with op.batch_alter_table("run", schema=None) as batch_op:
        batch_op.add_column(sa.Column("xlsx_export_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_run_xlsx_export_id_xlsx_export",
            "xlsx_export",
            ["xlsx_export_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("run", schema=None) as batch_op:
        batch_op.drop_constraint("fk_run_xlsx_export_id_xlsx_export", type_="foreignkey")
        batch_op.drop_column("xlsx_export_id")
    op.drop_table("xlsx_export")
