"""C-12 pacientes + HCE API (CRUD + clinical history + append-only notes)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    get_current_principal,
    require_any,
    require_role,
    tenant_session,
)
from app.api.audit import audit_sensitive_request
from app.application.auth_service import Principal
from app.application.pacientes import (
    AccesoClinicoService,
    DbAccesoClinicoStore,
    DbDerivacionStore,
    DbEvolucionStore,
    DbHistoriaStore,
    DbPacienteStore,
    HistoriaClinicaService,
    PacienteService,
)

__all__ = [
    "router",
    "get_paciente_service",
    "get_historia_service",
]

STAFF_ROLES = ("propietario", "odontologo", "recepcion", "asistente")
READ_GUARD = require_any(*STAFF_ROLES)
WRITE_GUARD = require_any(*STAFF_ROLES)
OWNER_GUARD = require_role("propietario")
CLINICAL_GUARD = require_any("propietario", "odontologo")

router = APIRouter(tags=["pacientes"], dependencies=[Depends(audit_sensitive_request)])


async def get_paciente_service(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> PacienteService:
    """Production patient service pinned to the JWT tenant (D11)."""
    return PacienteService(DbPacienteStore(session, principal.tenant_id))


async def get_historia_service(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> HistoriaClinicaService:
    """Production HCE service with DB-backed stores and clinical access."""
    tenant = principal.tenant_id
    derivaciones = DbDerivacionStore(session, tenant)
    acceso = AccesoClinicoService(
        DbAccesoClinicoStore(session, tenant), derivaciones
    )
    return HistoriaClinicaService(
        historias=DbHistoriaStore(session, tenant),
        pacientes=DbPacienteStore(session, tenant),
        evoluciones=DbEvolucionStore(session, tenant),
        derivaciones=derivaciones,
        acceso=acceso,
    )


class PacienteCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    telefono: str = Field(min_length=1, max_length=32)
    dni: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    obra_social: str | None = Field(default=None, max_length=120)
    consentimiento_datos: bool = False
    consentimiento_at: datetime | None = None


class PacienteUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    telefono: str | None = Field(default=None, min_length=1, max_length=32)
    dni: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    obra_social: str | None = Field(default=None, max_length=120)
    consentimiento_datos: bool | None = None
    consentimiento_at: datetime | None = None


class PacienteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    nombre: str
    telefono: str
    dni: str | None = None
    email: str | None = None
    obra_social: str | None = None
    consentimiento_datos: bool
    consentimiento_at: datetime | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class HistoriaCreate(BaseModel):
    paciente_id: uuid.UUID


class HistoriaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    alergias: str | None = None
    medicacion: str | None = None
    antecedentes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AnamnesisUpdate(BaseModel):
    alergias: str | None = None
    medicacion: str | None = None
    antecedentes: str | None = None


class EvolucionCreate(BaseModel):
    contenido: str = Field(min_length=1)
    corrige_evolucion_id: uuid.UUID | None = None


class EvolucionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    autor_usuario_id: uuid.UUID
    autor_profesional_id: uuid.UUID | None = None
    contenido: str
    corrige_evolucion_id: uuid.UUID | None = None
    created_at: datetime | None = None


class DerivacionCreate(BaseModel):
    hacia_profesional_id: uuid.UUID
    desde_profesional_id: uuid.UUID | None = None
    motivo: str | None = None


class DerivacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    desde_profesional_id: uuid.UUID | None = None
    hacia_profesional_id: uuid.UUID
    motivo: str | None = None
    created_by_usuario_id: uuid.UUID | None = None
    created_at: datetime | None = None


# --- Pacientes -------------------------------------------------------------


@router.get("/pacientes", response_model=list[PacienteRead])
async def list_pacientes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Buscar por nombre o DNI"),
    service: PacienteService = Depends(get_paciente_service),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    rows = await service.listar(
        principal.tenant_id, limit=limit, offset=offset, q=q
    )
    return [PacienteRead.model_validate(row) for row in rows]


@router.post("/pacientes", response_model=PacienteRead, status_code=201)
async def create_paciente(
    body: PacienteCreate,
    service: PacienteService = Depends(get_paciente_service),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    paciente = await service.crear(
        tenant_id=principal.tenant_id,
        nombre=body.nombre,
        telefono=body.telefono,
        dni=body.dni,
        email=body.email,
        obra_social=body.obra_social,
        consentimiento_datos=body.consentimiento_datos,
        consentimiento_at=body.consentimiento_at,
    )
    return PacienteRead.model_validate(paciente)


@router.get("/pacientes/{paciente_id}", response_model=PacienteRead)
async def get_paciente(
    paciente_id: uuid.UUID,
    service: PacienteService = Depends(get_paciente_service),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    paciente = await service.obtener(principal.tenant_id, paciente_id)
    return PacienteRead.model_validate(paciente)


@router.patch("/pacientes/{paciente_id}", response_model=PacienteRead)
async def update_paciente(
    paciente_id: uuid.UUID,
    body: PacienteUpdate,
    service: PacienteService = Depends(get_paciente_service),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    paciente = await service.actualizar(
        principal.tenant_id,
        paciente_id,
        body.model_dump(exclude_unset=True),
    )
    return PacienteRead.model_validate(paciente)


@router.delete("/pacientes/{paciente_id}", status_code=204)
async def delete_paciente(
    paciente_id: uuid.UUID,
    service: PacienteService = Depends(get_paciente_service),
    principal: Principal = Depends(OWNER_GUARD),
) -> Response:
    await service.borrar(principal.tenant_id, paciente_id)
    return Response(status_code=204)


# --- Historia clinica ------------------------------------------------------


@router.post(
    "/historias-clinicas", response_model=HistoriaRead, status_code=201
)
async def open_historia(
    body: HistoriaCreate,
    service: HistoriaClinicaService = Depends(get_historia_service),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    historia = await service.obtener_o_crear(
        principal, body.paciente_id
    )
    return HistoriaRead.model_validate(historia)


@router.get(
    "/historias-clinicas/{historia_id}", response_model=HistoriaRead
)
async def get_historia(
    historia_id: uuid.UUID,
    service: HistoriaClinicaService = Depends(get_historia_service),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    historia = await service.obtener(principal, historia_id)
    return HistoriaRead.model_validate(historia)


@router.patch(
    "/historias-clinicas/{historia_id}", response_model=HistoriaRead
)
async def update_anamnesis(
    historia_id: uuid.UUID,
    body: AnamnesisUpdate,
    service: HistoriaClinicaService = Depends(get_historia_service),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    historia = await service.actualizar_anamnesis(
        principal, historia_id, body.model_dump(exclude_unset=True)
    )
    return HistoriaRead.model_validate(historia)


# --- Evoluciones (append-only) ---------------------------------------------


@router.get(
    "/historias-clinicas/{historia_id}/evoluciones",
    response_model=list[EvolucionRead],
)
async def list_evoluciones(
    historia_id: uuid.UUID,
    service: HistoriaClinicaService = Depends(get_historia_service),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    rows = await service.listar_evoluciones(principal, historia_id)
    return [EvolucionRead.model_validate(row) for row in rows]


@router.post(
    "/historias-clinicas/{historia_id}/evoluciones",
    response_model=EvolucionRead,
    status_code=201,
)
async def create_evolucion(
    historia_id: uuid.UUID,
    body: EvolucionCreate,
    service: HistoriaClinicaService = Depends(get_historia_service),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    evolucion = await service.registrar_evolucion(
        principal,
        historia_id,
        contenido=body.contenido,
        corrige_evolucion_id=body.corrige_evolucion_id,
    )
    return EvolucionRead.model_validate(evolucion)


# --- Derivaciones ----------------------------------------------------------


@router.post(
    "/historias-clinicas/{historia_id}/derivaciones",
    response_model=DerivacionRead,
    status_code=201,
)
async def create_derivacion(
    historia_id: uuid.UUID,
    body: DerivacionCreate,
    service: HistoriaClinicaService = Depends(get_historia_service),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    derivacion = await service.registrar_derivacion(
        principal,
        historia_id,
        hacia_profesional_id=body.hacia_profesional_id,
        desde_profesional_id=body.desde_profesional_id,
        motivo=body.motivo,
    )
    return DerivacionRead.model_validate(derivacion)
