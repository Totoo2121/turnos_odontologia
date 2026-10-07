"""C-03 portal token service (D7): issue / validate / revoke.

Single-turno portal JWTs (`type=portal`, signed with the dedicated
`PORTAL_SECRET` domain) plus a revocable mirror row in `portal_token`:
cancelling or rescheduling the turno revokes the row, which kills the token
even before its expiry. Endpoints (`GET/POST /p/{token}`) land in C-08;
this module is emission + validation + the store ports only.

Validation answers 401 on untrusted tokens (bad signature, expired, wrong
type) and 404 on well-formed tokens that must not authorize (unknown,
revoked, or foreign turno/tenant) — never leaking tenant data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.infrastructure.security import (
    TokenError,
    create_portal_token,
    decode_token,
    portal_expiry,
)
from app.shared.exceptions import AppError


class PortalError(AppError):
    """Portal token rejected (401 untrusted, 404 unknown/revoked/foreign)."""


@dataclass(frozen=True)
class PortalRecord:
    """Revocable mirror of one issued portal token (`portal_token` row)."""

    turno_id: uuid.UUID
    tenant_id: uuid.UUID
    jti: str
    expires_at: datetime
    revoked_at: datetime | None = None


class PortalStore(Protocol):
    """Persistence for portal rows (DB table in prod, memory in tests)."""

    async def record(self, row: PortalRecord) -> None: ...
    async def find_by_jti(self, jti: str) -> PortalRecord | None: ...
    async def revoke(self, jti: str, now: datetime) -> bool: ...


class MemoryPortalStore:
    """In-memory PortalStore (tests/dev; prod uses `portal_token`)."""

    def __init__(self) -> None:
        self._rows: dict[str, PortalRecord] = {}

    async def record(self, row: PortalRecord) -> None:
        self._rows[row.jti] = row

    async def find_by_jti(self, jti: str) -> PortalRecord | None:
        return self._rows.get(jti)

    async def revoke(self, jti: str, now: datetime) -> bool:
        row = self._rows.get(jti)
        if row is None or row.revoked_at is not None:
            return False
        self._rows[jti] = PortalRecord(
            turno_id=row.turno_id,
            tenant_id=row.tenant_id,
            jti=row.jti,
            expires_at=row.expires_at,
            revoked_at=now,
        )
        return True


@dataclass
class PortalService:
    """Issue and validate single-turno portal tokens (D7)."""

    portal_secret: str
    store: PortalStore = field(default_factory=MemoryPortalStore)

    def issue(
        self,
        *,
        turno_id: uuid.UUID,
        tenant_id: uuid.UUID,
        turno_inicio: datetime,
        now: datetime | None = None,
    ) -> str:
        """Mint a portal token + mirror row (expiry D7, sync helper).

        This sync wrapper covers the in-memory path used by tests and the
        C-08 emission seam; the DB-backed path (`issue_persisted`) awaits the
        row insert instead.
        """
        reference = now or datetime.now(UTC)
        expires_at = portal_expiry(turno_inicio, now=reference)
        token, jti = self._mint(
            turno_id=turno_id, tenant_id=tenant_id, expires_at=expires_at
        )
        row = PortalRecord(
            turno_id=turno_id,
            tenant_id=tenant_id,
            jti=jti,
            expires_at=expires_at,
        )
        store = self.store
        if isinstance(store, MemoryPortalStore):
            store._rows[jti] = row
        return token

    async def issue_persisted(
        self,
        *,
        turno_id: uuid.UUID,
        tenant_id: uuid.UUID,
        turno_inicio: datetime,
        now: datetime | None = None,
    ) -> str:
        """Mint a portal token, awaiting the mirror-row insert (DB path)."""
        reference = now or datetime.now(UTC)
        expires_at = portal_expiry(turno_inicio, now=reference)
        token, jti = self._mint(
            turno_id=turno_id, tenant_id=tenant_id, expires_at=expires_at
        )
        await self.store.record(
            PortalRecord(
                turno_id=turno_id,
                tenant_id=tenant_id,
                jti=jti,
                expires_at=expires_at,
            )
        )
        return token

    def _mint(
        self, *, turno_id: uuid.UUID, tenant_id: uuid.UUID, expires_at: datetime
    ) -> tuple[str, str]:
        import jwt as pyjwt

        token = create_portal_token(
            turno_id=str(turno_id),
            tenant_id=str(tenant_id),
            secret=self.portal_secret,
            expires_at=expires_at,
        )
        jti = str(pyjwt.decode(token, options={"verify_signature": False})["jti"])
        return token, jti

    async def validate(
        self,
        token: str,
        *,
        expected_turno_id: uuid.UUID | None = None,
        expected_tenant_id: uuid.UUID | None = None,
    ) -> PortalRecord:
        """Validate a portal token → its mirror row (401/404, no leaks)."""
        try:
            claims = decode_token(token, self.portal_secret, expected_type="portal")
        except TokenError as exc:
            raise PortalError("invalid portal token", 401) from exc
        row = await self.store.find_by_jti(str(claims["jti"]))
        if row is None or row.revoked_at is not None:
            raise PortalError("portal token not found", 404)
        try:
            token_turno = uuid.UUID(str(claims.get("turno_id", row.turno_id)))
            token_tenant = uuid.UUID(str(claims["tenant_id"]))
        except (ValueError, AttributeError) as exc:
            raise PortalError("invalid portal token", 401) from exc
        if token_turno != row.turno_id or token_tenant != row.tenant_id:
            raise PortalError("portal token not found", 404)
        if expected_turno_id is not None and row.turno_id != expected_turno_id:
            raise PortalError("portal token not found", 404)
        if expected_tenant_id is not None and row.tenant_id != expected_tenant_id:
            raise PortalError("portal token not found", 404)
        return row

    async def revoke(self, token: str) -> bool:
        """Revoke a portal token by value (cancel/reprogram path, C-08)."""
        try:
            claims = decode_token(token, self.portal_secret, expected_type="portal")
        except TokenError as exc:
            raise PortalError("invalid portal token", 401) from exc
        return await self.store.revoke(str(claims["jti"]), datetime.now(UTC))
