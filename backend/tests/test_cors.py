"""CORS contract for the local Vite UI."""

from fastapi.testclient import TestClient


def test_local_vite_origin_can_preflight_login(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
    )
    monkeypatch.setenv("JWT_SECRET", "fictitious-jwt-secret-for-tests-only")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"
