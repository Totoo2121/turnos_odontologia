"""C-05 typed agenda repositories (D1): thin BaseRepository[T] subclasses.

Tenant scoping + soft-delete come from ``BaseRepository`` (C-02, D8): every
query filters by ``tenant_id`` fail-closed and ``UnitOfWork`` pins the
``app.tenant_id`` GUC so RLS enforces the same boundary underneath.
``ProfesionalPrestacionRepository`` is link-table shaped like ``UserRol``:
no soft-delete columns, so it exposes a physical ``remove()`` instead.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from app.domain.agenda.models import (
    Bloqueo,
    Prestacion,
    Profesional,
    ProfesionalPrestacion,
    Sillon,
)
from app.infrastructure.repository import BaseRepository


class ProfesionalRepository(BaseRepository[Profesional]):
    """Tenant-scoped CRUD for profesionales."""

    def __init__(self, session, tenant_id) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session, Profesional, tenant_id)


class SillonRepository(BaseRepository[Sillon]):
    """Tenant-scoped CRUD for sillones."""

    def __init__(self, session, tenant_id) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session, Sillon, tenant_id)


class PrestacionRepository(BaseRepository[Prestacion]):
    """Tenant-scoped CRUD for prestaciones."""

    def __init__(self, session, tenant_id) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session, Prestacion, tenant_id)


class BloqueoRepository(BaseRepository[Bloqueo]):
    """Tenant-scoped CRUD for bloqueos."""

    def __init__(self, session, tenant_id) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session, Bloqueo, tenant_id)


class ProfesionalPrestacionRepository(BaseRepository[ProfesionalPrestacion]):
    """Enablement links: physical DELETE only (no lifecycle columns)."""

    def __init__(self, session, tenant_id) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session, ProfesionalPrestacion, tenant_id)

    async def list_for_profesional(
        self, profesional_id: uuid.UUID
    ) -> list[ProfesionalPrestacion]:
        """List enablement links of one professional within this tenant."""
        stmt = (
            self.query(include_deleted=True)
            .where(ProfesionalPrestacion.profesional_id == profesional_id)
            .order_by(ProfesionalPrestacion.created_at)
        )
        result = await self._require_session().execute(stmt)
        return list(result.scalars().all())

    async def remove(self, profesional_id: uuid.UUID, prestacion_id: uuid.UUID) -> bool:
        """Physically revoke one enablement (link tables carry no lifecycle)."""
        session = self._require_session()
        stmt = (
            select(ProfesionalPrestacion)
            .where(ProfesionalPrestacion.tenant_id == self.tenant_id)
            .where(ProfesionalPrestacion.profesional_id == profesional_id)
            .where(ProfesionalPrestacion.prestacion_id == prestacion_id)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return False
        await session.execute(
            delete(ProfesionalPrestacion).where(
                ProfesionalPrestacion.id == row.id,
                ProfesionalPrestacion.tenant_id == self.tenant_id,
            )
        )
        await session.flush()
        return True
