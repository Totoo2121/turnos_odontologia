"""C-02 soft-delete tests (task 1.3) — RED first.

Default exclusion is asserted on compiled SQL (no DB). Persistence
(invisible + row kept with deleted_at) is Postgres-gated.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid

import pytest

from app.domain.models import Sucursal, Tenant, UserRol
from app.infrastructure.repository import BaseRepository


def _repo(model: object, tenant_id: uuid.UUID | None = None) -> BaseRepository:  # type: ignore[type-arg]
    return BaseRepository(session=None, model=model, tenant_id=tenant_id)  # type: ignore[arg-type]


def test_default_query_excludes_deleted() -> None:
    """WHEN default scoped query compiled THEN deleted_at IS NULL filter present."""
    tid = uuid.uuid4()
    stmt = _repo(Sucursal, tid).query()
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "deleted_at IS NULL" in compiled
    assert str(tid).replace("-", "") in compiled


def test_include_deleted_omits_filter() -> None:
    """WHEN include_deleted compiled THEN no deleted_at filter, tenant kept."""
    tid = uuid.uuid4()
    stmt = _repo(Sucursal, tid).query(include_deleted=True)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "deleted_at IS NULL" not in compiled
    assert "deleted_at =" not in compiled
    assert str(tid).replace("-", "") in compiled


def test_link_table_query_has_no_deleted_filter() -> None:
    """WHEN user_rol query compiled THEN only tenant scope (physical delete)."""
    tid = uuid.uuid4()
    stmt = _repo(UserRol, tid).query()
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "deleted_at" not in compiled
    assert "tenant_id" in compiled


def test_soft_delete_unsupported_on_link_table() -> None:
    """WHEN soft_delete called on user_rol THEN refused (physical DELETE only)."""
    import asyncio

    async def _run() -> None:
        with pytest.raises(ValueError):
            await _repo(UserRol, uuid.uuid4()).soft_delete(uuid.uuid4())

    asyncio.run(_run())


def test_pg_gated_deleted_invisible_but_persisted() -> None:
    """WHEN sucursal deleted on live PG THEN hidden by default, row kept."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.domain.models import Base
        from tests.c02_pg import pg_dsn

        engine = create_async_engine(pg_dsn())
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                tenant = Tenant(slug_reserva="sd-ficticia", nombre="SD Ficticia")
                session.add(tenant)
                await session.commit()
                repo = BaseRepository(session, Sucursal, tenant.id)
                branch = await repo.add(
                    Sucursal(tenant_id=tenant.id, nombre="Centro Ficticio")
                )
                await session.commit()
                assert await repo.soft_delete(branch.id) is True
                await session.commit()
                assert await repo.get(branch.id) is None
                assert await repo.list() == []
                fetched = await repo.get(branch.id, include_deleted=True)
                assert fetched is not None
                assert fetched.deleted_at is not None
                assert fetched.is_active is False
                raw = (
                    await session.execute(
                        select(Sucursal).where(Sucursal.id == branch.id)
                    )
                ).scalar_one()
                assert raw.deleted_at is not None
                await session.delete(raw)
                await session.delete(tenant)
                await session.commit()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_run())
