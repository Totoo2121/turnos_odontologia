"""C-10 Migración tests (task 1.1) — RED first."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend" / "alembic" / "versions"
REVISION_009 = "c09a1b2c3d4e5"
REVISION_010 = "c10a1b2c3d4e5"


def _migration_010() -> Path:
    candidates = [p for p in VERSIONS.glob("*.py") if REVISION_010 in p.name]
    assert len(candidates) == 1, f"expected exactly one 010 file, got {candidates}"
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


def test_migration_010_chains_009() -> None:
    content = _migration_010().read_text(encoding="utf-8")
    assert re.search(rf"down_revision[^=]*=\s*[\"']{REVISION_009}[\"']", content)
    assert re.search(rf"revision[^=]*=\s*[\"']{REVISION_010}[\"']", content)


def test_offline_upgrade_creates_pago_table() -> None:
    sql = _alembic_sql(["upgrade", "head"]).upper()
    assert "CREATE TABLE PAGO" in sql


def test_offline_upgrade_adds_mp_order_id_to_turno() -> None:
    sql = _alembic_sql(["upgrade", "head"]).upper()
    assert "MP_ORDER_ID" in sql


def test_offline_upgrade_pago_rls() -> None:
    sql = _alembic_sql(["upgrade", "head"]).upper()
    assert "ALTER TABLE PAGO ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE PAGO FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY PAGO_ISOLATION" in sql


def test_offline_upgrade_pago_unique_mp_payment_id() -> None:
    sql = _alembic_sql(["upgrade", "head"]).upper()
    assert "UQ_PAGO_MP_PAYMENT_ID" in sql or "UNIQUE" in sql


def test_offline_downgrade_removes_pago() -> None:
    sql = _alembic_sql(["downgrade", "head:base"]).upper()
    assert "DROP TABLE PAGO" in sql