"""C-11 operative API: reception alerts and read-only approved templates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.deps import (
    get_current_principal,
    require_any,
    require_role,
    tenant_session,
)
from app.application.auth_service import Principal
from app.application.notificaciones import (
    DbPlantillaStore,
    DbRecordatorioStore,
    NotificacionService,
)
from app.application.notificaciones_runtime import build_service

__all__ = ["router", "get_notificacion_service"]

STAFF_ROLES = ("propietario", "odontologo", "recepcion", "asistente")
READ_GUARD = require_any(*STAFF_ROLES)
OWNER_GUARD = require_role("propietario")

router = APIRouter(tags=["notificaciones"])


async def get_notificacion_service(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> NotificacionService:
    """Production service: DB-backed stores pinned to the JWT tenant (D4)."""
    base = build_service()
    return NotificacionService(
        recordatorios=DbRecordatorioStore(session, principal.tenant_id),
        plantillas=DbPlantillaStore(session, principal.tenant_id),
        whatsapp=base.whatsapp,
        email=base.email,
        max_intentos=base.max_intentos,
        backoff_base_s=base.backoff_base_s,
    )


class RecordatorioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    turno_id: uuid.UUID
    paciente_id: uuid.UUID | None = None
    canal: str
    tipo: str
    plantilla: str
    destinatario: str | None = None
    enviar_at: datetime
    estado: str
    intentos: int = 0
    ultimo_error: str | None = None
    confirmado_at: datetime | None = None


class PlantillaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clave: str
    canal: str
    idioma: str
    version: int
    cuerpo: str
    meta_template_name: str | None = None
    activo: bool


@router.get("/recordatorios", response_model=list[RecordatorioRead])
async def list_recordatorios(
    tipo: str | None = Query(None, description="Filtrar por tipo de recordatorio"),
    limit: int = Query(100, ge=1, le=500),
    service: NotificacionService = Depends(get_notificacion_service),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    rows = await service.recordatorios.list_by_tenant(
        principal.tenant_id, tipo=tipo, limit=limit
    )
    return [RecordatorioRead.model_validate(row) for row in rows]


@router.get("/plantillas", response_model=list[PlantillaRead])
async def list_plantillas(
    service: NotificacionService = Depends(get_notificacion_service),
    principal: Principal = Depends(OWNER_GUARD),
) -> Any:
    rows = await service.plantillas.list_plantillas(principal.tenant_id)
    return [
        PlantillaRead(
            id=row.id,
            clave=row.clave,
            canal=row.canal,
            idioma=row.idioma,
            version=row.version,
            cuerpo=row.cuerpo,
            meta_template_name=row.meta_template_name,
            activo=row.activo,
        )
        for row in rows
    ]
