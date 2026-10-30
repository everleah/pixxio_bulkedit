"""Benutzer, Profile und Profilzuordnung."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum, utc_now
from app.models.enums import Role

USERNAME_MAX_LENGTH = 64
DEFAULT_MAX_ROWS = 5_000


class AppUser(Base):
    """Anmeldekonto der Anwendung; unabhaengig vom pixx.io-Benutzer."""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"), default=Role.VIEWER)
    can_edit_scripts: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    profiles: Mapped[list[Profile]] = relationship(
        secondary="user_profile",
        back_populates="users",
        order_by="Profile.name",
    )

    def __repr__(self) -> str:
        return f"AppUser(id={self.id!r}, username={self.username!r}, role={self.role.value!r})"


class Profile(Base):
    """pixx.io-Zugang mit verschluesseltem API-Key und Schreibgrenzen."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    host: Mapped[str] = mapped_column(String(255))
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary)
    api_key_hint: Mapped[str] = mapped_column(String(32))
    max_retries: Mapped[int] = mapped_column(default=3)
    max_rows: Mapped[int] = mapped_column(default=DEFAULT_MAX_ROWS)
    allow_write: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_check_at: Mapped[datetime | None] = mapped_column(default=None)
    last_check_ok: Mapped[bool | None] = mapped_column(default=None)
    last_check_user: Mapped[str | None] = mapped_column(String(200), default=None)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    users: Mapped[list[AppUser]] = relationship(
        secondary="user_profile",
        back_populates="profiles",
    )
    updated_by: Mapped[AppUser | None] = relationship(foreign_keys=[updated_by_id])

    def __repr__(self) -> str:
        return f"Profile(id={self.id!r}, name={self.name!r}, host={self.host!r})"


class UserProfile(Base):
    """Welcher Benutzer darf welches Profil nutzen."""

    __tablename__ = "user_profile"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), primary_key=True
    )
