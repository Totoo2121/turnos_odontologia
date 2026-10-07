"""C-03 security tests (task 2.1) — RED first.

argon2id hashing (D1), HS256 access/refresh/portal round-trips, tampered
signature rejection, wrong-type rejection, expiry enforcement, the
`!UNSET-C03*` marker never validating, portal expiry `min(turno+24h, 90d)`.
Pure unit: no DB needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

SECRET = "fictitious-jwt-secret-for-tests-only"
PORTAL_SECRET = "fictitious-portal-secret-for-tests-only"
TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
TURNO_ID = uuid.uuid4()


def test_password_round_trip_verifies() -> None:
    """WHEN a password is hashed THEN the same password verifies."""
    from app.infrastructure.security import hash_password, verify_password

    hashed = hash_password("Fictitious-Seed-9!")
    assert hashed != "Fictitious-Seed-9!"
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "Fictitious-Seed-9!") is True


def test_wrong_password_does_not_verify() -> None:
    """WHEN the wrong password is tried THEN verification fails closed."""
    from app.infrastructure.security import hash_password, verify_password

    hashed = hash_password("Fictitious-Seed-9!")
    assert verify_password(hashed, "otra-clave-ficticia-1") is False


def test_unset_marker_never_valid() -> None:
    """WHEN the C-02 `!UNSET-C03*` marker is tried THEN it never verifies."""
    from app.domain.models import PASSWORD_UNSET_MARKER
    from app.infrastructure.security import verify_password

    assert PASSWORD_UNSET_MARKER == "!UNSET-C03*"
    assert verify_password(PASSWORD_UNSET_MARKER, "anything-fictitious") is False
    assert verify_password(PASSWORD_UNSET_MARKER, PASSWORD_UNSET_MARKER) is False
    assert verify_password("!LOCKED-C03-MIGRATED*", "anything-fictitious") is False


def test_access_token_round_trip_claims() -> None:
    """WHEN an access token is created THEN decode returns all spec claims."""
    from app.infrastructure.security import create_access_token, decode_token

    token = create_access_token(
        sub=str(USER_ID),
        tenant_id=str(TENANT_ID),
        roles=["recepcion"],
        email="recepcion@demo-ficticia.invalid",
        secret=SECRET,
    )
    claims = decode_token(token, SECRET, expected_type="access")
    assert claims["sub"] == str(USER_ID)
    assert claims["tenant_id"] == str(TENANT_ID)
    assert claims["roles"] == ["recepcion"]
    assert claims["email"] == "recepcion@demo-ficticia.invalid"
    assert claims["type"] == "access"
    assert "jti" in claims and "iat" in claims and "exp" in claims
    assert "fam" in claims


def test_refresh_token_round_trip_and_family() -> None:
    """WHEN a refresh token is created THEN it decodes as refresh with a family."""
    from app.infrastructure.security import create_refresh_token, decode_token

    first = create_refresh_token(
        sub=str(USER_ID),
        tenant_id=str(TENANT_ID),
        roles=["propietario"],
        email="admin@demo-ficticia.invalid",
        secret=SECRET,
    )
    claims = decode_token(first, SECRET, expected_type="refresh")
    assert claims["type"] == "refresh"
    family = claims["fam"]
    second = create_refresh_token(
        sub=str(USER_ID),
        tenant_id=str(TENANT_ID),
        roles=["propietario"],
        email="admin@demo-ficticia.invalid",
        secret=SECRET,
        family_id=family,
    )
    assert decode_token(second, SECRET, expected_type="refresh")["fam"] == family
    assert decode_token(second, SECRET, expected_type="refresh")["jti"] != claims["jti"]


def test_tampered_signature_rejected() -> None:
    """WHEN a token signature is adulterated THEN decode raises (401 path)."""
    from app.infrastructure.security import (
        TokenError,
        create_access_token,
        decode_token,
    )

    token = create_access_token(
        sub=str(USER_ID),
        tenant_id=str(TENANT_ID),
        roles=["recepcion"],
        email="recepcion@demo-ficticia.invalid",
        secret=SECRET,
    )
    head, body, _sig = token.split(".")
    with pytest.raises(TokenError):
        decode_token(f"{head}.{body}.AAAA", SECRET, expected_type="access")
    with pytest.raises(TokenError):
        decode_token(
            token,
            "otro-secreto-ficticio-de-al-menos-32-bytes",
            expected_type="access",
        )


def test_wrong_type_rejected() -> None:
    """WHEN a refresh is used as access THEN decode with type=access raises."""
    from app.infrastructure.security import (
        TokenError,
        create_refresh_token,
        decode_token,
    )

    refresh = create_refresh_token(
        sub=str(USER_ID),
        tenant_id=str(TENANT_ID),
        roles=["recepcion"],
        email="recepcion@demo-ficticia.invalid",
        secret=SECRET,
    )
    with pytest.raises(TokenError):
        decode_token(refresh, SECRET, expected_type="access")


def test_expired_token_rejected() -> None:
    """WHEN a token is past exp THEN decode raises even with valid signature."""
    from app.infrastructure.security import (
        TokenError,
        create_access_token,
        decode_token,
    )

    token = create_access_token(
        sub=str(USER_ID),
        tenant_id=str(TENANT_ID),
        roles=["recepcion"],
        email="recepcion@demo-ficticia.invalid",
        secret=SECRET,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(TokenError):
        decode_token(token, SECRET, expected_type="access")


def test_empty_secret_never_valid() -> None:
    """WHEN the signing secret is empty THEN creation and decode refuse."""
    from app.infrastructure.security import (
        TokenError,
        create_access_token,
        decode_token,
    )

    with pytest.raises(TokenError):
        create_access_token(
            sub=str(USER_ID),
            tenant_id=str(TENANT_ID),
            roles=["recepcion"],
            email="recepcion@demo-ficticia.invalid",
            secret="",
        )
    with pytest.raises(TokenError):
        decode_token("a.b.c", "", expected_type="access")


def test_portal_token_round_trip() -> None:
    """WHEN a portal token is created THEN it decodes as type=portal."""
    from app.infrastructure.security import create_portal_token, decode_token

    expires_at = datetime.now(UTC) + timedelta(hours=2)
    token = create_portal_token(
        turno_id=str(TURNO_ID),
        tenant_id=str(TENANT_ID),
        secret=PORTAL_SECRET,
        expires_at=expires_at,
    )
    claims = decode_token(token, PORTAL_SECRET, expected_type="portal")
    assert claims["type"] == "portal"
    assert claims["turno_id"] == str(TURNO_ID)
    assert claims["tenant_id"] == str(TENANT_ID)


def test_portal_expiry_is_min_turno_plus_24h_or_90d() -> None:
    """WHEN computing portal expiry THEN min(turno+24h, now+90d) (D7)."""
    from app.infrastructure.security import portal_expiry

    now = datetime.now(UTC)
    soon = now + timedelta(days=2)
    assert portal_expiry(soon, now=now) == soon + timedelta(hours=24)
    far = now + timedelta(days=200)
    assert portal_expiry(far, now=now) == now + timedelta(days=90)
