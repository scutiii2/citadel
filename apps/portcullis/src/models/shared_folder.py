from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base, utcnow


class SharedFolder(Base):
    """A temporary folder an account opens and shares by link with people who do not log in.

    `expires_at` is fixed at creation (never moved by adding or removing files) and is at most one
    hour away. The link's `token` is kept as it is, not hashed: the owner copies it again later, and
    a leaked database only leaks links that die within the hour. The files are on disk
    (services/shared_folder_service.py); an expired folder reads as missing at once, before the
    sweeper has removed it."""

    __tablename__ = "shared_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(index=True)


class SharedFolderFile(Base):
    """One file in a SharedFolder. Only its name and size are here; the bytes sit at `<root>/<folder id>/<id>`."""

    __tablename__ = "shared_folder_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("shared_folders.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
