"""C-13 clinical artifacts: odontogram, attachments and signed consents.

Tenant-scoped tables on the shared ``app.shared.db.metadata`` so
``alembic/env.py`` sees them with no changes:

- ``Odontograma``: one odontogram per clinical history (C-12).
- ``EventoPieza``: append-only FDI event (piece + surface + state + date +
  author). DB triggers reject UPDATE/DELETE, same spirit as ``evolucion``.
- ``Adjunto``: RX/photo/document always attached to the history, never to a
  turno (RN-HC-05), stored privately behind opaque storage keys.
- ``Consentimiento``: electronic signature record with a canonical SHA-256,
  timestamp, IP/device and a generated PDF (RN-HC-04).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models import Base

ESTADOS_PIEZA = (
    "sano",
    "caries",
    "obturacion",
    "corona",
    "endodoncia",
    "extraccion",
    "implante",
    "sellador",
)
SUPERFICIES = (
    "oclusal",
    "mesial",
    "distal",
    "vestibular",
    "lingual",
    "palatina",
    "incisal",
)
TIPOS_ADJUNTO = ("rx", "foto", "documento")
TIPOS_CONSENTIMIENTO = (
    "tratamiento",
    "invasivo",
    "cirugia",
    "ortodoncia",
    "datos",
)
ESTADOS_PRESUPUESTO = ("borrador", "enviado", "aceptado", "rechazado")
ESTADOS_PLAN = ("activo", "completado", "cancelado")
TIPOS_MOVIMIENTO_CC = ("debito", "credito")


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Odontograma(Base):
    """Single odontogram per clinical history (RN-HC-02)."""

    __tablename__ = "odontograma"

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
    historia_clinica_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("historia_clinica.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "historia_clinica_id",
            name="uq_odontograma_tenant_historia",
        ),
    )


class EventoPieza(Base):
    """Append-only FDI event (RN-HC-02)."""

    __tablename__ = "evento_pieza"

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
    odontograma_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("odontograma.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pieza_fdi: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    superficie: Mapped[str | None] = mapped_column(String(16), nullable=True)
    estado: Mapped[str] = mapped_column(String(16), nullable=False)
    fecha: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    autor_usuario_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    autor_profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profesional.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "pieza_fdi BETWEEN 11 AND 48 "
            "AND (pieza_fdi % 10) BETWEEN 1 AND 8 "
            "AND (pieza_fdi / 10) BETWEEN 1 AND 4",
            name="evento_pieza_fdi_valida",
        ),
        CheckConstraint(
            "superficie IS NULL OR " + _in_clause("superficie", SUPERFICIES),
            name="evento_pieza_superficie_enum",
        ),
        CheckConstraint(
            _in_clause("estado", ESTADOS_PIEZA),
            name="evento_pieza_estado_enum",
        ),
        CheckConstraint(
            "estado NOT IN ('caries', 'obturacion', 'sellador') "
            "OR superficie IS NOT NULL",
            name="evento_pieza_superficie_requerida",
        ),
        CheckConstraint(
            "estado NOT IN ('corona', 'endodoncia', 'extraccion', 'implante') "
            "OR superficie IS NULL",
            name="evento_pieza_superficie_prohibida",
        ),
        Index(
            "ix_evento_pieza_estado_actual",
            "tenant_id",
            "odontograma_id",
            "pieza_fdi",
            "superficie",
            "fecha",
        ),
    )


class Adjunto(Base):
    """Clinical attachment bound to the history, never to a turno (RN-HC-05)."""

    __tablename__ = "adjunto"

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
    historia_clinica_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("historia_clinica.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    origen: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subido_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "storage_key",
            name="uq_adjunto_tenant_storage_key",
        ),
        CheckConstraint(
            _in_clause("tipo", TIPOS_ADJUNTO),
            name="adjunto_tipo_enum",
        ),
        CheckConstraint("size_bytes > 0", name="adjunto_size_positivo"),
        CheckConstraint(
            "char_length(sha256) = 64", name="adjunto_sha256_hex"
        ),
    )


class Consentimiento(Base):
    """Signed informed consent with verifiable hash (RN-HC-04)."""

    __tablename__ = "consentimiento"

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
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("paciente.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    historia_clinica_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("historia_clinica.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    texto_version: Mapped[str] = mapped_column(String(40), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    plan_invasivo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    firmante_nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    firmante_dni: Mapped[str | None] = mapped_column(String(20), nullable=True)
    firmado_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    dispositivo: Mapped[str] = mapped_column(String(255), nullable=False)
    firma_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pdf_storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            _in_clause("tipo", TIPOS_CONSENTIMIENTO),
            name="consentimiento_tipo_enum",
        ),
        CheckConstraint(
            "char_length(firma_hash) = 64",
            name="consentimiento_firma_hash_hex",
        ),
        CheckConstraint(
            "char_length(pdf_sha256) = 64",
            name="consentimiento_pdf_sha256_hex",
        ),
        Index(
            "ix_consentimiento_paciente_invasivo",
            "tenant_id",
            "paciente_id",
            "plan_invasivo",
        ),
    )


class Presupuesto(Base):
    """Clinical treatment quote in ARS with a 4-state lifecycle (C-14)."""

    __tablename__ = "presupuesto"

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
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("paciente.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    historia_clinica_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("historia_clinica.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    creado_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(
        String(12), nullable=False, default="borrador",
        server_default=text("'borrador'"),
    )
    moneda: Mapped[str] = mapped_column(
        String(3), nullable=False, default="ARS", server_default=text("'ARS'")
    )
    total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default=text("0")
    )
    validez_hasta: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    enviado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    aceptado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rechazado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            _in_clause("estado", ESTADOS_PRESUPUESTO),
            name="presupuesto_estado_enum",
        ),
        CheckConstraint(
            "moneda = 'ARS'", name="presupuesto_moneda_ars"
        ),
        CheckConstraint("total >= 0", name="presupuesto_total_nonneg"),
        Index(
            "ix_presupuesto_tenant_paciente_estado",
            "tenant_id",
            "paciente_id",
            "estado",
        ),
    )


class PresupuestoItem(Base):
    """Quote line: prestacion + optional FDI piece, snapshotted price."""

    __tablename__ = "presupuesto_item"

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
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("presupuesto.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prestacion.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pieza_fdi: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    superficie: Mapped[str | None] = mapped_column(String(16), nullable=True)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=False)
    cantidad: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=text("1")
    )
    precio_unitario: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    importe: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    etapa: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=text("1")
    )
    requiere_consentimiento: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("cantidad > 0", name="presupuesto_item_cantidad_pos"),
        CheckConstraint(
            "precio_unitario >= 0", name="presupuesto_item_precio_nonneg"
        ),
        CheckConstraint("importe >= 0", name="presupuesto_item_importe_nonneg"),
        CheckConstraint(
            "etapa BETWEEN 1 AND 20", name="presupuesto_item_etapa_rango"
        ),
        CheckConstraint(
            "pieza_fdi IS NULL OR (pieza_fdi BETWEEN 11 AND 48 "
            "AND (pieza_fdi % 10) BETWEEN 1 AND 8 "
            "AND (pieza_fdi / 10) BETWEEN 1 AND 4)",
            name="presupuesto_item_fdi_valida",
        ),
        CheckConstraint(
            "superficie IS NULL OR " + _in_clause("superficie", SUPERFICIES),
            name="presupuesto_item_superficie_enum",
        ),
        CheckConstraint(
            "superficie IS NULL OR pieza_fdi IS NOT NULL",
            name="presupuesto_item_superficie_exige_pieza",
        ),
        Index(
            "ix_presupuesto_item_tenant_presupuesto_etapa",
            "tenant_id",
            "presupuesto_id",
            "etapa",
        ),
    )


class PlanTratamiento(Base):
    """Accepted budget turned into a staged treatment plan (RN-AD-02)."""

    __tablename__ = "plan_tratamiento"

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
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("presupuesto.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("paciente.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    consentimiento_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consentimiento.id", ondelete="RESTRICT"),
        nullable=True,
    )
    estado: Mapped[str] = mapped_column(
        String(12), nullable=False, default="activo",
        server_default=text("'activo'"),
    )
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    etapas: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    etapa_actual: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "presupuesto_id",
            name="uq_plan_tenant_presupuesto",
        ),
        CheckConstraint(
            _in_clause("estado", ESTADOS_PLAN), name="plan_tratamiento_estado_enum"
        ),
        CheckConstraint("total >= 0", name="plan_tratamiento_total_nonneg"),
        CheckConstraint("etapas >= 1", name="plan_tratamiento_etapas_pos"),
        CheckConstraint(
            "etapa_actual BETWEEN 1 AND etapas",
            name="plan_tratamiento_etapa_actual_rango",
        ),
        Index(
            "ix_plan_tratamiento_tenant_paciente",
            "tenant_id",
            "paciente_id",
        ),
    )


class CuentaCorriente(Base):
    """One running account per patient/tenant; balance derives from movements."""

    __tablename__ = "cuenta_corriente"

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
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("paciente.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    moneda: Mapped[str] = mapped_column(
        String(3), nullable=False, default="ARS", server_default=text("'ARS'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "paciente_id", name="uq_cc_tenant_paciente"
        ),
        CheckConstraint("moneda = 'ARS'", name="cuenta_corriente_moneda_ars"),
    )


class MovimientoCC(Base):
    """Append-only account movement; C-14 only writes debits (RN-AD-02)."""

    __tablename__ = "movimiento_cc"

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
    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cuenta_corriente.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_tratamiento_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plan_tratamiento.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tipo: Mapped[str] = mapped_column(String(8), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ocurrido_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "referencia", name="uq_movimiento_cc_tenant_referencia"
        ),
        CheckConstraint(
            _in_clause("tipo", TIPOS_MOVIMIENTO_CC),
            name="movimiento_cc_tipo_enum",
        ),
        CheckConstraint("monto > 0", name="movimiento_cc_monto_pos"),
        Index(
            "ix_movimiento_cc_tenant_cuenta_ocurrido",
            "tenant_id",
            "cuenta_id",
            "ocurrido_at",
        ),
    )
