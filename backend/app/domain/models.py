"""C-02 core multi-tenant domain models (SQLAlchemy 2.0 async).

Tables live on the shared ``app.shared.db.metadata`` so ``alembic/env.py``
sees them with no changes. All identifiers are lowercase; PKs are native
UUID v4. ``Rol`` is the SOLE global catalog (no tenant_id, no RLS, no PII);
everything else is tenant-scoped and RLS-enforced (see Migración 001).

``password_hash`` exists as NULLABLE storage only. The ``!UNSET-C03*`` marker
never authenticates against anything in this change; C-03 chooses the hash
scheme and hardens the column to NOT NULL.
"""

import datetime
import re
import uuid

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates

from app.domain.mixins import AuditMixin
from app.shared import db as shared_db

# Global reservation slug alphabet: lowercase, digits, hyphens only (D7).
SLUG_PATTERN = r"^[a-z0-9-]+$"

# Global role catalog (D6): exactly these four rows, immutable by app code.
ROLE_NAMES: tuple[str, str, str, str] = (
    "propietario",
    "odontologo",
    "recepcion",
    "asistente",
)

# TODO(C-03): replace with a real password hash (argon2id vs bcrypt decision
# lives in C-03) and harden usuario.password_hash to NOT NULL. This marker is
# intentionally unverifiable: no login path in C-02 accepts it.
PASSWORD_UNSET_MARKER = "!UNSET-C03*"


class Base(DeclarativeBase):
    """Declarative base bound to the shared C-01 metadata (naming convention)."""

    metadata = shared_db.metadata


class Tenant(AuditMixin, Base):
    """Customer organization (one row per tenant; RLS policy keys on id)."""

    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    slug_reserva: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False, default="base")
    moneda: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="ARS")

    __table_args__ = (
        CheckConstraint(r"slug_reserva ~ '^[a-z0-9-]+$'", name="slug_reserva_format"),
    )


class Sucursal(AuditMixin, Base):
    """Minimal branch row (D3): full multi-branch behavior arrives in E2/C-18."""

    __tablename__ = "sucursal"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    direccion: Mapped[str | None] = mapped_column(String(240), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(60), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "nombre", name="uq_sucursal_tenant_nombre"),
    )


class Rol(AuditMixin, Base):
    """Global role catalog (D6): no tenant_id, no PII, read-only for app code."""

    __tablename__ = "rol"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    nombre: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(240), nullable=True)


class Usuario(AuditMixin, Base):
    """Tenant user; email is unique per tenant and normalized to lowercase."""

    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # TODO(C-03): NOT NULL + real hash scheme; the UNSET marker never logs in.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_usuario_tenant_email"),
    )

    @validates("email")
    def _normalize_email(self, key: str, value: str) -> str:
        """Normalize email to lowercase (app-level complement to the UNIQUE)."""
        return value.strip().lower()


class UserRol(Base):
    """Tenant-scoped user↔role link (D4/D6): physical DELETE only, no lifecycle."""

    __tablename__ = "user_rol"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rol_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rol.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("usuario_id", "rol_id", name="uq_user_rol_usuario_rol"),
    )


class RevokedToken(Base):
    """Global JWT denylist (C-03, D3/D6): NO tenant_id, NO RLS by design.

    Second explicit exception to the hard rule after ``rol``: the lookup runs
    on the non-guessable ``jti`` BEFORE the tenant is known (chicken-egg —
    logout/rotation with an expired token has no GUC), and rows carry no PII
    (jti, type, expiry, reason). ``jti`` values starting with ``fam:`` are
    family-revocation markers (reuse detection) sharing this table.
    """

    __tablename__ = "revoked_token"

    jti: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortalToken(Base):
    """Revocable mirror row for single-turno portal JWTs (C-03, D6/D7).

    Tenant-scoped + RLS/FORCE RLS like every tenant table: the flow verifies
    the signature first, extracts the tenant, pins ``SET LOCAL`` and then
    fetches this row. ``turno_id`` has no FK yet (the turno table arrives in
    C-05/C-08); integrity is enforced by the signed JWT + this row.
    """

    __tablename__ = "portal_token"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turno_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    jti: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("jti", name="uq_portal_token_jti"),)


# Compiled slug alphabet for app-level pre-checks (DB CHECK is authoritative).
SLUG_RE = re.compile(SLUG_PATTERN)
