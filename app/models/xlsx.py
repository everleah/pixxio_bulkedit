"""Export-Snapshot der Excel-Schnittstelle.

Der Snapshot liegt bewusst in der Datenbank und nicht in der Datei: Nur so laesst sich
beim Import ein Drei-Wege-Abgleich aus Exportbasis, Excel und aktuellem pixx.io-Stand
fuehren, ohne dass die Datei die Basis faelschen kann.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now


class XlsxExport(Base):
    """Ein Exportvorgang mit Spaltenauswahl und Wertsnapshot."""

    __tablename__ = "xlsx_export"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profile.id", ondelete="SET NULL"), default=None
    )
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="SET NULL"), default=None
    )
    columns_json: Mapped[str] = mapped_column(Text)
    snapshot_blob: Mapped[bytes] = mapped_column(LargeBinary)
    row_count: Mapped[int] = mapped_column(default=0)
    had_pending_changes: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)

    def __repr__(self) -> str:
        return f"XlsxExport(id={self.id!r}, rows={self.row_count!r})"
