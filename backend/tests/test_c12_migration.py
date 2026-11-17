"""C-12 tasks 1.2/1.3: migration 008 static + offline SQL checks."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend" / "alembic" / "versions"
REVISION_011 = "c11a1b2c3d4e5"
REVISION_012 = "c12a1b2c3d4e5"
TABLES = (
    "paciente",
    "historia_clinica",
    "evolucion",
    "derivacion_hce",
)


def _migration_012() -> Path:
    candidates = [p for p in VERSIONS.glob("*.py") if REVISION_012 in p.name]
    assert len(candidates) == 1, f"expected exactly one 012 file, got {candidates}"
    return candidates[0]


def _load_migration():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("c12_migration", _migration_012())
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alembic_sql(args: list[str]) -> str:
    completed = subprocess.run(
        ["alembic", *args, "--sql"],
        cwd=str(ROOT / "backend"),
        capture_output=True,
        text=True,
        timeout=120,
        env=dict(os.environ),
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return completed.stdout


def test_migration_chains_011() -> None:
    content = _migration_012().read_text(encoding="utf-8")
    assert re.search(rf"down_revision[^=]*=\s*[\"']{REVISION_011}[\"']", content)
    assert re.search(rf"revision[^=]*=\s*[\"']{REVISION_012}[\"']", content)


def test_rls_helper_covers_four_tables() -> None:
    module = _load_migration()
    assert tuple(module.TENANT_TABLES) == TABLES
    statements = module._rls_upgrade_sql()
    for table in TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in statements
        assert any(f"CREATE POLICY {table}_isolation" in s for s in statements)
    assert any("WITH CHECK" in s and "app.tenant_id" in s for s in statements)


def test_append_only_helper_has_function_and_triggers() -> None:
    module = _load_migration()
    statements = "\n".join(module._append_only_upgrade_sql())
    assert "CREATE OR REPLACE FUNCTION evolucion_append_only" in statements
    assert "BEFORE UPDATE ON evolucion" in statements
    assert "BEFORE DELETE ON evolucion" in statements
    assert "evolucion_no_update" in statements
    assert "evolucion_no_delete" in statements


def test_offline_upgrade_creates_tables_index_and_triggers() -> None:
    sql = _alembic_sql(["upgrade", "head"]).upper()
    for table in TABLES:
        assert f"CREATE TABLE {table.upper()}" in sql
    assert "CREATE UNIQUE INDEX UQ_PACIENTE_TENANT_DNI_ACTIVO" in sql
    assert "WHERE IS_ACTIVE AND DNI IS NOT NULL" in sql
    assert "UQ_HISTORIA_CLINICA_TENANT_PACIENTE" in sql
    assert "EVOLUCION_APPEND_ONLY" in sql
    assert "CREATE TRIGGER EVOLUCION_NO_UPDATE" in sql
    assert "CREATE TRIGGER EVOLUCION_NO_DELETE" in sql


def test_offline_downgrade_removes_c12_objects() -> None:
    sql = _alembic_sql(["downgrade", "head:base"]).upper()
    assert "DROP TRIGGER IF EXISTS EVOLUCION_NO_DELETE" in sql
    assert "DROP TRIGGER IF EXISTS EVOLUCION_NO_UPDATE" in sql
    assert "DROP FUNCTION IF EXISTS EVOLUCION_APPEND_ONLY" in sql
    for table in reversed(TABLES):
        assert f"DROP TABLE {table.upper()}" in sql


def test_pg_gated_append_only_rejects_update_and_delete() -> None:
    """WHEN UPDATE/DELETE run on live PG THEN the trigger rejects them."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    from tests.support_c12_db import run_append_only_scenario

    asyncio.run(run_append_only_scenario())
