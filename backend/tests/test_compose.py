"""Compose definition tests (C-01 task 2.3) — static YAML seams, no daemon."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _compose() -> str:
    return (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_compose_defines_four_services() -> None:
    """WHEN compose file inspected THEN api/worker/postgres/redis are defined."""
    content = _compose()
    for service in ("api:", "worker:", "postgres:", "redis:"):
        assert service in content, f"missing service: {service}"


def test_compose_has_healthchecks_named_volume_and_same_image() -> None:
    """WHEN compose file inspected THEN healthchecks + named volume exist."""
    content = _compose()
    assert "postgres:15" in content
    assert "pg_isready" in content
    assert "redis-cli" in content
    assert "ping" in content
    assert "healthcheck" in content.lower()
    assert "volumes:" in content
    assert "pgdata" in content
