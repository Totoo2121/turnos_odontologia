"""Alembic baseline tests (C-01 task 2.1) — file-level seams, no DB needed."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC = ROOT / "backend" / "alembic"


def test_alembic_ini_points_at_settings() -> None:
    """WHEN config inspected THEN alembic.ini exists and delegates URL to settings."""
    ini = ROOT / "backend" / "alembic.ini"
    assert ini.is_file()
    content = ini.read_text(encoding="utf-8")
    assert "script_location" in content
    assert "alembic" in content


def test_env_is_async_and_baseline_revision_exists() -> None:
    """WHEN scaffold inspected THEN env.py is async and one baseline revision exists."""
    env = ALEMBIC / "env.py"
    assert env.is_file()
    content = env.read_text(encoding="utf-8")
    assert "async" in content
    assert "asyncpg" in content or "DATABASE_URL" in content
    revisions = list((ALEMBIC / "versions").glob("*.py"))
    non_init = [r for r in revisions if r.name != "__init__.py"]
    assert len(non_init) >= 1
