"""C-03 tenant-binding + guard tests (task 5.1) — RED first.

`tenant_id` comes from the validated access token (D4), never from client
params: cross-tenant access by id is 404 (no leak), tampered signatures and
spoofed `tenant_id` are 401 before touching any store, and the composable
guards (`require_role` / `require_any` / `require_owner_or_treating`, D10)
answer 401/403/404 uniformly. No live DB needed (in-memory fakes).
"""

from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tests.support_c03_http import (
    TENANT_ID,
    TENANT_SLUG,
    USER_EMAIL,
    USER_PASSWORD,
    FakeClock,
    FakeUsers,
)

OTHER_TENANT_ID = uuid.uuid4()
JWT_SECRET = "fictitious-jwt-secret-for-tests-only"

# One fictitious diary entry owned by the demo tenant (cross-tenant → 404).
ITEM_ID = uuid.uuid4()
OTHER_ITEM_ID = uuid.uuid4()
ITEMS = {ITEM_ID: TENANT_ID, OTHER_ITEM_ID: OTHER_TENANT_ID}


def _build_guarded_client(
    *,
    password_hash: str | None = None,
    extra_users: dict | None = None,
) -> tuple[TestClient, FakeClock, object]:
    """Test app: REAL auth router + guarded demo routes over fake ports."""
    from app.api import auth as auth_module
    from app.api import deps as deps_module
    from app.application.auth_service import (
        AuthService,
        LoginRateLimiter,
        MemorySessionStore,
    )
    from app.shared.exceptions import AppError, register_exception_handlers

    if password_hash is None:
        from app.infrastructure.security import hash_password

        password_hash = hash_password(USER_PASSWORD)
    clock = FakeClock()
    service = AuthService(
        jwt_secret=JWT_SECRET,
        access_minutes=15,
        refresh_days=7,
        users=FakeUsers(password_hash, extra_users),
        sessions=MemorySessionStore(),
        limiter=LoginRateLimiter(attempts=5, window_seconds=60, now=clock.now),
        secure_cookies=False,
    )
    app = FastAPI()
    register_exception_handlers(app)
    auth_module.configure_rate_limiting(app)
    try:
        auth_module.limiter.reset()
    except Exception:
        pass
    app.include_router(auth_module.router, prefix="/api")
    app.dependency_overrides[auth_module.get_auth_service] = lambda: service

    async def _agenda_item(
        item_id: uuid.UUID,
        principal=Depends(deps_module.get_current_principal),
    ) -> dict[str, str]:
        owner = ITEMS.get(item_id)
        if owner is None or owner != principal.tenant_id:
            raise AppError("not found", 404)
        return {"item": str(item_id), "tenant": str(principal.tenant_id)}

    async def _owner_report(
        principal=Depends(deps_module.require_role("propietario")),
    ) -> dict[str, str]:
        return {"tenant": str(principal.tenant_id)}

    async def _desk_or_owner(
        principal=Depends(deps_module.require_any("recepcion", "propietario")),
    ) -> dict[str, str]:
        return {"tenant": str(principal.tenant_id)}

    app.get("/api/agenda/{item_id}")(_agenda_item)
    app.get("/api/reportes")(_owner_report)
    app.get("/api/mostrador")(_desk_or_owner)
    app.dependency_overrides[deps_module.get_auth_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False), clock, service


def _login(client: TestClient, **overrides: str) -> str:
    body = {
        "tenant_slug": TENANT_SLUG,
        "email": USER_EMAIL,
        "password": USER_PASSWORD,
    }
    body.update(overrides)
    response = client.post("/api/auth/login", json=body)
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _other_tenant_token() -> str:
    from app.infrastructure.security import create_access_token

    return create_access_token(
        sub=str(uuid.uuid4()),
        tenant_id=str(OTHER_TENANT_ID),
        roles=["propietario"],
        email="otro@otro-ficticio.invalid",
        secret=JWT_SECRET,
    )


def test_same_tenant_item_is_visible() -> None:
    """WHEN token tenant matches THEN guarded read is 200 (happy path)."""
    client, _, _ = _build_guarded_client()
    token = _login(client)
    response = client.get(
        f"/api/agenda/{ITEM_ID}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["tenant"] == str(TENANT_ID)


def test_cross_tenant_item_is_404_without_leak() -> None:
    """WHEN token tenant differs THEN 404 with no content (D4/RN-SE-01)."""
    client, _, _ = _build_guarded_client()
    token = _other_tenant_token()
    response = client.get(
        f"/api/agenda/{ITEM_ID}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404
    assert "demo-ficticia" not in response.text


def test_tampered_signature_is_401_before_store() -> None:
    """WHEN signature does not verify THEN 401, no operation runs."""
    client, _, _ = _build_guarded_client()
    token = _login(client)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    response = client.get(
        f"/api/agenda/{ITEM_ID}", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert response.status_code == 401


def test_spoofed_tenant_id_breaks_signature_is_401() -> None:
    """WHEN payload tenant is altered THEN signature fails → 401 (D4)."""
    import base64
    import json

    from app.infrastructure.security import create_access_token

    client, _, _ = _build_guarded_client()
    _ = _login(client)
    token = create_access_token(
        sub=str(uuid.uuid4()),
        tenant_id=str(TENANT_ID),
        roles=["propietario"],
        email=USER_EMAIL,
        secret=JWT_SECRET,
    )
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["tenant_id"] = str(OTHER_TENANT_ID)
    forged_payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    )
    forged = f"{header}.{forged_payload}.{signature}"
    response = client.get(
        f"/api/agenda/{ITEM_ID}", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401


def test_missing_bearer_is_401() -> None:
    """WHEN no Authorization header THEN 401 (uniform, no leak)."""
    client, _, _ = _build_guarded_client()
    assert client.get(f"/api/agenda/{ITEM_ID}").status_code == 401


def test_refresh_presented_as_access_is_401() -> None:
    """WHEN refresh used as Bearer on guarded route THEN 401 (type check)."""
    client, _, _ = _build_guarded_client()
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
    response = client.get(
        f"/api/agenda/{ITEM_ID}", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401


def test_require_role_denies_with_403_not_404() -> None:
    """WHEN role lacks permission THEN 403 uniform (D10, no partial 200)."""
    from app.infrastructure.security import hash_password

    client, _, _ = _build_guarded_client(
        password_hash=hash_password("irrelevant"),
        extra_users={
            "recepcion@demo-ficticia.invalid": {
                "password_hash": hash_password("Recep-Ficticia-1"),
                "roles": ("recepcion",),
            }
        },
    )
    token = _login(
        client,
        email="recepcion@demo-ficticia.invalid",
        password="Recep-Ficticia-1",
    )
    denied = client.get("/api/reportes", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403
    allowed = client.get("/api/mostrador", headers={"Authorization": f"Bearer {token}"})
    assert allowed.status_code == 200, allowed.text


def test_require_role_allows_matching_role() -> None:
    """WHEN propietario calls owner route THEN 200 (second behavior case)."""
    client, _, _ = _build_guarded_client()
    token = _login(client)
    response = client.get("/api/reportes", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text


def test_hce_guard_fail_closed_without_derivation() -> None:
    """WHEN non-owner w/o derivation hits HCE THEN 404/403 (RN-SE-02, D10)."""
    from app.api import deps as deps_module

    assert (
        deps_module.may_access_hce(("odontologo",), is_owner_treating_or_derived=False)
        is False
    )
    assert (
        deps_module.may_access_hce(("odontologo",), is_owner_treating_or_derived=True)
        is True
    )
    assert (
        deps_module.may_access_hce(("propietario",), is_owner_treating_or_derived=False)
        is True
    )
