"""C-03 credential + JWT primitives (D1, D7, D8).

argon2id (OWASP profile) for passwords; HS256 JWT for access / refresh /
portal tokens. `verify_password` fails closed on anything that is not a real
argon2id PHC hash — the C-02 `!UNSET-C03*` marker and the `!LOCKED-*`
migration values never verify. Empty signing secrets are refused at both
creation and verification time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# D1: OWASP argon2id profile (memory-hard, GPU/ASIC resistant). PHC format
# self-describes parameters for future re-calibration without migration.
_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
PORTAL_TOKEN_TYPE = "portal"

# Marker/lock prefixes that must NEVER verify as a password.
_NEVER_VALID_PREFIX = "!"


class TokenError(ValueError):
    """A JWT could not be trusted (bad signature, type, expiry or secret)."""


def hash_password(plain: str) -> str:
    """Hash a password with argon2id (PHC string, e.g. `$argon2id$...`)."""
    return _password_hasher.hash(plain)


def verify_password(password_hash: str | None, plain: str) -> bool:
    """Verify a password, failing closed on markers, locks and garbage."""
    if not password_hash or password_hash.startswith(_NEVER_VALID_PREFIX):
        return False
    try:
        return bool(_password_hasher.verify(password_hash, plain))
    except (VerifyMismatchError, Exception):
        return False


def new_jti() -> str:
    """Fresh token identifier."""
    return uuid.uuid4().hex


def new_family_id() -> str:
    """Fresh refresh-family identifier (stable across rotations)."""
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


def _encode(payload: dict[str, Any], secret: str) -> str:
    if not secret:
        raise TokenError("refusing to sign with an empty secret")
    return jwt.encode(payload, secret, algorithm="HS256")


def _base_claims(
    *,
    sub: str,
    tenant_id: str,
    token_type: str,
    expires_delta: timedelta,
    jti: str | None = None,
) -> dict[str, Any]:
    issued = _now()
    return {
        "sub": sub,
        "tenant_id": tenant_id,
        "jti": jti or new_jti(),
        "type": token_type,
        "iat": issued,
        "exp": issued + expires_delta,
    }


def create_access_token(
    *,
    sub: str,
    tenant_id: str,
    roles: list[str],
    email: str,
    secret: str,
    expires_delta: timedelta | None = None,
    family_id: str | None = None,
) -> str:
    """Create a short-lived access token (`type=access`, D8 default 15 min)."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=15)
    payload = _base_claims(
        sub=sub,
        tenant_id=tenant_id,
        token_type=ACCESS_TOKEN_TYPE,
        expires_delta=expires_delta,
    )
    payload.update(
        {"roles": list(roles), "email": email, "fam": family_id or new_family_id()}
    )
    return _encode(payload, secret)


def create_refresh_token(
    *,
    sub: str,
    tenant_id: str,
    roles: list[str],
    email: str,
    secret: str,
    expires_delta: timedelta | None = None,
    family_id: str | None = None,
) -> str:
    """Create a rotating refresh token (`type=refresh`, D8 default 7 days)."""
    if expires_delta is None:
        expires_delta = timedelta(days=7)
    payload = _base_claims(
        sub=sub,
        tenant_id=tenant_id,
        token_type=REFRESH_TOKEN_TYPE,
        expires_delta=expires_delta,
    )
    payload.update(
        {"roles": list(roles), "email": email, "fam": family_id or new_family_id()}
    )
    return _encode(payload, secret)


def create_portal_token(
    *,
    turno_id: str,
    tenant_id: str,
    secret: str,
    expires_at: datetime,
) -> str:
    """Create a single-turno portal token (`type=portal`, D7)."""
    payload = _base_claims(
        sub=f"portal:{turno_id}",
        tenant_id=tenant_id,
        token_type=PORTAL_TOKEN_TYPE,
        expires_delta=timedelta(seconds=0),
    )
    payload["exp"] = expires_at
    payload["turno_id"] = turno_id
    return _encode(payload, secret)


def decode_token(token: str, secret: str, *, expected_type: str) -> dict[str, Any]:
    """Verify signature + expiry + type; return claims or raise TokenError."""
    if not secret:
        raise TokenError("refusing to verify with an empty secret")
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"token rejected: {exc}") from exc
    if claims.get("type") != expected_type:
        raise TokenError(
            f"wrong token type: expected {expected_type!r}, "
            f"got {claims.get('type')!r}"
        )
    return dict(claims)


def portal_expiry(turno_inicio: datetime, *, now: datetime | None = None) -> datetime:
    """Portal expiry per D7: `min(turno.inicio + 24h, now + 90d)`."""
    reference = now or _now()
    if turno_inicio.tzinfo is None:
        turno_inicio = turno_inicio.replace(tzinfo=UTC)
    return min(turno_inicio + timedelta(hours=24), reference + timedelta(days=90))
