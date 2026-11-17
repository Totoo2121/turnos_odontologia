"""C-05 catalogo-agenda domain models (SQLAlchemy 2.0 async).

Five tenant-scoped tables on the shared ``app.shared.db.metadata`` so
``alembic/env.py`` sees them with no changes (D1 — ``models.py`` root stays
intact). All identifiers lowercase; PKs native UUID v4.

- ``Profesional`` / ``Sillon`` / ``Prestacion`` / ``Bloqueo`` carry
  ``AuditMixin`` (soft-delete lifecycle, never physical DELETE).
- ``ProfesionalPrestacion`` is a link table like ``UserRol``: ``tenant_id``
  redundant (same-tenant guard, D3) + ``UNIQUE(profesional_id,
  prestacion_id)``, physical DELETE only.
- ``activo`` (operational availability) is distinct from ``is_active``
  (soft-delete lifecycle): an inactive sillón is excluded from slot offers
  until reactivated, without losing its history.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import AuditMixin
from app.domain.models import Base

# Bloqueo motives (RN-AG-05): closed enum enforced by a DB CHECK (D5).
MOTIVOS_BLOQUEO: tuple[str, str, str, str] = (
    "feriado",
    "licencia",
    "administrativo",
    "mantenimiento",
)


class Profesional(AuditMixin, Base):
    """Tenant professional: who provides care and what they may provide."""

    __tablename__ = "profesional"

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
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    matricula: Mapped[str | None] = mapped_column(String(60), nullable=True)
    especialidades: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    duracion_default_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        CheckConstraint("duracion_default_min > 0", name="duracion_default_min_pos"),
    )


class Sillon(AuditMixin, Base):
    """First-class chair/box resource (KB 04): every turno references one."""

    __tablename__ = "sillon"

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
    sucursal_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sucursal.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "nombre", name="uq_sillon_tenant_nombre"),
    )


class Prestacion(AuditMixin, Base):
    """Billable service with scheduling rules (durations, deposit, notice)."""

    __tablename__ = "prestacion"

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
    duracion_min: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    requiere_sillon: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    permite_sobreturno: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sena_obligatoria: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    monto_sena: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    anticipacion_min_cancel_hs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=24, server_default=text("24")
    )
    precio: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # C-11 (RN-NO-04): interval between periodic follow-up appointments.
    intervalo_control_dias: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # C-14 (RN-HC-04): a budget item inherits this flag as a snapshot.
    requiere_consentimiento: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "nombre", name="uq_prestacion_tenant_nombre"),
        CheckConstraint("duracion_min > 0", name="duracion_min_pos"),
        CheckConstraint("buffer_min >= 0", name="buffer_min_nonneg"),
        CheckConstraint(
            "intervalo_control_dias IS NULL OR intervalo_control_dias > 0",
            name="intervalo_control_dias_pos",
        ),
    )


class ProfesionalPrestacion(Base):
    """Professional↔prestacion enablement (D3): physical DELETE only."""

    __tablename__ = "profesional_prestacion"

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
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profesional.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prestacion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "profesional_id",
            "prestacion_id",
            name="uq_profesional_prestacion_pair",
        ),
    )


class Bloqueo(AuditMixin, Base):
    """Unavailability window over a professional and/or sillón (RN-AG-05)."""

    __tablename__ = "bloqueo"

    MOTIVOS_VALIDOS: tuple[str, str, str, str] = MOTIVOS_BLOQUEO

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
    profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profesional.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sillon_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sillon.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    inicio: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fin: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    motivo: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        CheckConstraint("fin > inicio", name="bloqueo_fin_despues_inicio"),
        CheckConstraint(
            "motivo IN ('feriado', 'licencia', 'administrativo', 'mantenimiento')",
            name="bloqueo_motivo_enum",
        ),
        CheckConstraint(
            "profesional_id IS NOT NULL OR sillon_id IS NOT NULL",
            name="bloqueo_al_menos_un_objetivo",
        ),
    )


class Turno(Base):
    """Appointment with anti-overlap guaranteed at DB level (RN-AG-01/02)."""

    __tablename__ = "turno"

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
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("paciente.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profesional.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sillon_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sillon.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prestacion.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inicio: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fin: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente", server_default=text("'pendiente'")
    )
    origen: Mapped[str] = mapped_column(
        String(20), nullable=False, default="recepcion", server_default=text("'recepcion'")
    )
    token_portal: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sobreturno: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sena_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    mp_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # C-11: contact snapshot captured at booking time (C-12 not available yet).
    contacto_whatsapp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contacto_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # C-11 (RN-NO-02): audited WhatsApp confirmation instant.
    confirmado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("fin > inicio", name="turno_fin_despues_inicio"),
    )


class ListaEspera(Base):
    """Waitlist entry: patient waiting for a compatible slot (C-09)."""

    __tablename__ = "lista_espera"

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
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("paciente.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prestacion.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profesional.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    franja: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="activa", server_default=text("'activa'")
    )
    ofrecida_hasta: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Pago(Base):
    """Mercado Pago payment order linked to a turno (C-10)."""

    __tablename__ = "pago"

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
    turno_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("turno.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mp_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mp_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(
        String(8), nullable=False, default="ARS", server_default=text("'ARS'")
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente", server_default=text("'pendiente'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acreditado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("mp_payment_id", name="uq_pago_mp_payment_id"),
    )
