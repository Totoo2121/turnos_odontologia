"""C-12 pacientes + HCE domain models (SQLAlchemy 2.0 async).

Tenant-scoped tables on the shared ``app.shared.db.metadata`` so
``alembic/env.py`` sees them with no changes:

- ``Paciente``: patient identity + contact + data-consent audit.
- ``HistoriaClinica``: one history per patient/tenant (RN-HC-01).
- ``Evolucion``: append-only clinical entries (DB triggers enforce it).
- ``DerivacionHCE``: explicit clinical derivation to another professional.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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


class Paciente(AuditMixin, Base):
    """Patient identity scoped to one tenant (RN-SE-01, C-12)."""

    __tablename__ = "paciente"

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
    dni: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telefono: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    obra_social: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consentimiento_datos: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    consentimiento_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_paciente_tenant_dni_activo",
            "tenant_id",
            "dni",
            unique=True,
            postgresql_where=text("is_active AND dni IS NOT NULL"),
        ),
        CheckConstraint(
            "NOT consentimiento_datos OR consentimiento_at IS NOT NULL",
            name="paciente_consentimiento_fecha_requerida",
        ),
        CheckConstraint(
            "consentimiento_at IS NULL OR consentimiento_datos",
            name="paciente_consentimiento_sin_flag",
        ),
    )


class HistoriaClinica(Base):
    """Single clinical history per patient/tenant (RN-HC-01)."""

    __tablename__ = "historia_clinica"

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
    alergias: Mapped[str | None] = mapped_column(Text, nullable=True)
    medicacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    antecedentes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
            "paciente_id",
            name="uq_historia_clinica_tenant_paciente",
        ),
    )


class Evolucion(Base):
    """Append-only clinical note: never updated or deleted (RN-HC-01)."""

    __tablename__ = "evolucion"

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
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    corrige_evolucion_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evolucion.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DerivacionHCE(Base):
    """Explicit clinical derivation enabling access (RN-SE-02)."""

    __tablename__ = "derivacion_hce"

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
    desde_profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profesional.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    hacia_profesional_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profesional.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
