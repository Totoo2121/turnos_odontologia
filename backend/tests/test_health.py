"""Health endpoint tests (C-01 task 1.3) — no auth, no patient data."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_ok_json() -> None:
    """WHEN API alive THEN GET /api/health responds 200 {"status": "ok"} as JSON."""
    response = _client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")


def test_health_requires_no_auth() -> None:
    """WHEN anonymous without token THEN health still responds 200 (never 401/403)."""
    response = _client().get("/api/health")
    assert response.status_code == 200
    assert response.status_code not in (401, 403)


def test_unknown_route_returns_json_error_shape() -> None:
    """WHEN unknown route THEN base exception handler returns JSON error (not HTML)."""
    response = _client().get("/api/does-not-exist-fictitious")
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
