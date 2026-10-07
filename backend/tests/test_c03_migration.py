"""C-03 Migración 002 tests (task 3.2) — RED first.

File-level + offline-SQL seams run without a DB. The live
upgrade/downgrade/upgrade cycle is Postgres-gated (honest SKIP without a
live DB; CI runs it).
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend" / "alembic" / "versions"
REVISION_001 = "c02a1b2c3d4e5"
REVISION_002 = "c03a1b2c3d4e5"


def _migration_002() -> Path:
    candidates = [p for p in VERSIONS.glob("*.py") if REVISION_002 in p.name]
    assert len(candidates) == 1, f"expected exactly one 002 file, got {candidates}"
    return candidates[0]


def _alembic_sql(args: list[str]) -> str:
    env = dict(os.environ)
    completed = subprocess.run(
        ["alembic", *args, "--sql"],
        cwd=str(ROOT / "backend"),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return completed.stdout


def test_migration_002_chains_001() -> None:
    """WHEN 002 inspected THEN down_revision is the C-02 head (manual chain)."""
    content = _migration_002().read_text(encoding="utf-8")
    assert re.search(rf"down_revision[^=]*=\s*[\"']{REVISION_001}[\"']", content)
    assert re.search(rf"revision[^=]*=\s*[\"']{REVISION_002}[\"']", content)


def test_offline_upgrade_creates_auth_tables() -> None:
    """WHEN offline upgrade SQL generated THEN revoked/portal tables created."""
    sql = _alembic_sql(["upgrade", "head"]).upper()
    assert "CREATE TABLE REVOKED_TOKEN" in sql
    assert "CREATE TABLE PORTAL_TOKEN" in sql


def test_offline_upgrade_portal_rls_revoked_global() -> None:
    """WHEN SQL inspected THEN portal_token RLS+FORCE, revoked_token global."""
    sql = _alembic_sql(["upgrade", "head"])
    upper = sql.upper()
    assert "ALTER TABLE PORTAL_TOKEN ENABLE ROW LEVEL SECURITY" in upper
    assert "ALTER TABLE PORTAL_TOKEN FORCE ROW LEVEL SECURITY" in upper
    assert "CREATE POLICY portal_token_isolation" in sql
    # D6 exception: revoked_token must NOT gain RLS (pre-auth jti lookup).
    assert "ALTER TABLE REVOKED_TOKEN ENABLE" not in upper
    assert "ALTER TABLE REVOKED_TOKEN FORCE" not in upper


def test_offline_upgrade_hardens_password_hash() -> None:
    """WHEN SQL inspected THEN marker migrated + password_hash SET NOT NULL."""
    sql = _alembic_sql(["upgrade", "head"])
    assert "!UNSET-" in sql, "data migration must neutralize the C-02 marker"
    assert re.search(
        r"ALTER\s+TABLE\s+usuario\s+ALTER\s+COLUMN\s+password_hash\s+SET\s+NOT\s+NULL",
        sql,
        re.IGNORECASE,
    ), "usuario.password_hash must become NOT NULL"


def test_offline_upgrade_adds_auth_lookup_function() -> None:
    """WHEN SQL inspected THEN the pre-auth lookup function is created."""
    sql = _alembic_sql(["upgrade", "head"])
    assert "CREATE FUNCTION auth_lookup_user" in sql
    assert "SECURITY DEFINER" in sql


def test_offline_downgrade_removes_002() -> None:
    """WHEN offline downgrade SQL generated THEN 002 tables/policy dropped."""
    sql = _alembic_sql(["downgrade", "head:base"]).upper()
    assert "DROP TABLE PORTAL_TOKEN" in sql
    assert "DROP TABLE REVOKED_TOKEN" in sql
    assert "DROP POLICY" in sql


def test_pg_gated_live_002_cycle() -> None:
    """WHEN live cycle runs on PG THEN 002 applies, reverts, re-applies."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from tests.c02_pg import pg_dsn
        from tests.support_c02_db import alembic_upgrade_head, pg_sqlalchemy_url
        from tests.support_c03_db import alembic_downgrade_001, alembic_upgrade_002

        dsn = pg_dsn()
        sa_url = pg_sqlalchemy_url(dsn)
        await alembic_upgrade_head(sa_url)
        engine = create_async_engine(dsn)
        try:
            async with engine.connect() as conn:
                tables = (
                    (
                        await conn.execute(
                            text(
                                "SELECT tablename FROM pg_tables "
                                "WHERE schemaname='public' AND tablename IN "
                                "('revoked_token','portal_token')"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert sorted(tables) == ["portal_token", "revoked_token"]
                rls = (
                    (
                        await conn.execute(
                            text(
                                "SELECT relname FROM pg_class "
                                "WHERE relname='portal_token' "
                                "AND relrowsecurity AND relforcerowsecurity"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert rls == ["portal_token"], "portal_token needs RLS+FORCE"
                no_rls = (
                    (
                        await conn.execute(
                            text(
                                "SELECT relname FROM pg_class "
                                "WHERE relname='revoked_token' "
                                "AND (relrowsecurity OR relforcerowsecurity)"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert no_rls == [], "revoked_token must stay global (D6)"
                not_null = (
                    await conn.execute(
                        text(
                            "SELECT is_nullable FROM information_schema.columns "
                            "WHERE table_name='usuario' "
                            "AND column_name='password_hash'"
                        )
                    )
                ).scalar()
                assert not_null == "NO"
            await alembic_downgrade_001(sa_url)
            async with engine.connect() as conn:
                tables = (
                    (
                        await conn.execute(
                            text(
                                "SELECT tablename FROM pg_tables "
                                "WHERE schemaname='public' AND tablename IN "
                                "('revoked_token','portal_token')"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert tables == []
            await alembic_upgrade_002(sa_url)
            async with engine.connect() as conn:
                tables = (
                    (
                        await conn.execute(
                            text(
                                "SELECT tablename FROM pg_tables "
                                "WHERE schemaname='public' AND tablename IN "
                                "('revoked_token','portal_token')"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert sorted(tables) == ["portal_token", "revoked_token"]
            # Leave the DB upgraded: suites after this file expect tables.
            await alembic_upgrade_head(sa_url)
        finally:
            await engine.dispose()

    asyncio.run(_run())
