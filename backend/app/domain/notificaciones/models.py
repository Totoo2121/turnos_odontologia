"""C-11 notificaciones WhatsApp domain models (SQLAlchemy 2.0 async).

Tenant-scoped tables on the shared ``app.shared.db.metadata`` so
``alembic/env.py`` sees them with no changes:

- ``PlantillaMensaje``: approved, versioned template per tenant/channel.
- ``Recordatorio``: outbound message (or internal reception alert) linked to
  a turno, with delivery state and confirmation audit.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models import Base


class PlantillaMensaje(Base):
    """Approved message template (RN-NO-01, RN-NO-05)."""

    __tablename__ = "plantilla_mensaje"

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
    clave: Mapped[str] = mapped_column(String(64), nullable=False)
    canal: Mapped[str] = mapped_column(String(16), nullable=False)
    idioma: Mapped[str] = mapped_column(
        String(8), nullable=False, default="es", server_default=text("'es'")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    meta_template_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "clave",
            "canal",
            "idioma",
            "version",
            name="uq_plantilla_mensaje_version",
        ),
        CheckConstraint(
            "canal IN ('whatsapp', 'email')", name="plantilla_canal_enum"
        ),
        CheckConstraint("version > 0", name="plantilla_version_pos"),
    )


class Recordatorio(Base):
    """Message delivery attempt or internal reception alert (C-11)."""

    __tablename__ = "recordatorio"

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
    # C-12 owns the paciente table; this is a forward-compatible reference.
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    canal: Mapped[str] = mapped_column(String(16), nullable=False)
    tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    plantilla: Mapped[str] = mapped_column(String(64), nullable=False)
    destinatario: Mapped[str | None] = mapped_column(String(320), nullable=True)
    enviar_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pendiente",
        server_default=text("'pendiente'"),
    )
    intentos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "turno_id", "canal", "tipo", name="uq_recordatorio_turno_canal_tipo"
        ),
        CheckConstraint(
            "canal IN ('whatsapp', 'email', 'interno')",
            name="recordatorio_canal_enum",
        ),
        CheckConstraint(
            "tipo IN ('t48h', 't24h', 'confirmacion', 'recall_ausente', "
            "'control', 'aviso_recepcion')",
            name="recordatorio_tipo_enum",
        ),
        CheckConstraint(
            "estado IN ('pendiente', 'enviado', 'fallido', 'confirmado', "
            "'cancelado')",
            name="recordatorio_estado_enum",
        ),
        CheckConstraint("intentos >= 0", name="recordatorio_intentos_nonneg"),
    )
