"""C-10 task 5.1: agenda con estado de cobro + reporte de senas pendientes.

- ``GET /api/turnos/agenda`` alimenta la agenda del mostrador (C-07): cada
  turno expone ``cobro`` (pendiente/acreditado/vencido/rechazado/sin-sena),
  ademas del monto y la orden MP cuando existen (patron FLAP).
- ``GET /api/reportes/senias-pendientes`` lista las ordenes de senia sin
  acreditar con los datos de agenda del turno (seguimiento de RN-AD-04).

``tenant_id`` proviene SOLO del JWT validado (D4) y el store DB filtra por
tenant ademas de la RLS. Lectura staff: propietario/odontologo/recepcion/
asistente; el paciente del portal no accede a la agenda completa.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import Depends, Query
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.deps import (
    get_current_principal,
    require_any,
    tenant_session,
)
from app.api.audit import audit_sensitive_request
from app.application.agenda_cobros import AgendaCobroService, DbAgendaCobroStore
from app.application.auth_service import Principal

__all__ = ["router", "get_agenda_cobro_service", "get_current_principal"]

STAFF_ROLES = ("propietario", "odontologo", "recepcion", "asistente")
READ_GUARD = require_any(*STAFF_ROLES)

_UNAUTHORIZED = {"description": "JWT ausente o invalido"}
_FORBIDDEN = {"description": "Rol sin acceso a la agenda"}
_UNPROCESSABLE = {"description": "Parametros invalidos (fecha/vista)"}

router = APIRouter(tags=["agenda-cobros"], dependencies=[Depends(audit_sensitive_request)])


async def get_agenda_cobro_service(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> AgendaCobroService:
    """Production service: DB-backed, pinned to the JWT tenant."""
    return AgendaCobroService(DbAgendaCobroStore(session, principal.tenant_id))


class AgendaTurnoRead(BaseModel):
    """Turno de agenda con su estado de cobro MP resuelto."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    inicio: datetime
    fin: datetime
    estado: str
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    prestacion_id: uuid.UUID | None = None
    paciente_id: uuid.UUID | None = None
    sobreturno: bool = False
    cobro: str
    cobro_monto: float | None = None
    cobro_moneda: str | None = None
    cobro_mp_order_id: str | None = None
    cobro_acreditado_at: datetime | None = None


class SeniaPendienteRead(BaseModel):
    """Orden de senia sin acreditar (reporte de seguimiento)."""

    model_config = ConfigDict(from_attributes=True)

    pago_id: uuid.UUID
    turno_id: uuid.UUID
    monto: float
    moneda: str
    estado: str
    mp_order_id: str | None = None
    created_at: datetime | None = None
    turno_inicio: datetime | None = None
    turno_estado: str | None = None


@router.get(
    "/turnos/agenda",
    response_model=list[AgendaTurnoRead],
    summary="Agenda con estado de cobro",
    description="Turnos del dia o semana (vista=dia|semana) con estado de agenda "
    "y estado de cobro MP (pendiente/acreditado/vencido/rechazado/sin-sena). "
    "Filtrable por profesional o sillon. Solo staff.",
    responses={
        200: {"description": "Turnos con estado y cobro"},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        422: _UNPROCESSABLE,
    },
)
async def get_agenda(
    fecha: date = Query(..., description="Fecha de la agenda (YYYY-MM-DD)"),
    vista: Literal["dia", "semana"] = Query("dia"),
    profesional_id: uuid.UUID | None = Query(None),
    sillon_id: uuid.UUID | None = Query(None),
    service: AgendaCobroService = Depends(get_agenda_cobro_service),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = principal
    turnos = await service.agenda(
        fecha=fecha,
        vista=vista,
        profesional_id=profesional_id,
        sillon_id=sillon_id,
    )
    return [AgendaTurnoRead.model_validate(turno) for turno in turnos]


@router.get(
    "/reportes/senias-pendientes",
    response_model=list[SeniaPendienteRead],
    summary="Reporte de senas pendientes",
    description="Ordenes de senia creadas sin acreditar, con el turno asociado "
    "(seguimiento antes del vencimiento, RN-AD-04). Solo staff.",
    responses={
        200: {"description": "Senas pendientes de acreditacion"},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
    },
)
async def get_senias_pendientes(
    limit: int = Query(100, ge=1, le=500),
    service: AgendaCobroService = Depends(get_agenda_cobro_service),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = principal
    senias = await service.senias_pendientes(limit=limit)
    return [SeniaPendienteRead.model_validate(senia) for senia in senias]
