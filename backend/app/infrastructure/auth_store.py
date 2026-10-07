"""C-03 production adapters (SQLAlchemy over the 002 tables).

`DbUserLookup` resolves the login credential pre-auth via the
`auth_lookup_user()` SECURITY DEFINER function (migration 002): `usuario`
and `tenant` are RLS fail-closed without a tenant GUC, and login — like the
`revoked_token` check — legitimately runs before any tenant is known. The
function returns at most the single row matching slug+email, and failures
stay generic 401s, so it reveals nothing beyond the login seam itself.
`DbSessionStore` persists revocation in the global `revoked_token` table
(D3 source of truth, no RLS by D6 design).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth_service import SessionStore, UserLookup, UserRecord
from app.application.portal_service import PortalRecord, PortalStore
from app.domain.models import PortalToken, RevokedToken

FAMILY_MARKER_PREFIX = "fam:"


def family_marker_jti(family_id: str) -> str:
    """Denylist row identifying a revoked refresh family (shares the table)."""
    return f"{FAMILY_MARKER_PREFIX}{family_id}"


class DbUserLookup(UserLookup):
    """Pre-auth credential lookup via `auth_lookup_user()` (RLS-safe)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active(self, tenant_slug: str, email: str) -> UserRecord | None:
        row = (
            (
                await self._session.execute(
                    text("SELECT * FROM auth_lookup_user(:slug, :email)"),
                    {"slug": tenant_slug, "email": email},
                )
            )
            .mappings()
            .first()
        )
        if row is None or not row["is_active"]:
            return None
        roles = tuple(row["roles"] or ())
        return UserRecord(
            id=uuid.UUID(str(row["user_id"])),
            tenant_id=uuid.UUID(str(row["tenant_id"])),
            tenant_slug=tenant_slug,
            email=str(row["user_email"]),
            password_hash=str(row["password_hash"]),
            roles=roles,
            is_active=True,
        )


class DbSessionStore(SessionStore):
    """Revocation persisted in `revoked_token` (global, no RLS)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_revoked(self, jti: str) -> bool:
        row = (
            await self._session.execute(
                select(RevokedToken.jti).where(RevokedToken.jti == jti)
            )
        ).first()
        return row is not None

    async def revocation_reason(self, jti: str) -> str | None:
        row = (
            await self._session.execute(
                select(RevokedToken.reason).where(RevokedToken.jti == jti)
            )
        ).first()
        return str(row[0]) if row else None

    async def revoke(
        self, jti: str, token_type: str, expires_at: datetime, reason: str
    ) -> None:
        existing = await self._session.get(RevokedToken, jti)
        if existing is None:
            self._session.add(
                RevokedToken(
                    jti=jti,
                    type=token_type,
                    expires_at=expires_at,
                    reason=reason,
                )
            )
            await self._session.flush()

    async def is_family_revoked(self, family_id: str) -> bool:
        return await self.is_revoked(family_marker_jti(family_id))

    async def revoke_family(self, family_id: str, expires_at: datetime) -> None:
        await self.revoke(family_marker_jti(family_id), "refresh", expires_at, "reuse")

    async def purge_expired(self, now: datetime) -> int:
        result = await self._session.execute(
            delete(RevokedToken).where(RevokedToken.expires_at < now)
        )
        return int(getattr(result, "rowcount", 0) or 0)


class DbPortalStore(PortalStore):
    """Portal rows persisted in `portal_token` (tenant-scoped + RLS, D6).

    Callers pin `SET LOCAL app.tenant_id` from the portal token claims before
    touching this store (same D4 binding as the session seam); RLS then
    guarantees a token can only ever resolve rows of its own tenant.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, row: PortalRecord) -> None:
        self._session.add(
            PortalToken(
                tenant_id=row.tenant_id,
                turno_id=row.turno_id,
                jti=row.jti,
                expires_at=row.expires_at,
                revoked_at=row.revoked_at,
            )
        )
        await self._session.flush()

    async def find_by_jti(self, jti: str) -> PortalRecord | None:
        row = (
            await self._session.execute(
                select(PortalToken).where(PortalToken.jti == jti)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return PortalRecord(
            turno_id=row.turno_id,
            tenant_id=row.tenant_id,
            jti=row.jti,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )

    async def revoke(self, jti: str, now: datetime) -> bool:
        row = (
            await self._session.execute(
                select(PortalToken).where(PortalToken.jti == jti)
            )
        ).scalar_one_or_none()
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = now
        await self._session.flush()
        return True


def utcnow() -> datetime:
    """UTC now (purge watermark helper)."""
    return datetime.now(UTC)
