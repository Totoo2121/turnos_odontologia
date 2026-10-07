"""C-02 Migración 001 tests (tasks 3.1/3.2) — RED first.

File-level + offline-SQL seams run without a DB (``alembic ... --sql`` never
connects). The live upgrade/downgrade cycle is Postgres-gated and leaves the
DB downgraded (clean slate) so other suites stay order-independent.
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
BASELINE = "a1b2c3d4e5f6"
TABLES = ("tenant", "sucursal", "usuario", "rol", "user_rol")


def _migration_files() -> list[Path]:
    return [
        p
        for p in VERSIONS.glob("*.py")
        if p.name != "__init__.py" and BASELINE not in p.name
    ]


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


def test_offline_history_shows_baseline_then_001() -> None:
    """WHEN history inspected THEN baseline -> 001 chain is explicit."""
    completed = subprocess.run(
        ["alembic", "history"],
        cwd=str(ROOT / "backend"),
        capture_output=True,
        text=True,
        timeout=120,
        env=dict(os.environ),
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert BASELINE in completed.stdout
    assert "c02a1b2c3d4e5" in completed.stdout


def test_migration_001_chains_baseline() -> None:
    """WHEN versions inspected THEN the 001 file chains down_revision=baseline."""
    files = _migration_files()
    ones = [p for p in files if BASELINE in p.name or "c02a1b2c3d4e5" in p.name]
    assert len(ones) == 1, f"expected exactly one C-02 migration, got {ones}"
    content = ones[0].read_text(encoding="utf-8")
    assert re.search(
        rf"down_revision[^=]*=\s*[\"']{BASELINE}[\"']", content
    ), "migration must chain down_revision to the C-01 baseline"
    assert re.search(r"revision[^=]*=\s*[\"']c02a1b2c3d4e5[\"']", content)


def test_offline_upgrade_creates_five_tables_with_rls() -> None:
    """WHEN offline upgrade SQL generated THEN 5 tables + RLS/FORCE/policies."""
    sql = _alembic_sql(["upgrade", "head"]).upper()
    for table in TABLES:
        assert f"CREATE TABLE {table}".upper() in sql, f"missing CREATE TABLE {table}"
    for table in ("tenant", "sucursal", "usuario", "user_rol"):
        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert "FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY" in sql
    assert "CURRENT_SETTING('APP.TENANT_ID')" in sql


def test_offline_upgrade_policies_are_fail_closed() -> None:
    """WHEN policy SQL inspected THEN strict current_setting (no soft default)."""
    sql = _alembic_sql(["upgrade", "head"])
    assert "current_setting('app.tenant_id')" in sql
    # A `, true` default would turn "no context" into NULL→empty instead of
    # the fail-closed ERROR the design mandates (D1 risk mitigation).
    policies = [line for line in sql.splitlines() if "CREATE POLICY" in line]
    assert policies, "expected CREATE POLICY statements"
    for line in policies:
        assert "current_setting('app.tenant_id', true)" not in line


def test_offline_downgrade_drops_policies_and_tables() -> None:
    """WHEN offline downgrade SQL generated THEN policies + tables dropped."""
    sql = _alembic_sql(["downgrade", "head:base"]).upper()
    assert "DROP POLICY" in sql
    for table in TABLES:
        assert f"DROP TABLE {table}".upper() in sql, f"missing DROP TABLE {table}"


def test_pg_gated_live_upgrade_downgrade_cycle() -> None:
    """WHEN live cycle runs on PG THEN tables+RLS appear, vanish, reappear."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    async def _run() -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from tests.c02_pg import pg_dsn
        from tests.support_c02_db import (
            alembic_current,
            alembic_downgrade_baseline,
            alembic_upgrade_head,
            pg_sqlalchemy_url,
        )

        dsn = pg_dsn()
        await alembic_upgrade_head(pg_sqlalchemy_url(dsn))
        engine = create_async_engine(dsn)
        try:
            async with engine.connect() as conn:
                tables = (
                    (
                        await conn.execute(
                            text(
                                "SELECT tablename FROM pg_tables "
                                "WHERE schemaname='public' AND tablename IN "
                                "('tenant','sucursal','usuario','rol','user_rol')"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert sorted(tables) == sorted(TABLES)
                rls = (
                    (
                        await conn.execute(
                            text(
                                "SELECT relname FROM pg_class WHERE relname IN "
                                "('tenant','sucursal','usuario','user_rol') "
                                "AND relrowsecurity AND relforcerowsecurity"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert sorted(rls) == sorted(
                    ("tenant", "sucursal", "usuario", "user_rol")
                ), f"RLS+FORCE missing: {set(TABLES) - set(rls)}"
                policies = (
                    await conn.execute(
                        text(
                            "SELECT COUNT(*) FROM pg_policies "
                            "WHERE schemaname='public'"
                        )
                    )
                ).scalar()
                assert policies is not None and policies >= 4
            assert (await alembic_current(pg_sqlalchemy_url(dsn))).endswith(
                "c02a1b2c3d4e5"
            ) or "c02a1b2c3d4e5" in await alembic_current(pg_sqlalchemy_url(dsn))
            await alembic_downgrade_baseline(pg_sqlalchemy_url(dsn))
            async with engine.connect() as conn:
                tables = (
                    (
                        await conn.execute(
                            text(
                                "SELECT tablename FROM pg_tables "
                                "WHERE schemaname='public' AND tablename IN "
                                "('tenant','sucursal','usuario','rol','user_rol')"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert tables == []
            # Leave the DB upgraded: suites after this file expect tables.
            await alembic_upgrade_head(pg_sqlalchemy_url(dsn))
        finally:
            await engine.dispose()

    asyncio.run(_run())
