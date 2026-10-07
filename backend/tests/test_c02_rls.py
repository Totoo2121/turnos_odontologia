"""C-02 RLS enforcement test (task 3.3) — RED first.

Dedicated enforcement scenarios: a session WITHOUT the tenant GUC must fail
closed (error, never cross-tenant rows); a session WITH the GUC pinned to a
tenant sees only that tenant's rows. Both need live Postgres (+ Migración
001 applied) and SKIP honestly without one.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest


def test_migration_source_enforces_fail_closed() -> None:
    """WHEN migration sources read THEN strict GUC + FORCE RLS documented."""
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = [
        p
        for p in versions.glob("*.py")
        if "a1b2c3d4e5f6" not in p.name and p.name != "__init__.py"
    ]
    # C-03 adds Migración 002 alongside 001: EVERY tenant migration (not just
    # the first) must carry the fail-closed RLS shape.
    assert len(matches) >= 1
    assert {p.name for p in matches} >= {
        "c02a1b2c3d4e5_c02_core_multitenant.py",
        "c03a1b2c3d4e5_c03_identity_auth.py",
    }
    for migration in matches:
        content = migration.read_text(encoding="utf-8")
        assert "FORCE ROW LEVEL SECURITY" in content, migration.name
        assert "current_setting('app.tenant_id')" in content, migration.name


def test_pg_gated_no_guc_session_fails_closed() -> None:
    """WHEN a live session without GUC reads THEN denied (fail-closed)."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    from tests.support_c02_db import run_rls_enforcement

    asyncio.run(run_rls_enforcement("no_guc_denied"))


def test_pg_gated_guc_session_sees_only_own_tenant() -> None:
    """WHEN GUC pinned to tenant A on live PG THEN only A's rows visible."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    from tests.support_c02_db import run_rls_enforcement

    asyncio.run(run_rls_enforcement("guc_scoped"))
