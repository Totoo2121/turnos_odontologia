"""C-03 refresh/logout tests (task 4.2) — RED first.

Rotation issues a new pair and invalidates the old refresh; reuse of a
rotated refresh revokes the whole family; logout blacklists the access
token. HTTP seam over the REAL router with fake ports (no live DB).
"""

from __future__ import annotations

from tests.support_c03_http import (
    TENANT_SLUG,
    USER_EMAIL,
    USER_PASSWORD,
    build_auth_client,
)

LOGIN_BODY = {
    "tenant_slug": TENANT_SLUG,
    "email": USER_EMAIL,
    "password": USER_PASSWORD,
}


def _login(client):
    response = client.post("/api/auth/login", json=dict(LOGIN_BODY))
    assert response.status_code == 200, response.text
    return response


def _with_refresh_cookie(client, login_response):
    client.cookies.set(
        "refresh_token",
        login_response.cookies["refresh_token"],
        domain="testserver.local",
        path="/api/auth",
    )
    return client


def _replay_with(client, raw_refresh_token):
    """Replace the jar cookie with a stale token (replay/reuse attack)."""
    client.cookies.clear()
    client.cookies.set(
        "refresh_token", raw_refresh_token, domain="testserver.local", path="/api/auth"
    )


def test_refresh_rotates_pair_and_invalidates_old() -> None:
    """WHEN refresh used THEN new pair issued, old refresh rejected after."""
    client, _, _ = build_auth_client()
    first = _login(client)
    old_access = first.json()["access_token"]
    old_refresh = first.cookies["refresh_token"]
    _with_refresh_cookie(client, first)
    second = client.post("/api/auth/refresh")
    assert second.status_code == 200, second.text
    assert second.json()["access_token"] != old_access
    assert "refresh_token=" in second.headers.get("set-cookie", "")
    # Old refresh is now rotated: replay must NOT yield another pair.
    _replay_with(client, old_refresh)
    replay = client.post("/api/auth/refresh")
    assert replay.status_code == 401


def test_reuse_of_rotated_refresh_revokes_family() -> None:
    """WHEN a rotated refresh is replayed THEN family dies (derived tokens 401)."""
    client, _, _ = build_auth_client()
    first = _login(client)
    old_refresh = first.cookies["refresh_token"]
    _with_refresh_cookie(client, first)
    second = client.post("/api/auth/refresh")
    assert second.status_code == 200, second.text
    fresh_access = second.json()["access_token"]
    # Steal/rotation signal: replay the already-rotated refresh.
    _replay_with(client, old_refresh)
    assert client.post("/api/auth/refresh").status_code == 401
    # The derived access token of that family is now rejected too.
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {fresh_access}"}
        ).status_code
        == 401
    )


def test_logout_invalidates_access() -> None:
    """WHEN logout with access THEN that access is rejected afterwards."""
    client, _, _ = build_auth_client()
    first = _login(client)
    access = first.json()["access_token"]
    assert (
        client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {access}"}
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {access}"}
        ).status_code
        == 401
    )


def test_refresh_without_cookie_is_401() -> None:
    """WHEN no refresh cookie THEN 401 (no body-token fallback, D2)."""
    client, _, _ = build_auth_client()
    response = client.post("/api/auth/refresh")
    assert response.status_code == 401
