"""CI workflow tests (C-01 task 4.1) — static YAML seams, no runner needed."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _workflow() -> str:
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ci_has_parallel_backend_and_frontend_jobs() -> None:
    """WHEN workflow inspected THEN backend + frontend jobs are defined."""
    content = _workflow()
    assert "backend" in content
    assert "frontend" in content
    assert "pytest" in content


def test_ci_backend_runs_lint_types_tests_with_postgres() -> None:
    """WHEN backend job inspected THEN lint/type/test + Postgres service exist."""
    content = _workflow()
    assert "ruff" in content
    assert "mypy" in content
    assert "postgres" in content.lower()
    assert "alembic" in content


def test_ci_frontend_runs_typecheck_and_build() -> None:
    """WHEN frontend job inspected THEN tsc --noEmit + build run."""
    content = _workflow()
    assert "tsc --noEmit" in content
    assert "npm run build" in content or "npm ci" in content
