"""C-03 login tests (task 4.1) — RED first.

HTTP seam over the REAL router with fake ports: login ok (access + HttpOnly
refresh cookie), generic 401 without user enumeration, email
case-insensitivity, and 5/60s IP+email rate limiting. No live DB needed.
"""

from __future__ import annotations

from tests.support_c03_http import (
    TENANT_SLUG,
    USER_EMAIL,
    USER_PASSWORD,
    build_auth_client,
)

LOGIN = "/api/auth/login"
LOGIN_BODY = {
    "tenant_slug": TENANT_SLUG,
    "email": USER_EMAIL,
    "password": USER_PASSWORD,
}


def _login(client, body=None):
    return client.post(LOGIN, json=body or dict(LOGIN_BODY))


def test_login_ok_emits_access_and_http_only_cookie() -> None:
    """WHEN valid credential THEN 200 + access token + HttpOnly cookie (D2)."""
    client, _, _ = build_auth_client()
    response = _login(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert isinstance(payload["access_token"], str) and payload["access_token"]
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/api/auth" in set_cookie
    assert "SameSite=Lax" in set_cookie or "samesite=lax" in set_cookie.lower()


def test_login_email_case_insensitive() -> None:
    """WHEN email differs only in case THEN login still succeeds (spec)."""
    client, _, _ = build_auth_client()
    body = dict(LOGIN_BODY)
    body["email"] = USER_EMAIL.upper()
    response = _login(client, body)
    assert response.status_code == 200, response.text


def test_unknown_email_generic_401_without_tokens() -> None:
    """WHEN email unknown THEN 401 generic, no tokens, no cookie."""
    client, _, _ = build_auth_client()
    body = dict(LOGIN_BODY)
    body["email"] = "nadie@demo-ficticia.invalid"
    response = _login(client, body)
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}
    assert "access_token" not in response.json()
    assert "refresh_token" not in response.headers.get("set-cookie", "")


def test_wrong_password_same_generic_401() -> None:
    """WHEN password wrong THEN identical 401 (no user enumeration)."""
    client, _, _ = build_auth_client()
    body = dict(LOGIN_BODY)
    body["password"] = "Clave-Ficticia-Equivocada-1"
    response = _login(client, body)
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_sixth_attempt_in_window_is_429() -> None:
    """WHEN IP+email exceeds 5/60s THEN 6th attempt is 429 (D5/spec)."""
    client, _, _ = build_auth_client()
    statuses = [_login(client).status_code for _ in range(6)]
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


def test_rate_limit_counts_failures_not_only_successes() -> None:
    """WHEN 5 bad attempts THEN even the correct 6th is 429 (abuse-proof)."""
    client, _, _ = build_auth_client()
    body = dict(LOGIN_BODY)
    body["password"] = "Clave-Ficticia-Equivocada-1"
    for _ in range(5):
        assert _login(client, body).status_code == 401
    assert _login(client).status_code == 429
