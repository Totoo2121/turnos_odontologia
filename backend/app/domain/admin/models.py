"""Append-only audit trail and short-lived export job metadata (C-17)."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models import Base


class AuditEvento(Base):
    __tablename__ = "audit_evento"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=True,
    )
    evento: Mapped[str] = mapped_column(String(64), nullable=False)
    recurso: Mapped[str] = mapped_column(String(64), nullable=False)
    recurso_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metodo: Mapped[str] = mapped_column(String(12), nullable=False)
    ruta: Mapped[str] = mapped_column(String(255), nullable=False)
    detalles: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_evento_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_evento_tenant_evento_created", "tenant_id", "evento", "created_at"),
    )


class Exportacion(Base):
    __tablename__ = "exportacion"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    solicitada_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
    estado: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pendiente'"))
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    solicitada_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    generada_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vence_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_exportacion_tenant_solicitada", "tenant_id", "solicitada_at"),
    )
