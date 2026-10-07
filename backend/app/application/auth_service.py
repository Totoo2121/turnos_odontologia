"""C-03 authentication service (D2–D5): login / rotation / logout / me.

Pure application logic behind two ports (`UserLookup`, `SessionStore`) so
HTTP-seam behavior tests run with in-memory fakes while production wires
SQLAlchemy adapters (`infrastructure/auth_store.py`). Failures are generic
401s (no user enumeration); login is rate-limited 5/60s per IP+email (D5).
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import jwt as pyjwt

from app.infrastructure.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_family_id,
    verify_password,
)
from app.shared.exceptions import AppError

# Precomputed dummy hash: unknown emails burn the same argon2id work as real
# ones, so login timing does not reveal whether an email exists.
_DUMMY_HASH = hash_password("fictitious-dummy-password-never-stored")

GENERIC_401 = "invalid credentials"


class AuthError(AppError):
    """Authentication/authorization failure with an explicit HTTP status."""

    def __init__(self, message: str = GENERIC_401, status_code: int = 401) -> None:
        super().__init__(message, status_code)


class RateLimitedError(AuthError):
    """5/60s IP+email budget exhausted (D5); carries Retry-After seconds."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("too many login attempts", 429)
        self.retry_after_seconds = max(retry_after_seconds, 1)


@dataclass(frozen=True)
class UserRecord:
    """Active user row as seen by the auth service (adapter-provided)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_slug: str
    email: str
    password_hash: str
    roles: tuple[str, ...] = ()
    is_active: bool = True


@dataclass(frozen=True)
class Principal:
    """Validated `type=access` identity (D4: tenant comes from the token)."""

    sub: str
    tenant_id: uuid.UUID
    roles: tuple[str, ...]
    email: str


@dataclass(frozen=True)
class SessionPair:
    """Freshly issued access + refresh (refresh travels in an HttpOnly cookie)."""

    access_token: str
    refresh_token: str
    family_id: str
    access_jti: str
    refresh_jti: str


class UserLookup(Protocol):
    """Find the active user for a tenant slug + normalized email (or None)."""

    async def find_active(self, tenant_slug: str, email: str) -> UserRecord | None: ...


class SessionStore(Protocol):
    """Revocation + rotation bookkeeping (DB table in prod, memory in tests)."""

    async def is_revoked(self, jti: str) -> bool: ...
    async def revocation_reason(self, jti: str) -> str | None: ...
    async def revoke(
        self, jti: str, token_type: str, expires_at: datetime, reason: str
    ) -> None: ...
    async def is_family_revoked(self, family_id: str) -> bool: ...
    async def revoke_family(self, family_id: str, expires_at: datetime) -> None: ...
    async def purge_expired(self, now: datetime) -> int: ...


@dataclass
class _Revocation:
    token_type: str
    expires_at: datetime
    reason: str


class MemorySessionStore:
    """In-memory SessionStore (tests/dev; prod uses `revoked_token`)."""

    def __init__(self) -> None:
        self._revoked: dict[str, _Revocation] = {}
        self._families: dict[str, datetime] = {}

    async def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked

    async def revocation_reason(self, jti: str) -> str | None:
        row = self._revoked.get(jti)
        return row.reason if row else None

    async def revoke(
        self, jti: str, token_type: str, expires_at: datetime, reason: str
    ) -> None:
        self._revoked[jti] = _Revocation(token_type, expires_at, reason)

    async def is_family_revoked(self, family_id: str) -> bool:
        return family_id in self._families

    async def revoke_family(self, family_id: str, expires_at: datetime) -> None:
        self._families[family_id] = expires_at

    async def purge_expired(self, now: datetime) -> int:
        before = len(self._revoked) + len(self._families)
        self._revoked = {
            jti: row for jti, row in self._revoked.items() if row.expires_at > now
        }
        self._families = {fam: exp for fam, exp in self._families.items() if exp > now}
        return before - (len(self._revoked) + len(self._families))


class LoginRateLimiter:
    """Rolling-window attempt counter keyed by `ip|email` (D5, in-process)."""

    def __init__(
        self,
        attempts: int = 5,
        window_seconds: int = 60,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._attempts = attempts
        self._window = timedelta(seconds=window_seconds)
        self._now = now or (lambda: datetime.now(UTC))
        self._hits: dict[str, deque[datetime]] = {}

    def check(self, key: str) -> None:
        """Record an attempt; raise RateLimitedError when the budget is spent."""
        now = self._now()
        window = self._hits.setdefault(key, deque())
        while window and now - window[0] >= self._window:
            window.popleft()
        if len(window) >= self._attempts:
            retry = int((window[0] + self._window - now).total_seconds()) + 1
            raise RateLimitedError(retry)
        window.append(now)


def _claims_expiry(claims: dict[str, object]) -> datetime:
    return datetime.fromtimestamp(float(str(claims["exp"])), tz=UTC)


@dataclass
class AuthService:
    """Login / refresh-rotation / logout / me over the injected ports."""

    jwt_secret: str
    access_minutes: int = 15
    refresh_days: int = 7
    users: UserLookup | None = None
    sessions: SessionStore = field(default_factory=MemorySessionStore)
    limiter: LoginRateLimiter = field(default_factory=LoginRateLimiter)
    secure_cookies: bool = False

    def _require_users(self) -> UserLookup:
        if self.users is None:
            raise AuthError("authentication is not configured", 500)
        return self.users

    def _issue_pair(
        self,
        *,
        sub: str,
        tenant_id: uuid.UUID,
        roles: tuple[str, ...],
        email: str,
        family_id: str | None = None,
    ) -> SessionPair:
        fam = family_id or new_family_id()
        access = create_access_token(
            sub=sub,
            tenant_id=str(tenant_id),
            roles=list(roles),
            email=email,
            secret=self.jwt_secret,
            expires_delta=timedelta(minutes=self.access_minutes),
            family_id=fam,
        )
        # The issued jtis live inside the signed tokens: read them back
        # (unverified decode is safe here — we just signed these payloads).
        access_jti = str(
            pyjwt.decode(access, options={"verify_signature": False})["jti"]
        )
        refresh = create_refresh_token(
            sub=sub,
            tenant_id=str(tenant_id),
            roles=list(roles),
            email=email,
            secret=self.jwt_secret,
            expires_delta=timedelta(days=self.refresh_days),
            family_id=fam,
        )
        refresh_jti = str(
            pyjwt.decode(refresh, options={"verify_signature": False})["jti"]
        )
        return SessionPair(access, refresh, fam, access_jti, refresh_jti)

    async def login(
        self, *, tenant_slug: str, email: str, password: str, client_key: str
    ) -> SessionPair:
        """Verify credential → fresh session pair (generic 401, 429 on abuse)."""
        normalized = email.strip().lower()
        self.limiter.check(f"{client_key}|{normalized}")
        user = await self._require_users().find_active(tenant_slug.strip(), normalized)
        if user is None or not user.is_active:
            verify_password(_DUMMY_HASH, password)  # burn equal work, no oracle
            raise AuthError()
        if not verify_password(user.password_hash, password):
            raise AuthError()
        return self._issue_pair(
            sub=str(user.id),
            tenant_id=user.tenant_id,
            roles=user.roles,
            email=user.email,
        )

    async def _validated_refresh_claims(self, refresh_token: str) -> dict[str, object]:
        try:
            claims = decode_token(
                refresh_token, self.jwt_secret, expected_type="refresh"
            )
        except TokenError as exc:
            raise AuthError() from exc
        fam = str(claims.get("fam", ""))
        if not fam or await self.sessions.is_family_revoked(fam):
            raise AuthError()
        jti = str(claims["jti"])
        reason = await self.sessions.revocation_reason(jti)
        if reason == "rotated":
            # Reuse of a rotated refresh = suspected theft: kill the family.
            await self.sessions.revoke_family(fam, _claims_expiry(claims))
            raise AuthError()
        if reason is not None:
            raise AuthError()
        return claims

    async def refresh(self, refresh_token: str) -> SessionPair:
        """Rotate a valid refresh (old dies; reuse kills the family)."""
        claims = await self._validated_refresh_claims(refresh_token)
        old_jti = str(claims["jti"])
        await self.sessions.revoke(
            old_jti, "refresh", _claims_expiry(claims), "rotated"
        )
        raw_roles = claims.get("roles", [])
        roles = (
            tuple(str(role) for role in raw_roles)
            if isinstance(raw_roles, list)
            else ()
        )
        return self._issue_pair(
            sub=str(claims["sub"]),
            tenant_id=uuid.UUID(str(claims["tenant_id"])),
            roles=roles,
            email=str(claims.get("email", "")),
            family_id=str(claims.get("fam")),
        )

    async def logout(self, access_token: str) -> None:
        """Blacklist the presented access token until its natural expiry."""
        try:
            claims = decode_token(access_token, self.jwt_secret, expected_type="access")
        except TokenError as exc:
            raise AuthError() from exc
        await self.sessions.revoke(
            str(claims["jti"]), "access", _claims_expiry(claims), "logout"
        )

    async def validate_access(self, access_token: str) -> Principal:
        """Validate an access token → Principal (401 on revoked/family/expiry)."""
        try:
            claims = decode_token(access_token, self.jwt_secret, expected_type="access")
        except TokenError as exc:
            raise AuthError() from exc
        fam = str(claims.get("fam", ""))
        if not fam or await self.sessions.is_family_revoked(fam):
            raise AuthError()
        if await self.sessions.is_revoked(str(claims["jti"])):
            raise AuthError()
        try:
            tenant_id = uuid.UUID(str(claims["tenant_id"]))
        except (ValueError, AttributeError) as exc:
            raise AuthError() from exc
        return Principal(
            sub=str(claims["sub"]),
            tenant_id=tenant_id,
            roles=tuple(claims.get("roles", [])),
            email=str(claims.get("email", "")),
        )

    async def me(self, access_token: str) -> Principal:
        """Identity of the bearer (spec: sub, tenant_id, roles, email)."""
        return await self.validate_access(access_token)
