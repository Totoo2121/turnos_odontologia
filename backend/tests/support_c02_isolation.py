"""Shared live-Postgres isolation scenarios for test_c02_isolation (RN-SE-01).

Each scenario builds two tenants (A/B) with one branch each, runs the check
through tenant-A UnitOfWork/repositories, then tears everything down.
Requires the C-02 tables to exist (Base.metadata.create_all in the runner).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.models import Base, Sucursal, Tenant
from app.infrastructure.repository import UnitOfWork
from tests.c02_pg import pg_dsn


async def _seed_two_tenants(
    factory: async_sessionmaker,
) -> tuple[Tenant, Tenant, Sucursal, Sucursal]:
    async with factory() as setup:
        tenant_a = Tenant(slug_reserva="iso-a-ficticia", nombre="A Ficticia")
        tenant_b = Tenant(slug_reserva="iso-b-ficticia", nombre="B Ficticia")
        setup.add_all([tenant_a, tenant_b])
        await setup.commit()
        async with UnitOfWork(factory, tenant_a.id) as uow_a:
            branch_a = await uow_a.repo(Sucursal).add(
                Sucursal(nombre="Sucursal A Ficticia")
            )
        async with UnitOfWork(factory, tenant_b.id) as uow_b:
            branch_b = await uow_b.repo(Sucursal).add(
                Sucursal(nombre="Sucursal B Ficticia")
            )
    return (tenant_a, tenant_b, branch_a, branch_b)


async def _teardown(factory: async_sessionmaker) -> None:
    async with factory() as cleanup:
        for model in (Sucursal, Tenant):
            for row in (await cleanup.execute(select(model))).scalars():
                await cleanup.delete(row)
        await cleanup.commit()


async def run_isolation_scenario(kind: str) -> None:
    """Run one named isolation scenario against live Postgres."""
    engine = create_async_engine(pg_dsn())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            tenant_a, tenant_b, branch_a, branch_b = await _seed_two_tenants(factory)
            if kind == "list_empty":
                async with UnitOfWork(factory, tenant_a.id) as uow:
                    names = [s.nombre for s in await uow.repo(Sucursal).list()]
                assert "Sucursal A Ficticia" in names
                assert "Sucursal B Ficticia" not in names
            elif kind == "get_denied":
                async with UnitOfWork(factory, tenant_a.id) as uow:
                    assert await uow.repo(Sucursal).get(branch_b.id) is None
            elif kind == "write_denied":
                async with UnitOfWork(factory, tenant_a.id) as uow:
                    assert await uow.repo(Sucursal).soft_delete(branch_b.id) is False
                async with UnitOfWork(factory, tenant_b.id) as uow:
                    survivor = await uow.repo(Sucursal).get(branch_b.id)
                    assert survivor is not None
                    assert survivor.deleted_at is None
            else:
                raise AssertionError(f"unknown scenario: {kind}")
        finally:
            await _teardown(factory)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()
        await asyncio.sleep(0)
