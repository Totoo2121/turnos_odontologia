"""C-15 minimal appointment lifecycle API (C-06 debt, C-15 scope).

Only create, state change and cancel are mounted; reprogramming and
overbooking stay open in C-06. ``fin`` is always computed server-side from the
prestacion duration + buffer, and overlap/blocking conflicts answer 409.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import Depends
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_current_principal, tenant_session
from app.api.audit import audit_sensitive_request
from app.application.auth_service import Principal
from app.application.pacientes import DbPacienteStore
from app.application.turnos import (
    CancelacionView,
    DbBloqueoStore,
    DbTurnoCatalogStore,
    DbTurnoStore,
    TurnoRecord,
    TurnoService,
)

__all__ = ["router", "get_turno_services"]

router = APIRouter(tags=["turnos"], dependencies=[Depends(audit_sensitive_request)])

EstadoTurno = Literal[
    "pendiente",
    "confirmado",
    "reservado-pendiente-pago",
    "atendido",
    "ausente",
    "cancelado",
]


@dataclass(frozen=True)
class TurnoServices:
    turnos: TurnoService


async def get_turno_services(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> TurnoServices:
    """Production services pinned to the JWT tenant (D11/D14)."""
    tenant = principal.tenant_id
    return TurnoServices(
        turnos=TurnoService(
            DbTurnoStore(session, tenant),
            DbTurnoCatalogStore(session, tenant),
            DbBloqueoStore(session, tenant),
            DbPacienteStore(session, tenant),
        )
    )


class TurnoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    prestacion_id: uuid.UUID
    inicio: datetime.datetime
    origen: Literal["recepcion", "control", "mostrador"] = "recepcion"


class TurnoEstadoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: EstadoTurno


class TurnoRead(BaseModel):
    id: uuid.UUID
    paciente_id: uuid.UUID | None = None
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    prestacion_id: uuid.UUID
    inicio: datetime.datetime
    fin: datetime.datetime
    estado: str
    origen: str
    sobreturno: bool = False
    confirmado_at: datetime.datetime | None = None


class CancelacionRead(BaseModel):
    turno: TurnoRead
    cancelacion_tardia: bool
    senia_perdida: bool


def _turno_read(turno: TurnoRecord) -> TurnoRead:
    return TurnoRead(
        id=turno.id,
        paciente_id=turno.paciente_id,
        profesional_id=turno.profesional_id,
        sillon_id=turno.sillon_id,
        prestacion_id=turno.prestacion_id,
        inicio=turno.inicio,
        fin=turno.fin,
        estado=turno.estado,
        origen=turno.origen,
        sobreturno=turno.sobreturno,
        confirmado_at=turno.confirmado_at,
    )


def _cancelacion_read(view: CancelacionView) -> CancelacionRead:
    return CancelacionRead(
        turno=_turno_read(view.turno),
        cancelacion_tardia=view.cancelacion_tardia,
        senia_perdida=view.senia_perdida,
    )


@router.post(
    "/turnos",
    response_model=TurnoRead,
    status_code=201,
    summary="Crear un turno",
)
async def create_turno(
    body: TurnoCreate,
    services: TurnoServices = Depends(get_turno_services),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    turno = await services.turnos.crear(
        principal,
        paciente_id=body.paciente_id,
        profesional_id=body.profesional_id,
        sillon_id=body.sillon_id,
        prestacion_id=body.prestacion_id,
        inicio=body.inicio,
        origen=body.origen,
    )
    return _turno_read(turno)


@router.patch(
    "/turnos/{turno_id}/estado",
    response_model=TurnoRead,
    summary="Cambiar el estado de un turno",
)
async def update_turno_estado(
    turno_id: uuid.UUID,
    body: TurnoEstadoUpdate,
    services: TurnoServices = Depends(get_turno_services),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    turno = await services.turnos.cambiar_estado(
        principal, turno_id, body.estado
    )
    return _turno_read(turno)


@router.post(
    "/turnos/{turno_id}/cancelar",
    response_model=CancelacionRead,
    summary="Cancelar un turno con politica de sena",
)
async def cancelar_turno(
    turno_id: uuid.UUID,
    services: TurnoServices = Depends(get_turno_services),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    view = await services.turnos.cancelar(principal, turno_id)
    return _cancelacion_read(view)
