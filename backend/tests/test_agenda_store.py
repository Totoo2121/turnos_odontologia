"""C-05 catalog store seam tests (tasks 2.2/4.1 support) — RED first.

The store protocol + in-memory fake let HTTP behavior tests run without
Postgres; the DB-backed store is exercised pg-gated. Tenant scoping is
fail-closed in both implementations.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid
from collections.abc import Coroutine
from typing import Any

import pytest

from app.application.catalog_store import MemoryCatalogStore, reset_memory_catalog


@pytest.fixture(autouse=True)
def _clean_memory():  # type: ignore[no-untyped-def]
    reset_memory_catalog()
    yield
    reset_memory_catalog()


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    import asyncio

    return asyncio.run(coro)


def test_memory_store_crud_prestacion() -> None:
    """WHEN prestacion creada THEN get/list/update/delete dentro del tenant."""
    tid = uuid.uuid4()
    store = MemoryCatalogStore(tenant_id=tid)

    async def _flow():  # type: ignore[no-untyped-def]
        created = await store.create_prestacion(
            {"nombre": "Limpieza (ficticia)", "duracion_min": 45}
        )
        assert created["tenant_id"] == tid
        assert (await store.get_prestacion(created["id"]))["nombre"].startswith(
            "Limpieza"
        )
        assert len(await store.list_prestaciones(limit=10, offset=0)) == 1
        updated = await store.update_prestacion(created["id"], {"duracion_min": 50})
        assert updated is not None and updated["duracion_min"] == 50
        assert await store.delete_prestacion(created["id"]) is True
        assert await store.get_prestacion(created["id"]) is None
        assert await store.delete_prestacion(created["id"]) is False

    _run(_flow())


def test_memory_store_cross_tenant_invisible() -> None:
    """WHEN otro tenant pide el id THEN None (el router respondera 404)."""
    tid_a, tid_b = uuid.uuid4(), uuid.uuid4()
    store_a = MemoryCatalogStore(tenant_id=tid_a)
    store_b = MemoryCatalogStore(tenant_id=tid_b)

    async def _flow():  # type: ignore[no-untyped-def]
        created = await store_a.create_sillon({"nombre": "Box 1 (demo)"})
        assert await store_b.get_sillon(created["id"]) is None
        assert await store_b.list_sillones(limit=10, offset=0) == []
        assert await store_b.update_sillon(created["id"], {"nombre": "X"}) is None
        assert await store_b.delete_sillon(created["id"]) is False
        # El dueño original lo sigue viendo (2do input: aislamiento no borra).
        assert await store_a.get_sillon(created["id"]) is not None

    _run(_flow())


def test_memory_store_habilitaciones_por_profesional() -> None:
    """WHEN habilitaciones fijadas THEN solo ese profesional las ve."""
    tid = uuid.uuid4()
    store = MemoryCatalogStore(tenant_id=tid)

    async def _flow():  # type: ignore[no-untyped-def]
        prof = await store.create_profesional({"nombre": "Dr. Demo (ficticio)"})
        prest = await store.create_prestacion(
            {"nombre": "Consulta (ficticia)", "duracion_min": 30}
        )
        await store.set_habilitaciones(prof["id"], [prest["id"]])
        assert await store.get_habilitaciones(prof["id"]) == [prest["id"]]
        assert await store.get_habilitaciones(uuid.uuid4()) == []
        # Cross-tenant: otro tenant no ve habilitaciones ajenas.
        other = MemoryCatalogStore(tenant_id=uuid.uuid4())
        assert await other.get_habilitaciones(prof["id"]) == []

    _run(_flow())


def test_memory_store_paginacion() -> None:
    """WHEN 3 bloqueos y limit=2 THEN pagina 2+1 (offset honrado)."""
    from datetime import UTC, datetime, timedelta

    tid = uuid.uuid4()
    store = MemoryCatalogStore(tenant_id=tid)
    base = datetime(2026, 12, 25, 9, tzinfo=UTC)
    prof = uuid.uuid4()

    async def _flow():  # type: ignore[no-untyped-def]
        for i in range(3):
            await store.create_bloqueo(
                {
                    "profesional_id": prof,
                    "sillon_id": None,
                    "inicio": base + timedelta(days=i),
                    "fin": base + timedelta(days=i, hours=8),
                    "motivo": "feriado",
                }
            )
        assert len(await store.list_bloqueos(limit=2, offset=0)) == 2
        assert len(await store.list_bloqueos(limit=2, offset=2)) == 1
        assert await store.list_bloqueos(limit=2, offset=9) == []

    _run(_flow())
