"""C-02 seed tests (tasks 4.1/4.2) — RED first.

Marker/TODO/dependency seams run without a DB. Double-run idempotency is
Postgres-gated (honest SKIP without a live DB). All seed data is fictitious.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.domain.models import PASSWORD_UNSET_MARKER
from app.infrastructure import seed_c02 as seed_module


def test_seed_exposes_idempotent_entrypoint() -> None:
    """WHEN seed module inspected THEN seed_c02 coroutine + demo constants."""
    import asyncio

    assert asyncio.iscoroutinefunction(seed_module.seed_c02)
    assert seed_module.DEMO_SLUG == "demo-ficticia"
    assert seed_module.ADMIN_EMAIL == "admin@demo-ficticia.invalid"
    assert seed_module.ADMIN_EMAIL.endswith(".invalid")


def test_seed_uses_unset_marker_and_declares_c03_todo() -> None:
    """WHEN seed source read THEN UNSET marker used + C-03 TODO traceable."""
    from pathlib import Path

    source = Path(seed_module.__file__).read_text(encoding="utf-8")
    assert "PASSWORD_UNSET_MARKER" in source
    assert PASSWORD_UNSET_MARKER == "!UNSET-C03*"
    assert "TODO(C-03)" in source
    assert "NOT NULL" in source
    assert "admin@demo-ficticia.invalid" in source


def test_seed_authenticates_nothing() -> None:
    """WHEN seed source read THEN no login/verify/JWT path consumes the marker."""
    from pathlib import Path

    source = Path(seed_module.__file__).read_text(encoding="utf-8").lower()
    assert "verify_password" not in source
    assert "check_password" not in source
    assert "create_access_token" not in source
    assert "login" not in source


def test_seed_role_catalog_is_complete() -> None:
    """WHEN role descriptions inspected THEN every catalog role has one."""
    from app.domain.models import ROLE_NAMES

    assert set(seed_module.ROLE_DESCRIPTIONS) == set(ROLE_NAMES)
    assert all(seed_module.ROLE_DESCRIPTIONS[name] for name in ROLE_NAMES)


def test_pg_gated_double_seed_is_idempotent() -> None:
    """WHEN seed runs twice on live PG THEN 1 tenant + 4 roles + 1 admin."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy import delete, func, select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.domain.models import Base, Rol, Tenant, UserRol, Usuario
        from tests.c02_pg import pg_dsn
        from tests.support_c02_db import delete_tenant_rows

        engine = create_async_engine(pg_dsn())
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as first:
                summary = await seed_module.seed_c02(first)
                await first.commit()
                assert summary["tenants"] >= 1
                assert summary["roles"] == 4
            async with factory() as second:
                summary2 = await seed_module.seed_c02(second)
                await second.commit()
                assert summary2["tenants"] >= 1
                assert summary2["roles"] == 4
            async with factory() as check:
                tenants = (
                    (
                        await check.execute(
                            select(Tenant).where(
                                Tenant.slug_reserva == seed_module.DEMO_SLUG
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(tenants) == 1
                demo = tenants[0]
                assert demo.moneda == "ARS"
                role_count = (
                    await check.execute(select(func.count()).select_from(Rol))
                ).scalar()
                assert role_count == 4
                admins = (
                    (
                        await check.execute(
                            select(Usuario).where(
                                Usuario.tenant_id == demo.id,
                                Usuario.email == seed_module.ADMIN_EMAIL,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(admins) == 1
                assert admins[0].password_hash == PASSWORD_UNSET_MARKER
                assert admins[0].is_active is True
                link = (
                    await check.execute(
                        select(UserRol, Rol)
                        .join(Rol, UserRol.rol_id == Rol.id)
                        .where(UserRol.usuario_id == admins[0].id)
                    )
                ).all()
                assert len(link) == 1
                assert link[0][1].nombre == "propietario"
                assert link[0][0].tenant_id == demo.id
            async with factory() as cleanup:
                # Remove demo tenant rows; drop the global role catalog rows.
                await delete_tenant_rows(cleanup, demo.id)
                await cleanup.execute(delete(Rol))
                await cleanup.commit()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_run())
