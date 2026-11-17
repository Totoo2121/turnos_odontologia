"""C-09 lista de espera endpoints: POST /lista-espera, GET /lista-espera."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_principal, tenant_session
from app.application.auth_service import Principal
from app.domain.agenda.models import ListaEspera, Turno
from app.shared.exceptions import AppError

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)

router = APIRouter()


class ListaEsperaCreate(BaseModel):
    model_config = _STRICT

    paciente_id: uuid.UUID | None = None
    prestacion_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    franja: str = Field(min_length=1, max_length=20)


class ListaEsperaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID | None = None
    prestacion_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    franja: str
    estado: str
    ofrecida_hasta: Any = None
    created_at: Any


@router.post("/lista-espera", response_model=ListaEsperaRead, status_code=201)
async def create_lista_espera(
    body: ListaEsperaCreate,
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    row = ListaEspera(
        tenant_id=principal.tenant_id,
        paciente_id=body.paciente_id,
        prestacion_id=body.prestacion_id,
        profesional_id=body.profesional_id,
        franja=body.franja,
        estado="activa",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ListaEsperaRead.model_validate(row)


@router.get("/lista-espera", response_model=list[ListaEsperaRead])
async def list_lista_espera(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    stmt = (
        select(ListaEspera)
        .where(ListaEspera.tenant_id == principal.tenant_id)
        .order_by(ListaEspera.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()
    return [ListaEsperaRead.model_validate(r) for r in rows]


class AceptarOfertaIn(BaseModel):
    model_config = _STRICT

    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    inicio: datetime
    fin: datetime


@router.post("/lista-espera/{id}/aceptar", status_code=201)
async def aceptar_oferta(
    id: uuid.UUID,
    body: AceptarOfertaIn,
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    row = await session.get(ListaEspera, id)
    if row is None or row.tenant_id != principal.tenant_id:
        raise AppError(code="not_found", message="registro no encontrado", status_code=404)
    if row.estado != "ofrecida":
        raise AppError(code="invalid_state", message="registro no ofrecido", status_code=409)
    if row.ofrecida_hasta is not None:
        hasta = row.ofrecida_hasta
        if hasta.tzinfo is None:
            hasta = hasta.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > hasta:
            raise AppError(code="expired", message="oferta vencida", status_code=409)
    turno = Turno(
        tenant_id=principal.tenant_id,
        paciente_id=row.paciente_id,
        profesional_id=body.profesional_id,
        sillon_id=body.sillon_id,
        prestacion_id=row.prestacion_id,
        inicio=body.inicio,
        fin=body.fin,
        estado="pendiente",
        origen="lista_espera",
    )
    session.add(turno)
    row.estado = "convertida"
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(code="conflict", message="solapamiento o bloqueo en el horario elegido", status_code=409) from exc
    await session.refresh(turno)
    return {"turno_id": str(turno.id), "lista_espera_id": str(row.id), "estado": row.estado}
