"""C-13 tasks 1.2/1.3: migration 009 static + offline SQL checks."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend" / "alembic" / "versions"
REVISION_012 = "c12a1b2c3d4e5"
REVISION_013 = "c13a1b2c3d4e5"
TABLES = ("odontograma", "evento_pieza", "adjunto", "consentimiento")


def _migration_013() -> Path:
    candidates = [p for p in VERSIONS.glob("*.py") if REVISION_013 in p.name]
    assert len(candidates) == 1, f"expected exactly one 013 file, got {candidates}"
    return candidates[0]


def _load_migration():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("c13_migration", _migration_013())
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


def test_migration_chains_012() -> None:
    content = _migration_013().read_text(encoding="utf-8")
    assert re.search(
        rf"down_revision[^=]*=\s*[\"']{REVISION_012}[\"']", content
    )
    assert re.search(rf"revision[^=]*=\s*[\"']{REVISION_013}[\"']", content)


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
    assert "CREATE OR REPLACE FUNCTION evento_pieza_append_only" in statements
    assert "BEFORE UPDATE ON evento_pieza" in statements
    assert "BEFORE DELETE ON evento_pieza" in statements
    assert "evento_pieza_no_update" in statements
    assert "evento_pieza_no_delete" in statements


def test_offline_upgrade_creates_tables_indexes_and_triggers() -> None:
    sql = _alembic_sql(["upgrade", "head"]).upper()
    for table in TABLES:
        assert f"CREATE TABLE {table.upper()}" in sql
    assert "UQ_ODONTOGRAMA_TENANT_HISTORIA" in sql
    assert "IX_EVENTO_PIEZA_ESTADO_ACTUAL" in sql
    assert "IX_CONSENTIMIENTO_PACIENTE_INVASIVO" in sql
    assert "EVENTO_PIEZA_APPEND_ONLY" in sql
    assert "CREATE TRIGGER EVENTO_PIEZA_NO_UPDATE" in sql
    assert "CREATE TRIGGER EVENTO_PIEZA_NO_DELETE" in sql
    assert "CREATE POLICY ADJUNTO_ISOLATION" in sql


def test_offline_downgrade_removes_c13_objects() -> None:
    sql = _alembic_sql(["downgrade", "head:base"]).upper()
    assert "DROP TRIGGER IF EXISTS EVENTO_PIEZA_NO_DELETE" in sql
    assert "DROP TRIGGER IF EXISTS EVENTO_PIEZA_NO_UPDATE" in sql
    assert "DROP FUNCTION IF EXISTS EVENTO_PIEZA_APPEND_ONLY" in sql
    for table in reversed(TABLES):
        assert f"DROP TABLE {table.upper()}" in sql


def test_pg_gated_append_only_rejects_update_and_delete() -> None:
    """WHEN UPDATE/DELETE run on live PG THEN the trigger rejects them."""
    from tests.c02_pg import pg_available

    if not pg_available():
        pytest.skip("BLOCKED locally: no live Postgres (CI runs this)")
    import asyncio

    from tests.support_c13_db import run_append_only_scenario

    asyncio.run(run_append_only_scenario())
