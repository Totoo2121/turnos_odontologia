"""Live-Postgres support for C-02 migration/RLS/seed scenarios.

In-process Alembic runs (upgrade/current/downgrade) plus the RLS
enforcement runner. Only imported by Postgres-gated tests that already
skipped when no DB is reachable.
"""

from __future__ import annotations

import contextlib
import io
import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "a1b2c3d4e5f6"
HEAD = "c02a1b2c3d4e5"


def pg_sqlalchemy_url(asyncpg_dsn: str) -> str:
    """Convert an asyncpg DSN to the SQLAlchemy async URL form."""
    prefix = "postgresql://"
    assert asyncpg_dsn.startswith(prefix), asyncpg_dsn
    return "postgresql+asyncpg://" + asyncpg_dsn[len(prefix) :]


def _alembic_config(sqlalchemy_url: str):  # type: ignore[no-untyped-def]
    from alembic.config import Config

    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return cfg


def _with_database_url(sqlalchemy_url: str):  # type: ignore[no-untyped-def]
    """Temporarily point settings at the target DB (restores afterwards)."""
    return _EnvOverride("DATABASE_URL", sqlalchemy_url)


class _EnvOverride:
    def __init__(self, key: str, value: str) -> None:
        self._key = key
        self._value = value
        self._had = False
        self._old: str | None = None

    def __enter__(self) -> None:
        self._had = self._key in os.environ
        self._old = os.environ.get(self._key)
        os.environ[self._key] = self._value

    def __exit__(self, *args: object) -> None:
        if self._had:
            assert self._old is not None
            os.environ[self._key] = self._old
        else:
            os.environ.pop(self._key, None)


async def alembic_upgrade_head(sqlalchemy_url: str) -> None:
    """Apply all migrations up to the C-02 head on the target DB."""
    from alembic import command

    with _with_database_url(sqlalchemy_url):
        command.upgrade(_alembic_config(sqlalchemy_url), "head")


async def alembic_downgrade_baseline(sqlalchemy_url: str) -> None:
    """Downgrade back to the C-01 baseline (removes the 5 C-02 tables)."""
    from alembic import command

    with _with_database_url(sqlalchemy_url):
        command.downgrade(_alembic_config(sqlalchemy_url), BASELINE)


async def alembic_current(sqlalchemy_url: str) -> str:
    """Capture `alembic current` output on the target DB."""
    from alembic import command

    buffer = io.StringIO()
    with _with_database_url(sqlalchemy_url):
        with contextlib.redirect_stdout(buffer):
            command.current(_alembic_config(sqlalchemy_url))
    return buffer.getvalue()


async def delete_tenant_rows(session: object, tenant_id: uuid.UUID) -> None:
    """Delete every row of one tenant (GUC-aware: works with RLS enforced)."""
    from sqlalchemy import delete, text

    from app.domain.models import Sucursal, Tenant, UserRol, Usuario

    await session.execute(  # type: ignore[attr-defined]
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )
    for model, column in (
        (UserRol, UserRol.tenant_id),
        (Usuario, Usuario.tenant_id),
        (Sucursal, Sucursal.tenant_id),
    ):
        await session.execute(delete(model).where(column == tenant_id))  # type: ignore[attr-defined]
    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))  # type: ignore[attr-defined]
    await session.commit()  # type: ignore[attr-defined]


async def run_rls_enforcement(kind: str) -> None:
    """Run one RLS enforcement scenario on live Postgres (policies required)."""
    import pytest
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.domain.models import Tenant
    from app.infrastructure.repository import UnitOfWork
    from tests.c02_pg import pg_dsn

    dsn = pg_dsn()
    sa_url = pg_sqlalchemy_url(dsn)
    await alembic_upgrade_head(sa_url)
    engine = create_async_engine(dsn)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as setup:
            tenant_a = Tenant(slug_reserva="rls-a-ficticia", nombre="RLS A")
            tenant_b = Tenant(slug_reserva="rls-b-ficticia", nombre="RLS B")
            setup.add_all([tenant_a, tenant_b])
            await setup.commit()
            aid, bid = tenant_a.id, tenant_b.id
        try:
            if kind == "no_guc_denied":
                async with engine.connect() as raw:
                    with pytest.raises(Exception, match="app.tenant_id"):
                        await raw.execute(text("SELECT * FROM sucursal"))
            elif kind == "guc_scoped":
                from app.domain.models import Sucursal

                async with UnitOfWork(factory, aid) as uow_a:
                    await uow_a.repo(Sucursal).add(Sucursal(nombre="Solo A"))
                async with UnitOfWork(factory, bid) as uow_b:
                    await uow_b.repo(Sucursal).add(Sucursal(nombre="Solo B"))
                for tid, expected, unexpected in (
                    (aid, "Solo A", "Solo B"),
                    (bid, "Solo B", "Solo A"),
                ):
                    async with factory() as scoped:
                        await scoped.execute(
                            text("SELECT set_config('app.tenant_id', :tid, true)"),
                            {"tid": str(tid)},
                        )
                        names = (
                            (await scoped.execute(text("SELECT nombre FROM sucursal")))
                            .scalars()
                            .all()
                        )
                        assert expected in names
                        assert unexpected not in names
            else:
                raise AssertionError(f"unknown scenario: {kind}")
        finally:
            async with factory() as cleanup:
                await delete_tenant_rows(cleanup, aid)
                await delete_tenant_rows(cleanup, bid)
    finally:
        await engine.dispose()
