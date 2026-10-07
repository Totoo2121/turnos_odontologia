"""C-05 agenda repository tests (task 1.3) — RED first.

Constructor validation + compiled-SQL scoping run without a DB.
CRUD/soft-delete execution is Postgres-gated.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import asyncio
import inspect
import uuid

import pytest

from app.domain.agenda.models import (
    Bloqueo,
    Prestacion,
    Profesional,
    ProfesionalPrestacion,
    Sillon,
)
from app.domain.agenda.repositories import (
    BloqueoRepository,
    PrestacionRepository,
    ProfesionalPrestacionRepository,
    ProfesionalRepository,
    SillonRepository,
)
from app.infrastructure.repository import BaseRepository, TenantScopeError


def test_typed_repos_are_base_repositories() -> None:
    """WHEN typed repos inspected THEN each subclasses BaseRepository[T]."""
    for cls in (
        ProfesionalRepository,
        SillonRepository,
        PrestacionRepository,
        BloqueoRepository,
        ProfesionalPrestacionRepository,
    ):
        assert issubclass(cls, BaseRepository)


def test_repos_pin_model_and_require_tenant() -> None:
    """WHEN built without tenant THEN TenantScopeError (fail-closed)."""
    for cls in (
        ProfesionalRepository,
        SillonRepository,
        PrestacionRepository,
        BloqueoRepository,
        ProfesionalPrestacionRepository,
    ):
        with pytest.raises(TenantScopeError):
            cls(session=None, tenant_id=None)  # type: ignore[arg-type]
        with pytest.raises(TenantScopeError):
            cls(session=None, tenant_id="not-a-uuid")  # type: ignore[arg-type]


def test_repos_expose_tenant_and_model() -> None:
    """WHEN built with tenant THEN pinned; queries carry tenant scope."""
    tid = uuid.uuid4()
    cases = [
        (ProfesionalRepository, Profesional),
        (SillonRepository, Sillon),
        (PrestacionRepository, Prestacion),
        (BloqueoRepository, Bloqueo),
        (ProfesionalPrestacionRepository, ProfesionalPrestacion),
    ]
    for cls, model in cases:
        repo = cls(session=None, tenant_id=tid)
        assert repo.tenant_id == tid
        compiled = str(
            repo.query().compile(compile_kwargs={"literal_binds": True})
        )
        assert "tenant_id" in compiled
        assert str(tid).replace("-", "") in compiled
        assert model.__tablename__ in compiled


def test_link_repo_soft_delete_refused_physical_only() -> None:
    """WHEN soft_delete on link table THEN ValueError (physical DELETE only)."""
    tid = uuid.uuid4()
    repo = ProfesionalPrestacionRepository(session=None, tenant_id=tid)

    async def _run() -> None:
        with pytest.raises(ValueError, match="no deleted_at"):
            await repo.soft_delete(uuid.uuid4())

    asyncio.run(_run())


def test_link_repo_exposes_physical_remove() -> None:
    """WHEN link repo inspected THEN async remove() exists for enablement revoke."""
    assert inspect.iscoroutinefunction(ProfesionalPrestacionRepository.remove)


def test_include_deleted_stays_tenant_scoped() -> None:
    """WHEN include_deleted queried THEN tenant filter still present (2nd input)."""
    tid = uuid.uuid4()
    repo = BloqueoRepository(session=None, tenant_id=tid)
    compiled = str(
        repo.query(include_deleted=True).compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "tenant_id" in compiled
    assert "IS NULL" not in compiled  # no soft-delete WHERE when included


def test_add_stamps_missing_tenant_and_rejects_foreign() -> None:
    """WHEN add() called THEN stamps empty tenant, rejects foreign tenant."""
    tid = uuid.uuid4()
    repo = PrestacionRepository(session=None, tenant_id=tid)

    async def _run() -> None:
        stamped = Prestacion(nombre="X", duracion_min=30)
        assert stamped.tenant_id is None
        with pytest.raises(TenantScopeError):
            await repo.add(
                Prestacion(
                    tenant_id=uuid.uuid4(), nombre="Foreign", duracion_min=30
                )
            )

    asyncio.run(_run())


def test_pg_gated_crud_and_soft_delete_round_trip() -> None:
    """WHEN CRUD on live PG THEN create→read→soft-delete hides row."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")

    async def _run() -> None:
        import uuid as uuid_mod

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.domain.models import Base, Tenant
        from tests.c02_pg import pg_dsn

        engine = create_async_engine(pg_dsn())
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                tenant = Tenant(
                    slug_reserva="repo-c05-ficticia", nombre="Repo C05"
                )
                session.add(tenant)
                await session.commit()
                tid = tenant.id
                repo = PrestacionRepository(session=session, tenant_id=tid)
                created = await repo.add(
                    Prestacion(nombre="Limpieza Ficticia", duracion_min=45)
                )
                await session.commit()
                assert created.id is not None
                fetched = await repo.get(created.id)
                assert fetched is not None
                assert fetched.nombre == "Limpieza Ficticia"
                assert await repo.soft_delete(created.id) is True
                await session.commit()
                assert await repo.get(created.id) is None
                assert await repo.get(created.id, include_deleted=True) is not None
                assert await repo.soft_delete(uuid_mod.uuid4()) is False
        finally:
            await engine.dispose()

    asyncio.run(_run())
