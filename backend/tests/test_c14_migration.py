"""C-14 tasks 1.3/1.4: migration 010 static + offline SQL checks."""

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

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend" / "alembic" / "versions"
REVISION_013 = "c13a1b2c3d4e5"
REVISION_014 = "d14a1b2c3d4e5"
TABLES = (
    "presupuesto",
    "presupuesto_item",
    "plan_tratamiento",
    "cuenta_corriente",
    "movimiento_cc",
)


def _migration_014() -> Path:
    candidates = [p for p in VERSIONS.glob("*.py") if REVISION_014 in p.name]
    assert len(candidates) == 1, f"expected exactly one 014 file, got {candidates}"
    return candidates[0]


def _load_migration():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "c14_migration", _migration_014()
    )
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


def test_migration_chains_013() -> None:
    content = _migration_014().read_text(encoding="utf-8")
    assert re.search(
        rf"down_revision[^=]*=\s*[\"']{REVISION_013}[\"']", content
    )
    assert re.search(rf"revision[^=]*=\s*[\"']{REVISION_014}[\"']", content)


def test_rls_helper_covers_five_tables() -> None:
    module = _load_migration()
    assert tuple(module.TENANT_TABLES) == TABLES
    statements = module._rls_upgrade_sql()
    for table in TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in statements
        assert any(f"CREATE POLICY {table}_isolation" in s for s in statements)
    assert any("WITH CHECK" in s and "app.tenant_id" in s for s in statements)


def test_triggers_cover_ledger_and_items() -> None:
    module = _load_migration()
    statements = "\n".join(module._trigger_upgrade_sql())
    assert "CREATE OR REPLACE FUNCTION movimiento_cc_append_only" in statements
    assert "BEFORE UPDATE ON movimiento_cc" in statements
    assert "BEFORE DELETE ON movimiento_cc" in statements
    assert "movimiento_cc_no_update" in statements
    assert "movimiento_cc_no_delete" in statements
    assert "CREATE OR REPLACE FUNCTION presupuesto_item_guard" in statements
    assert "BEFORE UPDATE ON presupuesto_item" in statements
    assert "BEFORE DELETE ON presupuesto_item" in statements
    assert "presupuesto_item_no_update" in statements
    assert "presupuesto_item_no_delete" in statements
    assert "estado_padre IS NOT NULL" in statements


def test_offline_upgrade_adds_column_tables_and_policies() -> None:
    sql = _alembic_sql(["upgrade", REVISION_014]).upper()
    assert "ALTER TABLE PRESTACION ADD COLUMN REQUIERE_CONSENTIMIENTO" in sql
    for table in TABLES:
        assert f"CREATE TABLE {table.upper()}" in sql
    assert "UQ_PLAN_TENANT_PRESUPUESTO" in sql
    assert "UQ_CC_TENANT_PACIENTE" in sql
    assert "UQ_MOVIMIENTO_CC_TENANT_REFERENCIA" in sql
    assert "IX_PRESUPUESTO_ITEM_TENANT_PRESUPUESTO_ETAPA" in sql
    assert "IX_MOVIMIENTO_CC_TENANT_CUENTA_OCURRIDO" in sql
    assert "CREATE TRIGGER MOVIMIENTO_CC_NO_UPDATE" in sql
    assert "CREATE TRIGGER PRESUPUESTO_ITEM_NO_DELETE" in sql
    assert "CREATE POLICY CUENTA_CORRIENTE_ISOLATION" in sql


def test_offline_downgrade_removes_c14_objects() -> None:
    sql = _alembic_sql(["downgrade", f"{REVISION_014}:{REVISION_013}"]).upper()
    assert "DROP TRIGGER IF EXISTS MOVIMIENTO_CC_NO_DELETE" in sql
    assert "DROP TRIGGER IF EXISTS PRESUPUESTO_ITEM_NO_UPDATE" in sql
    assert "DROP FUNCTION IF EXISTS MOVIMIENTO_CC_APPEND_ONLY()" in sql
    assert "DROP FUNCTION IF EXISTS PRESUPUESTO_ITEM_GUARD()" in sql
    for table in reversed(TABLES):
        assert f"DROP TABLE {table.upper()}" in sql
    assert "DROP COLUMN REQUIERE_CONSENTIMIENTO" in sql
