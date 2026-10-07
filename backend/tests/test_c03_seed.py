"""C-03 seed rotation tests (task 3.3) — RED first.

`ADMIN_INITIAL_PASSWORD` (deny-listed) becomes the demo-admin argon2id hash,
idempotently. Env/deny-list seams run without a DB; the double-run + login
round-trip is Postgres-gated (honest SKIP without a live DB; CI runs it).
All values fictitious (`.invalid` domain).
"""

from __future__ import annotations

import pytest


def test_resolve_admin_password_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN ADMIN_INITIAL_PASSWORD unset THEN resolution refuses (fail-closed)."""
    from app.infrastructure.seed_c03 import SeedError, resolve_admin_password

    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    with pytest.raises(SeedError, match="ADMIN_INITIAL_PASSWORD"):
        resolve_admin_password()


def test_resolve_admin_password_rejects_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN ADMIN_INITIAL_PASSWORD is a placeholder THEN resolution refuses."""
    from app.infrastructure.seed_c03 import SeedError, resolve_admin_password

    for placeholder in ("changeme", "CHANGEME-xxx", "admin", "password1"):
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", placeholder)
        with pytest.raises(SeedError, match="placeholder"):
            resolve_admin_password()


def test_resolve_admin_password_accepts_strong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN ADMIN_INITIAL_PASSWORD is strong THEN it resolves verbatim."""
    from app.infrastructure.seed_c03 import resolve_admin_password

    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "Str0ng!Fictitious-Seed-9")
    assert resolve_admin_password() == "Str0ng!Fictitious-Seed-9"


def test_pg_gated_rotate_is_idempotent_with_login() -> None:
    """WHEN rotate runs twice on PG THEN single admin + password logs in."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy import func, select
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.domain.models import Usuario
        from app.infrastructure import seed_c02
        from app.infrastructure.security import verify_password
        from app.infrastructure.seed_c03 import rotate_admin_password
        from app.shared.db import create_session_factory
        from tests.c02_pg import pg_dsn
        from tests.support_c02_db import (
            alembic_upgrade_head,
            delete_tenant_rows,
            pg_sqlalchemy_url,
        )

        dsn = pg_dsn()
        sa_url = pg_sqlalchemy_url(dsn)
        await alembic_upgrade_head(sa_url)
        engine = create_async_engine(sa_url)
        try:
            import os

            os.environ["DATABASE_URL"] = sa_url
            os.environ["ADMIN_INITIAL_PASSWORD"] = "Str0ng!Fictitious-Seed-9"
            try:
                factory = create_session_factory(engine)
                async with factory() as session:
                    first = await rotate_admin_password(session)
                    await session.commit()
                    second = await rotate_admin_password(session)
                    await session.commit()
                    assert first["admins"] == 1
                    assert second["rotated"] is False  # idempotent double-run
                    count = (
                        await session.execute(
                            select(func.count())
                            .select_from(Usuario)
                            .where(Usuario.email == seed_c02.ADMIN_EMAIL)
                        )
                    ).scalar()
                    assert count == 1
                    stored = (
                        await session.execute(
                            select(Usuario).where(Usuario.email == seed_c02.ADMIN_EMAIL)
                        )
                    ).scalar_one()
                    assert stored.password_hash is not None
                    assert not stored.password_hash.startswith("!")
                    assert verify_password(
                        stored.password_hash, "Str0ng!Fictitious-Seed-9"
                    )
                async with factory() as cleanup:
                    tenant_id = (
                        await cleanup.execute(
                            select(Usuario.tenant_id).where(
                                Usuario.email == seed_c02.ADMIN_EMAIL
                            )
                        )
                    ).scalar_one()
                    await delete_tenant_rows(cleanup, tenant_id)
            finally:
                os.environ.pop("ADMIN_INITIAL_PASSWORD", None)
        finally:
            await engine.dispose()

    asyncio.run(_run())
