"""C-02 repository/UoW tests (task 2.1) — RED first.

Constructor validation + compiled-SQL scoping run without a DB.
CRUD/rollback/UoW execution is Postgres-gated.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid

import pytest

from app.domain.models import Rol, Sucursal, Usuario
from app.infrastructure.repository import (
    SET_TENANT_GUC_SQL,
    BaseRepository,
    TenantScopeError,
    UnitOfWork,
)


def test_repository_requires_tenant_id() -> None:
    """WHEN constructed without tenant THEN TenantScopeError (fail-closed)."""
    with pytest.raises(TenantScopeError):
        BaseRepository(session=None, model=Sucursal, tenant_id=None)  # type: ignore[arg-type]


def test_repository_rejects_malformed_tenant_id() -> None:
    """WHEN tenant_id is not a UUID THEN TenantScopeError."""
    with pytest.raises(TenantScopeError):
        BaseRepository(session=None, model=Sucursal, tenant_id="not-a-uuid")  # type: ignore[arg-type]


def test_repository_refuses_global_catalog() -> None:
    """WHEN model has no tenant_id (Rol) THEN refused, never silently unscoped."""
    with pytest.raises(TenantScopeError):
        BaseRepository(session=None, model=Rol, tenant_id=uuid.uuid4())


def test_add_stamps_missing_tenant_and_rejects_foreign() -> None:
    """WHEN add() called THEN stamps empty tenant, rejects foreign tenant."""
    import asyncio

    async def _run() -> None:
        tid = uuid.uuid4()
        repo = BaseRepository(session=None, model=Sucursal, tenant_id=tid)
        stamped = Sucursal(nombre="X")
        assert stamped.tenant_id is None
        with pytest.raises(TenantScopeError):
            await repo.add(Sucursal(tenant_id=uuid.uuid4(), nombre="Foreign"))

    asyncio.run(_run())


def test_crud_statements_carry_tenant_scope() -> None:
    """WHEN CRUD queries compiled THEN every one filters by tenant_id."""
    tid = uuid.uuid4()
    repo = BaseRepository(session=None, model=Usuario, tenant_id=tid)
    for stmt in (
        repo.query(),
        repo.query().where(Usuario.id == uuid.uuid4()),
    ):
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled
        assert str(tid).replace("-", "") in compiled


def test_uow_set_guc_statement_is_local_and_strict() -> None:
    """WHEN UoW opens THEN it sets a transaction-LOCAL strict GUC (fail-closed)."""
    assert "set_config" in SET_TENANT_GUC_SQL
    assert "app.tenant_id" in SET_TENANT_GUC_SQL
    assert ", true)" in SET_TENANT_GUC_SQL  # is_local → dies with the txn
    assert "current_setting" not in SET_TENANT_GUC_SQL


def test_uow_requires_tenant_id() -> None:
    """WHEN UnitOfWork built without tenant THEN TenantScopeError."""
    with pytest.raises(TenantScopeError):
        UnitOfWork(session_factory=None, tenant_id=None)  # type: ignore[arg-type]


def test_uow_session_unavailable_outside_context() -> None:
    """WHEN UnitOfWork not entered THEN session/repo raise instead of leaking."""
    from sqlalchemy.ext.asyncio import AsyncSession

    def _never_called() -> AsyncSession:
        raise AssertionError("factory must not be called outside context")

    uow = UnitOfWork(session_factory=_never_called, tenant_id=uuid.uuid4())
    with pytest.raises(TenantScopeError):
        _ = uow.session
    with pytest.raises(TenantScopeError):
        uow.repo(Sucursal)


def test_pg_gated_crud_scoped_and_rollback_atomic() -> None:
    """WHEN CRUD via repo/UoW on live PG THEN scoped; failed UoW rolls back all."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy import func, select
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.domain.models import Base, Tenant
        from tests.c02_pg import pg_dsn

        engine = create_async_engine(pg_dsn())
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as setup:
                tenant_a = Tenant(slug_reserva="repo-a-ficticia", nombre="A")
                tenant_b = Tenant(slug_reserva="repo-b-ficticia", nombre="B")
                setup.add_all([tenant_a, tenant_b])
                await setup.commit()
                aid, bid = tenant_a.id, tenant_b.id
            # Scoped CRUD through UnitOfWork.
            async with UnitOfWork(factory, aid) as uow:
                repo = uow.repo(Sucursal)
                branch = await repo.add(Sucursal(nombre="Matriz Ficticia"))
                assert branch.tenant_id == aid
            async with factory() as check:
                repo_b = BaseRepository(check, Sucursal, bid)
                assert await repo_b.list() == []
                assert await repo_b.get(branch.id) is None
                repo_a = BaseRepository(check, Sucursal, aid)
                assert len(await repo_a.list()) == 1
            # Atomic rollback: second write violates UNIQUE → nothing persists.
            with pytest.raises(IntegrityError):
                async with UnitOfWork(factory, aid) as uow:
                    await uow.repo(Sucursal).add(Sucursal(nombre="Unica Ficticia"))
                    await uow.repo(Sucursal).add(Sucursal(nombre="Unica Ficticia"))
            async with factory() as check2:
                names = [
                    s.nombre
                    for s in await BaseRepository(check2, Sucursal, aid).list(
                        include_deleted=True
                    )
                ]
                assert "Unica Ficticia" not in names
            # Cleanup.
            async with factory() as cleanup:
                for model in (Sucursal, Tenant):
                    for row in (await cleanup.execute(select(model))).scalars():
                        await cleanup.delete(row)
                await cleanup.commit()
                remaining = (
                    await cleanup.execute(select(func.count()).select_from(Tenant))
                ).scalar()
                assert remaining == 0
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_gated_uow_sets_guc_per_transaction() -> None:
    """WHEN UnitOfWork entered on live PG THEN current_setting matches tenant."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from tests.c02_pg import pg_dsn

        engine = create_async_engine(pg_dsn())
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            tid = uuid.uuid4()
            async with UnitOfWork(factory, tid) as uow:
                value = (
                    await uow.session.execute(
                        text("SELECT current_setting('app.tenant_id')")
                    )
                ).scalar()
                assert value == str(tid)
        finally:
            await engine.dispose()

    asyncio.run(_run())
