"""Reserved schema only; no fiscal or insurer behavior is implemented."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models import Base


class Nomenclador(Base):
    __tablename__ = "nomenclador"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String(48), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_nomenclador_tenant_codigo"),
        Index("ix_nomenclador_tenant_id", "tenant_id"),
    )


class ComprobanteFiscal(Base):
    """Placeholder row only; fiscal authorization is deliberately absent."""

    __tablename__ = "comprobante_fiscal"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    estado: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'reservado'"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("estado = 'reservado'", name="ck_comprobante_fiscal_reservado"),
        Index("ix_comprobante_fiscal_tenant_id", "tenant_id"),
    )
