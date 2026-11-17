"""C-17 migration and tenant-boundary contract checks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db")
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend" / "alembic" / "versions"


def test_c17_and_c18_migrations_are_a_linear_chain() -> None:
    c17 = next(VERSIONS.glob("*e17a1b2c3d4e5*.py"))
    c18 = next(VERSIONS.glob("*f18a1b2c3d4e5*.py"))
    assert 'down_revision: str | Sequence[str] | None = "d14a1b2c3d4e5"' in c17.read_text(encoding="utf-8")
    assert 'down_revision: str | Sequence[str] | None = "e17a1b2c3d4e5"' in c18.read_text(encoding="utf-8")


def test_audit_migration_has_forced_rls_and_update_delete_truncate_guards() -> None:
    source = next(VERSIONS.glob("*e17a1b2c3d4e5*.py")).read_text(encoding="utf-8")
    assert 'op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))' in source
    assert 'op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))' in source
    assert '_rls("audit_evento")' in source
    assert "BEFORE UPDATE OR DELETE ON audit_evento" in source
    assert "BEFORE TRUNCATE ON audit_evento" in source
    assert "tenant_id = {TENANT_GUC}" in source


def test_c18_upgrade_keeps_existing_obra_social_and_reserves_tables() -> None:
    source = next(VERSIONS.glob("*f18a1b2c3d4e5*.py")).read_text(encoding="utf-8")
    assert 'op.create_table(\n        "nomenclador"' in source
    assert 'op.create_table(\n        "comprobante_fiscal"' in source
    assert 'op.add_column("paciente", "obra_social"' not in source
    assert "ENABLE ROW LEVEL SECURITY" in source and "FORCE ROW LEVEL SECURITY" in source


def test_offline_upgrade_reaches_c18_head() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "f18a1b2c3d4e5", "--sql"],
        cwd=str(ROOT / "backend"), capture_output=True, text=True,
        timeout=120, env=dict(os.environ),
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    sql = completed.stdout.upper()
    for table in ("AUDIT_EVENTO", "EXPORTACION", "NOMENCLADOR", "COMPROBANTE_FISCAL"):
        assert f"CREATE TABLE {table}" in sql
