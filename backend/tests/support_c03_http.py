"""Shared C-03 HTTP test rig (fakes, no live DB).

Builds a REAL FastAPI app with the REAL auth router, but overrides the
user-lookup, session-store and clock ports with in-memory fakes so behavior
tests run green without Postgres. Postgres-backed adapters are exercised in
CI via the pg-gated tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

TENANT_SLUG = "demo-ficticia"
TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
USER_EMAIL = "admin@demo-ficticia.invalid"
USER_PASSWORD = "Str0ng!Fictitious-Seed-9"


class FakeUsers:
    """In-memory UserLookup: one active admin (+ optional extras)."""

    def __init__(
        self, password_hash: str, extra: dict[str, dict[str, Any]] | None = None
    ):
        self._hash = password_hash
        self._extra = extra or {}

    async def find_active(self, tenant_slug: str, email: str):
        from app.application.auth_service import UserRecord

        normalized = email.strip().lower()
        if tenant_slug == TENANT_SLUG and normalized == USER_EMAIL:
            return UserRecord(
                id=USER_ID,
                tenant_id=TENANT_ID,
                tenant_slug=TENANT_SLUG,
                email=USER_EMAIL,
                password_hash=self._hash,
                roles=("propietario",),
                is_active=True,
            )
        if normalized in self._extra:
            row = self._extra[normalized]
            return UserRecord(
                id=row.get("id", uuid.uuid4()),
                tenant_id=TENANT_ID,
                tenant_slug=TENANT_SLUG,
                email=normalized,
                password_hash=row["password_hash"],
                roles=row.get("roles", ("recepcion",)),
                is_active=row.get("is_active", True),
            )
        return None


class FakeClock:
    """Controllable clock for rate-limit window tests."""

    def __init__(self) -> None:
        self.now_value = datetime.now(UTC)

    def now(self) -> datetime:
        return self.now_value


def build_auth_client(
    *,
    password_hash: str | None = None,
    extra_users: dict[str, dict[str, Any]] | None = None,
    jwt_secret: str = "fictitious-jwt-secret-for-tests-only",
) -> tuple[TestClient, FakeClock, Any]:
    """Build a TestClient over the real auth router with fake ports."""
    from app.api import auth as auth_module
    from app.application.auth_service import (
        AuthService,
        LoginRateLimiter,
        MemorySessionStore,
    )

    if password_hash is None:
        from app.infrastructure.security import hash_password

        password_hash = hash_password(USER_PASSWORD)
    clock = FakeClock()
    service = AuthService(
        jwt_secret=jwt_secret,
        access_minutes=15,
        refresh_days=7,
        users=FakeUsers(password_hash, extra_users),
        sessions=MemorySessionStore(),
        limiter=LoginRateLimiter(attempts=5, window_seconds=60, now=clock.now),
        secure_cookies=False,
    )
    app = FastAPI()
    from app.shared.exceptions import register_exception_handlers

    register_exception_handlers(app)
    auth_module.configure_rate_limiting(app)
    try:
        auth_module.limiter.reset()
    except Exception:
        pass
    app.include_router(auth_module.router, prefix="/api")
    app.dependency_overrides[auth_module.get_auth_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False), clock, service
