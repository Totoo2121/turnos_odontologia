"""Row-lifecycle columns (soft-delete support) for C-02 domain entities.

`AuditMixin` is lifecycle metadata only (active window + timestamps), not the
C-17 append-only event audit. Soft-delete itself is executed by repositories.
"""

import datetime

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class AuditMixin:
    """is_active + created_at/updated_at/deleted_at for soft-deletable rows."""

    @declared_attr
    def is_active(cls) -> Mapped[bool]:
        """Whether the row is logically alive (soft-delete flips to False)."""
        return mapped_column(
            Boolean, nullable=False, default=True, server_default=func.true()
        )

    @declared_attr
    def created_at(cls) -> Mapped[datetime.datetime]:
        """Row creation instant (DB clock authority)."""
        return mapped_column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        )

    @declared_attr
    def updated_at(cls) -> Mapped[datetime.datetime]:
        """Last modification instant (advances on every UPDATE)."""
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )

    @declared_attr
    def deleted_at(cls) -> Mapped[datetime.datetime | None]:
        """Soft-delete instant (NULL means alive)."""
        return mapped_column(DateTime(timezone=True), nullable=True)
