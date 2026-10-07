"""C-05 RLS isolation tests (task 4.2) — RED first.

Static seams (RLS helper covers exactly the 5 model tables; repository
queries always carry the tenant filter) run without a DB. Raw enforcement
(insert A, read B → 0 rows) is Postgres-gated and SKIPs honestly locally.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.domain.agenda.models import Bloqueo, Prestacion, Profesional, Sillon
from app.domain.agenda.repositories import (
    BloqueoRepository,
    PrestacionRepository,
)
from app.domain.models import Base


def _migration_tables() -> tuple[str, ...]:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c05a1b2c3d4e5_c05_agenda_catalog.py"
    )
    spec = importlib.util.spec_from_file_location("c05_migration_rls", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.TENANT_TABLES)


def test_rls_cubre_exactamente_las_cinco_tablas_del_modelo() -> None:
    """WHEN migracion vs modelos THEN RLS en las 5 tablas del dominio."""
    model_tables = {
        Profesional.__tablename__,
        Sillon.__tablename__,
        "prestacion",
        "profesional_prestacion",
        Bloqueo.__tablename__,
    }
    assert set(_migration_tables()) == model_tables
    for name in model_tables:
        assert name in Base.metadata.tables


def test_repositorios_agenda_filtran_tenant_en_sql() -> None:
    """WHEN queries compiladas THEN filtro tenant_id presente (2 modelos)."""
    tid = uuid.uuid4()
    for repo in (
        PrestacionRepository(session=None, tenant_id=tid),
        BloqueoRepository(session=None, tenant_id=tid),
    ):
        compiled = str(repo.query().compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled
        assert str(tid).replace("-", "") in compiled


def test_pg_gated_inserta_a_lee_b_cero_filas() -> None:
    """WHEN fila en tenant A y lectura con GUC de B THEN 0 filas (RLS)."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")

    async def _run() -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.domain.models import Base, Tenant
        from tests.c02_pg import pg_dsn
        from tests.support_c02_db import delete_tenant_rows, pg_sqlalchemy_url

        dsn = pg_dsn()
        await __import__(
            "tests.support_c02_db", fromlist=["alembic_upgrade_head"]
        ).alembic_upgrade_head(pg_sqlalchemy_url(dsn))
        engine = create_async_engine(dsn)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as setup:
                tenant_a = Tenant(slug_reserva="rls-c05-a-ficticia", nombre="A")
                tenant_b = Tenant(slug_reserva="rls-c05-b-ficticia", nombre="B")
                setup.add_all([tenant_a, tenant_b])
                await setup.commit()
                aid, bid = tenant_a.id, tenant_b.id
            try:
                async with factory() as writer:
                    await writer.execute(
                        text("SELECT set_config('app.tenant_id', :tid, true)"),
                        {"tid": str(aid)},
                    )
                    writer.add(
                        Prestacion(
                            tenant_id=aid,
                            nombre="Solo A (ficticia)",
                            duracion_min=30,
                        )
                    )
                    await writer.commit()
                async with factory() as reader_b:
                    await reader_b.execute(
                        text("SELECT set_config('app.tenant_id', :tid, true)"),
                        {"tid": str(bid)},
                    )
                    names = (
                        (await reader_b.execute(text("SELECT nombre FROM prestacion")))
                        .scalars()
                        .all()
                    )
                    assert "Solo A (ficticia)" not in names
                    assert names == []
                # Sin GUC la politica falla cerrada (2do input: fail-closed).
                async with engine.connect() as raw:
                    with pytest.raises(Exception, match="app.tenant_id"):
                        await raw.execute(text("SELECT * FROM prestacion"))
            finally:
                async with factory() as cleanup:
                    await delete_tenant_rows(cleanup, aid)
                    await delete_tenant_rows(cleanup, bid)
        finally:
            await engine.dispose()

    import asyncio

    asyncio.run(_run())
