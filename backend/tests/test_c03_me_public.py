"""C-03 me + public-path tests (task 4.3) — RED first.

`GET /api/auth/me` reflects the bearer (sub/tenant/roles/email); anonymous
`GET /api/health` stays 200; refresh-as-access is 401; `PUBLIC_PATHS`
declares the turnero/portal/webhook surface (D9, guards land in C-08+).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support_c03_http import (
    TENANT_ID,
    TENANT_SLUG,
    USER_EMAIL,
    USER_PASSWORD,
    build_auth_client,
)


def test_me_reflects_roles() -> None:
    """WHEN recepcion-bearer calls me THEN sub/tenant/roles/email returned."""
    from app.infrastructure.security import hash_password

    client, _, _ = build_auth_client(
        password_hash=hash_password("irrelevant"),
        extra_users={
            "recepcion@demo-ficticia.invalid": {
                "password_hash": hash_password("Recep-Ficticia-1"),
                "roles": ("recepcion",),
            }
        },
    )
    login = client.post(
        "/api/auth/login",
        json={
            "tenant_slug": TENANT_SLUG,
            "email": "recepcion@demo-ficticia.invalid",
            "password": "Recep-Ficticia-1",
        },
    )
    assert login.status_code == 200, login.text
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200, me.text
    payload = me.json()
    assert payload["tenant_id"] == str(TENANT_ID)
    assert "recepcion" in payload["roles"]
    assert payload["email"] == "recepcion@demo-ficticia.invalid"
    assert payload["sub"]


def test_me_without_token_is_401() -> None:
    """WHEN anonymous calls me THEN 401."""
    client, _, _ = build_auth_client()
    assert client.get("/api/auth/me").status_code == 401


def test_refresh_used_as_access_is_401() -> None:
    """WHEN a refresh token is presented as Bearer THEN 401, no operation."""
    client, _, _ = build_auth_client()
    login = client.post(
        "/api/auth/login",
        json={
            "tenant_slug": TENANT_SLUG,
            "email": USER_EMAIL,
            "password": USER_PASSWORD,
        },
    )
    assert login.status_code == 200, login.text
    refresh = login.cookies["refresh_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert me.status_code == 401


def test_health_anonymous_is_ok() -> None:
    """WHEN anonymous hits the health seam THEN 200, never 401/403."""
    from app.api.health import router as health_router
    from app.shared.exceptions import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(health_router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_public_paths_declare_turnero_portal_webhooks() -> None:
    """WHEN PUBLIC_PATHS read THEN health/turnero/portal/webhooks declared (D9)."""
    from app.api.deps import PUBLIC_PATHS, is_public_path

    assert ("GET", "/api/health") in PUBLIC_PATHS
    assert is_public_path("GET", "/api/health") is True
    assert is_public_path("GET", "/reservar/demo-ficticia") is True
    assert is_public_path("GET", "/p/eyJhbGciOiJIUzI1NiJ9.fictitious") is True
    assert is_public_path("POST", "/webhooks/mercadopago") is True
    assert is_public_path("POST", "/webhooks/whatsapp") is True
    # Second case: protected resources are NOT public.
    assert is_public_path("GET", "/api/auth/me") is False
    assert is_public_path("GET", "/api/agenda") is False
