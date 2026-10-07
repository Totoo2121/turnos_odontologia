"""C-05 migration 003 tests (task 1.2) — RED first.

Static seams (revision chain, RLS/FORCE/policies, indexes, CHECKs) run
without a DB by inspecting the migration module source. The live
upgrade→downgrade→upgrade cycle is Postgres-gated and SKIPs honestly
when no live DB is reachable.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import importlib
from pathlib import Path

import pytest

REVISION = "c05a1b2c3d4e5"
DOWN_REVISION = "c03a1b2c3d4e5"
TABLES = ("profesional", "sillon", "prestacion", "profesional_prestacion", "bloqueo")


def _load_migration():  # type: ignore[no-untyped-def]
    """Import the migration module by path (alembic versions dir)."""
    import importlib.util

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c05a1b2c3d4e5_c05_agenda_catalog.py"
    )
    assert path.exists(), f"missing migration file: {path}"
    spec = importlib.util.spec_from_file_location("c05_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source() -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c05a1b2c3d4e5_c05_agenda_catalog.py"
    )
    return path.read_text(encoding="utf-8")


def test_revision_chain_links_c03_to_c05() -> None:
    """WHEN migration inspected THEN revision/down_revision chain C-03→C-05."""
    module = _load_migration()
    assert module.revision == REVISION
    assert module.down_revision == DOWN_REVISION


def test_upgrade_and_downgrade_are_callable() -> None:
    """WHEN migration inspected THEN upgrade/downgrade are reversible entrypoints."""
    module = _load_migration()
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_all_five_tables_created() -> None:
    """WHEN upgrade source inspected THEN all 5 tables are created."""
    source = _source()
    for table in TABLES:
        assert f'"{table}"' in source or f"'{table}'" in source, (
            f"missing create_table: {table}"
        )


def test_rls_and_force_rls_on_all_five_tables() -> None:
    """WHEN RLS helper inspected THEN ENABLE+FORCE RLS emitted for every table."""
    module = _load_migration()
    assert tuple(module.TENANT_TABLES) == TABLES
    statements = module._rls_upgrade_sql()
    for table in TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in statements
    source = _source()
    assert "_rls_upgrade_sql()" in source  # upgrade() applies the helper


def test_isolation_policy_on_all_five_tables() -> None:
    """WHEN RLS helper inspected THEN tenant isolation policy per table."""
    module = _load_migration()
    statements = module._rls_upgrade_sql()
    for table in TABLES:
        assert any(
            f"CREATE POLICY {table}_isolation" in stmt for stmt in statements
        ), f"missing policy: {table}_isolation"
    assert any("app.tenant_id" in stmt for stmt in statements)
    assert any("WITH CHECK" in stmt for stmt in statements)
    dropped = module._rls_downgrade_sql()
    assert len(dropped) == len(TABLES)


def test_required_indexes_present() -> None:
    """WHEN upgrade source inspected THEN (tenant_id,nombre/prof/inicio) indexes."""
    source = _source()
    for fragment in (
        '"tenant_id", "nombre"',
        '"profesional_id"',
        '"sillon_id", "inicio"',
    ):
        assert fragment in source, f"missing index fragment: {fragment}"


def test_check_constraints_mirrored() -> None:
    """WHEN upgrade source inspected THEN duracion/fin/motivo CHECKs mirrored."""
    source = _source()
    assert "duracion_min > 0" in source
    assert "fin > inicio" in source
    assert "feriado" in source


def test_single_head_no_branch_labels() -> None:
    """WHEN migration inspected THEN linear history (no branches)."""
    module = _load_migration()
    assert module.branch_labels in (None, [])


def test_pg_gated_upgrade_downgrade_upgrade_cycle() -> None:
    """WHEN cycled on live PG THEN head→-1→head applies cleanly (003 only)."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")

    async def _run() -> None:
        from tests.support_c02_db import _alembic_config, _with_database_url, pg_sqlalchemy_url
        from tests.c02_pg import pg_dsn
        from alembic import command

        sa_url = pg_sqlalchemy_url(pg_dsn())
        cfg = _alembic_config(sa_url)
        with _with_database_url(sa_url):
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "-1")
            command.upgrade(cfg, "head")

    import asyncio

    asyncio.run(_run())
