"""C-11 task 1.3: migration 007 static + offline SQL checks."""

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
REVISION_010 = "c10a1b2c3d4e5"
REVISION_011 = "c11a1b2c3d4e5"
TABLES = ("plantilla_mensaje", "recordatorio")


def _migration_011() -> Path:
    candidates = [p for p in VERSIONS.glob("*.py") if REVISION_011 in p.name]
    assert len(candidates) == 1, f"expected exactly one 011 file, got {candidates}"
    return candidates[0]


def _load_migration():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("c11_migration", _migration_011())
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


def test_migration_chains_010() -> None:
    content = _migration_011().read_text(encoding="utf-8")
    assert re.search(rf"down_revision[^=]*=\s*[\"']{REVISION_010}[\"']", content)
    assert re.search(rf"revision[^=]*=\s*[\"']{REVISION_011}[\"']", content)


def test_rls_helper_covers_both_tables() -> None:
    module = _load_migration()
    assert tuple(module.TENANT_TABLES) == TABLES
    statements = module._rls_upgrade_sql()
    for table in TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in statements
        assert any(f"CREATE POLICY {table}_isolation" in s for s in statements)
    assert any("WITH CHECK" in s and "app.tenant_id" in s for s in statements)


def test_offline_upgrade_creates_tables_and_columns() -> None:
    sql = _alembic_sql(["upgrade", "head"]).upper()
    assert "CREATE TABLE PLANTILLA_MENSAJE" in sql
    assert "CREATE TABLE RECORDATORIO" in sql
    assert "CONTACTO_WHATSAPP" in sql
    assert "CONTACTO_EMAIL" in sql
    assert "CONFIRMADO_AT" in sql
    assert "INTERVALO_CONTROL_DIAS" in sql


def test_offline_downgrade_removes_c11_objects() -> None:
    sql = _alembic_sql(["downgrade", "head:base"]).upper()
    assert "DROP TABLE RECORDATORIO" in sql
    assert "DROP TABLE PLANTILLA_MENSAJE" in sql
