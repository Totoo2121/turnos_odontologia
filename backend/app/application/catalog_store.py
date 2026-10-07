"""C-05 catalog store seam (ports/adapters, auth_service precedent).

``CatalogStore`` is the persistence port the CRUD routers speak to: the
tenant is pinned at construction (like ``BaseRepository``) so rows of other
tenants read as missing (routers answer 404, never 403-leak).

- ``DbCatalogStore``: SQLAlchemy implementation over the typed C-05
  repositories (production; RLS underneath enforces the same boundary).
- ``MemoryCatalogStore``: shared in-memory fake so HTTP behavior tests run
  without Postgres. Instances share one module-global dict keyed per
  resource; each instance only ever sees its own tenant's rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from app.infrastructure.repository import coerce_tenant_id

Row = dict[str, Any]

_RESOURCES = ("profesionales", "sillones", "prestaciones", "bloqueos")

_MEMORY: dict[str, dict[uuid.UUID, Row]] = {name: {} for name in _RESOURCES}
_LINKS: dict[uuid.UUID, list[uuid.UUID]] = {}


def reset_memory_catalog() -> None:
    """Clear the shared memory fake (test isolation between cases)."""
    for bucket in _MEMORY.values():
        bucket.clear()
    _LINKS.clear()


class CatalogStore(Protocol):
    """Persistence port for the 4 catalog resources + enablements."""

    async def create_profesional(self, data: Row) -> Row: ...
    async def get_profesional(self, entity_id: uuid.UUID) -> Row | None: ...
    async def list_profesionales(self, *, limit: int, offset: int) -> list[Row]: ...
    async def update_profesional(self, entity_id: uuid.UUID, patch: Row) -> Row | None: ...
    async def delete_profesional(self, entity_id: uuid.UUID) -> bool: ...
    async def set_habilitaciones(
        self, profesional_id: uuid.UUID, prestacion_ids: list[uuid.UUID]
    ) -> None: ...
    async def get_habilitaciones(
        self, profesional_id: uuid.UUID
    ) -> list[uuid.UUID]: ...

    async def create_sillon(self, data: Row) -> Row: ...
    async def get_sillon(self, entity_id: uuid.UUID) -> Row | None: ...
    async def list_sillones(self, *, limit: int, offset: int) -> list[Row]: ...
    async def update_sillon(self, entity_id: uuid.UUID, patch: Row) -> Row | None: ...
    async def delete_sillon(self, entity_id: uuid.UUID) -> bool: ...

    async def create_prestacion(self, data: Row) -> Row: ...
    async def get_prestacion(self, entity_id: uuid.UUID) -> Row | None: ...
    async def list_prestaciones(self, *, limit: int, offset: int) -> list[Row]: ...
    async def update_prestacion(
        self, entity_id: uuid.UUID, patch: Row
    ) -> Row | None: ...
    async def delete_prestacion(self, entity_id: uuid.UUID) -> bool: ...

    async def create_bloqueo(self, data: Row) -> Row: ...
    async def get_bloqueo(self, entity_id: uuid.UUID) -> Row | None: ...
    async def list_bloqueos(self, *, limit: int, offset: int) -> list[Row]: ...
    async def update_bloqueo(self, entity_id: uuid.UUID, patch: Row) -> Row | None: ...
    async def delete_bloqueo(self, entity_id: uuid.UUID) -> bool: ...
    async def list_bloqueos_for_profesional(
        self, profesional_id: uuid.UUID, *, desde: datetime, hasta: datetime
    ) -> list[Row]: ...


class MemoryCatalogStore:
    """In-memory fake: tenant-pinned view over the shared global dict."""

    def __init__(self, tenant_id: uuid.UUID | str) -> None:
        self._tenant_id = coerce_tenant_id(tenant_id)

    def _scoped(self, resource: str) -> list[Row]:
        return sorted(
            (
                row
                for row in _MEMORY[resource].values()
                if row["tenant_id"] == self._tenant_id and row.get("is_active", True)
            ),
            key=lambda row: row["created_at"],
        )

    def _get(self, resource: str, entity_id: uuid.UUID) -> Row | None:
        row = _MEMORY[resource].get(entity_id)
        if row is None or row["tenant_id"] != self._tenant_id:
            return None
        if not row.get("is_active", True):
            return None
        return row

    def _create(self, resource: str, data: Row) -> Row:
        now = datetime.now(UTC)
        row: Row = {
            "id": uuid.uuid4(),
            "tenant_id": self._tenant_id,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            **data,
        }
        _MEMORY[resource][row["id"]] = row
        return row

    def _update(self, resource: str, entity_id: uuid.UUID, patch: Row) -> Row | None:
        row = self._get(resource, entity_id)
        if row is None:
            return None
        row.update({k: v for k, v in patch.items() if k not in ("id", "tenant_id")})
        row["updated_at"] = datetime.now(UTC)
        return row

    def _delete(self, resource: str, entity_id: uuid.UUID) -> bool:
        row = self._get(resource, entity_id)
        if row is None:
            return False
        row["is_active"] = False
        row["deleted_at"] = datetime.now(UTC)
        row["updated_at"] = datetime.now(UTC)
        return True

    def _page(self, rows: list[Row], *, limit: int, offset: int) -> list[Row]:
        return rows[offset : offset + limit]

    async def create_profesional(self, data: Row) -> Row:
        return self._create("profesionales", data)

    async def get_profesional(self, entity_id: uuid.UUID) -> Row | None:
        row = self._get("profesionales", entity_id)
        if row is None:
            return None
        return {**row, "prestacion_ids": list(_LINKS.get(entity_id, []))}

    async def list_profesionales(self, *, limit: int, offset: int) -> list[Row]:
        rows = [
            {**row, "prestacion_ids": list(_LINKS.get(row["id"], []))}
            for row in self._scoped("profesionales")
        ]
        return self._page(rows, limit=limit, offset=offset)

    async def update_profesional(self, entity_id: uuid.UUID, patch: Row) -> Row | None:
        patch = dict(patch)
        prestacion_ids = patch.pop("prestacion_ids", None)
        row = self._update("profesionales", entity_id, patch)
        if row is None:
            return None
        if prestacion_ids is not None:
            _LINKS[entity_id] = list(prestacion_ids)
        return {**row, "prestacion_ids": list(_LINKS.get(entity_id, []))}

    async def delete_profesional(self, entity_id: uuid.UUID) -> bool:
        return self._delete("profesionales", entity_id)

    async def set_habilitaciones(
        self, profesional_id: uuid.UUID, prestacion_ids: list[uuid.UUID]
    ) -> None:
        owner = _MEMORY["profesionales"].get(profesional_id)
        if owner is None or owner["tenant_id"] != self._tenant_id:
            return
        _LINKS[profesional_id] = list(prestacion_ids)

    async def get_habilitaciones(
        self, profesional_id: uuid.UUID
    ) -> list[uuid.UUID]:
        owner = _MEMORY["profesionales"].get(profesional_id)
        if owner is None or owner["tenant_id"] != self._tenant_id:
            return []
        return list(_LINKS.get(profesional_id, []))

    async def create_sillon(self, data: Row) -> Row:
        return self._create("sillones", data)

    async def get_sillon(self, entity_id: uuid.UUID) -> Row | None:
        return self._get("sillones", entity_id)

    async def list_sillones(self, *, limit: int, offset: int) -> list[Row]:
        return self._page(self._scoped("sillones"), limit=limit, offset=offset)

    async def update_sillon(self, entity_id: uuid.UUID, patch: Row) -> Row | None:
        return self._update("sillones", entity_id, patch)

    async def delete_sillon(self, entity_id: uuid.UUID) -> bool:
        return self._delete("sillones", entity_id)

    async def create_prestacion(self, data: Row) -> Row:
        return self._create("prestaciones", data)

    async def get_prestacion(self, entity_id: uuid.UUID) -> Row | None:
        return self._get("prestaciones", entity_id)

    async def list_prestaciones(self, *, limit: int, offset: int) -> list[Row]:
        return self._page(self._scoped("prestaciones"), limit=limit, offset=offset)

    async def update_prestacion(
        self, entity_id: uuid.UUID, patch: Row
    ) -> Row | None:
        return self._update("prestaciones", entity_id, patch)

    async def delete_prestacion(self, entity_id: uuid.UUID) -> bool:
        return self._delete("prestaciones", entity_id)

    async def create_bloqueo(self, data: Row) -> Row:
        return self._create("bloqueos", data)

    async def get_bloqueo(self, entity_id: uuid.UUID) -> Row | None:
        return self._get("bloqueos", entity_id)

    async def list_bloqueos(self, *, limit: int, offset: int) -> list[Row]:
        return self._page(self._scoped("bloqueos"), limit=limit, offset=offset)

    async def update_bloqueo(self, entity_id: uuid.UUID, patch: Row) -> Row | None:
        return self._update("bloqueos", entity_id, patch)

    async def delete_bloqueo(self, entity_id: uuid.UUID) -> bool:
        return self._delete("bloqueos", entity_id)

    async def list_bloqueos_for_profesional(
        self, profesional_id: uuid.UUID, *, desde: datetime, hasta: datetime
    ) -> list[Row]:
        return [
            row
            for row in self._scoped("bloqueos")
            if row.get("profesional_id") == profesional_id
            and row["inicio"] < hasta
            and desde < row["fin"]
        ]


class DbCatalogStore:
    """SQLAlchemy implementation over the typed C-05 repositories."""

    def __init__(self, session, tenant_id: uuid.UUID | str) -> None:  # type: ignore[no-untyped-def]
        from app.domain.agenda.repositories import (
            BloqueoRepository,
            PrestacionRepository,
            ProfesionalPrestacionRepository,
            ProfesionalRepository,
            SillonRepository,
        )

        self._session = session
        self._tenant_id = coerce_tenant_id(tenant_id)
        self._profesionales = ProfesionalRepository(session, self._tenant_id)
        self._sillones = SillonRepository(session, self._tenant_id)
        self._prestaciones = PrestacionRepository(session, self._tenant_id)
        self._bloqueos = BloqueoRepository(session, self._tenant_id)
        self._links = ProfesionalPrestacionRepository(session, self._tenant_id)

    @staticmethod
    def _row(obj: Any, extra: Row | None = None) -> Row:  # type: ignore[no-untyped-def]
        data: Row = {
            column.name: getattr(obj, column.name)
            for column in obj.__table__.columns
        }
        if extra:
            data.update(extra)
        return data

    async def _habilitaciones(self, profesional_id: uuid.UUID) -> list[uuid.UUID]:
        links = await self._links.list_for_profesional(profesional_id)
        return [link.prestacion_id for link in links]

    async def create_profesional(self, data: Row) -> Row:
        from app.domain.agenda.models import Profesional, ProfesionalPrestacion

        data = dict(data)
        prestacion_ids = data.pop("prestacion_ids", [])
        obj = Profesional(tenant_id=self._tenant_id, **data)
        await self._profesionales.add(obj)
        await self._session.flush()
        for prestacion_id in prestacion_ids:
            await self._links.add(
                ProfesionalPrestacion(
                    tenant_id=self._tenant_id,
                    profesional_id=obj.id,
                    prestacion_id=prestacion_id,
                )
            )
        await self._session.flush()
        return self._row(obj, {"prestacion_ids": list(prestacion_ids)})

    async def get_profesional(self, entity_id: uuid.UUID) -> Row | None:
        obj = await self._profesionales.get(entity_id)
        if obj is None:
            return None
        return self._row(obj, {"prestacion_ids": await self._habilitaciones(obj.id)})

    async def list_profesionales(self, *, limit: int, offset: int) -> list[Row]:
        rows = []
        for obj in await self._profesionales.list(limit=limit, offset=offset):
            rows.append(
                self._row(obj, {"prestacion_ids": await self._habilitaciones(obj.id)})
            )
        return rows

    async def update_profesional(self, entity_id: uuid.UUID, patch: Row) -> Row | None:
        from app.domain.agenda.models import ProfesionalPrestacion

        obj = await self._profesionales.get(entity_id)
        if obj is None:
            return None
        patch = dict(patch)
        prestacion_ids = patch.pop("prestacion_ids", None)
        for key, value in patch.items():
            setattr(obj, key, value)
        await self._session.flush()
        if prestacion_ids is not None:
            for link in await self._links.list_for_profesional(entity_id):
                await self._links.remove(link.profesional_id, link.prestacion_id)
            for prestacion_id in prestacion_ids:
                await self._links.add(
                    ProfesionalPrestacion(
                        tenant_id=self._tenant_id,
                        profesional_id=entity_id,
                        prestacion_id=prestacion_id,
                    )
                )
            await self._session.flush()
        return self._row(obj, {"prestacion_ids": await self._habilitaciones(obj.id)})

    async def delete_profesional(self, entity_id: uuid.UUID) -> bool:
        return await self._profesionales.soft_delete(entity_id)

    async def set_habilitaciones(
        self, profesional_id: uuid.UUID, prestacion_ids: list[uuid.UUID]
    ) -> None:
        from app.domain.agenda.models import ProfesionalPrestacion

        for link in await self._links.list_for_profesional(profesional_id):
            await self._links.remove(link.profesional_id, link.prestacion_id)
        for prestacion_id in prestacion_ids:
            await self._links.add(
                ProfesionalPrestacion(
                    tenant_id=self._tenant_id,
                    profesional_id=profesional_id,
                    prestacion_id=prestacion_id,
                )
            )
        await self._session.flush()

    async def get_habilitaciones(
        self, profesional_id: uuid.UUID
    ) -> list[uuid.UUID]:
        obj = await self._profesionales.get(profesional_id)
        if obj is None:
            return []
        return await self._habilitaciones(profesional_id)

    async def _crud(
        self, repo: Any, model: Any, action: str, *args: Any  # type: ignore[no-untyped-def]
    ) -> Any:
        if action == "create":
            obj = model(tenant_id=self._tenant_id, **args[0])
            await repo.add(obj)
            await self._session.flush()
            return self._row(obj)
        if action == "get":
            obj = await repo.get(args[0])
            return None if obj is None else self._row(obj)
        if action == "list":
            return [self._row(obj) for obj in await repo.list(limit=args[0], offset=args[1])]
        if action == "update":
            obj = await repo.get(args[0])
            if obj is None:
                return None
            for key, value in args[1].items():
                setattr(obj, key, value)
            await self._session.flush()
            return self._row(obj)
        if action == "delete":
            return await repo.soft_delete(args[0])
        raise AssertionError(f"unknown crud action: {action}")

    async def create_sillon(self, data: Row) -> Row:
        from app.domain.agenda.models import Sillon

        return await self._crud(self._sillones, Sillon, "create", data)

    async def get_sillon(self, entity_id: uuid.UUID) -> Row | None:
        return await self._crud(self._sillones, None, "get", entity_id)

    async def list_sillones(self, *, limit: int, offset: int) -> list[Row]:
        return await self._crud(self._sillones, None, "list", limit, offset)

    async def update_sillon(self, entity_id: uuid.UUID, patch: Row) -> Row | None:
        return await self._crud(self._sillones, None, "update", entity_id, patch)

    async def delete_sillon(self, entity_id: uuid.UUID) -> bool:
        return await self._crud(self._sillones, None, "delete", entity_id)

    async def create_prestacion(self, data: Row) -> Row:
        from app.domain.agenda.models import Prestacion

        return await self._crud(self._prestaciones, Prestacion, "create", data)

    async def get_prestacion(self, entity_id: uuid.UUID) -> Row | None:
        return await self._crud(self._prestaciones, None, "get", entity_id)

    async def list_prestaciones(self, *, limit: int, offset: int) -> list[Row]:
        return await self._crud(self._prestaciones, None, "list", limit, offset)

    async def update_prestacion(
        self, entity_id: uuid.UUID, patch: Row
    ) -> Row | None:
        return await self._crud(
            self._prestaciones, None, "update", entity_id, patch
        )

    async def delete_prestacion(self, entity_id: uuid.UUID) -> bool:
        return await self._crud(self._prestaciones, None, "delete", entity_id)

    async def create_bloqueo(self, data: Row) -> Row:
        from app.domain.agenda.models import Bloqueo

        return await self._crud(self._bloqueos, Bloqueo, "create", data)

    async def get_bloqueo(self, entity_id: uuid.UUID) -> Row | None:
        return await self._crud(self._bloqueos, None, "get", entity_id)

    async def list_bloqueos(self, *, limit: int, offset: int) -> list[Row]:
        return await self._crud(self._bloqueos, None, "list", limit, offset)

    async def update_bloqueo(self, entity_id: uuid.UUID, patch: Row) -> Row | None:
        return await self._crud(self._bloqueos, None, "update", entity_id, patch)

    async def delete_bloqueo(self, entity_id: uuid.UUID) -> bool:
        return await self._crud(self._bloqueos, None, "delete", entity_id)

    async def list_bloqueos_for_profesional(
        self, profesional_id: uuid.UUID, *, desde: datetime, hasta: datetime
    ) -> list[Row]:
        from app.domain.agenda.models import Bloqueo

        stmt = (
            self._bloqueos.query()
            .where(Bloqueo.profesional_id == profesional_id)
            .where(Bloqueo.inicio < hasta)
            .where(desde < Bloqueo.fin)
        )
        result = await self._session.execute(stmt)
        return [self._row(obj) for obj in result.scalars().all()]
