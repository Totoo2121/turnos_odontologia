"""C-16 owner reports. All reads are tenant pinned and date bounded."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_principal, require_any, tenant_session
from app.api.audit import audit_sensitive_request
from app.application.auth_service import Principal
from app.application import reportes as queries
from app.shared.exceptions import AppError

router = APIRouter(prefix="/reportes", tags=["reportes"], dependencies=[Depends(audit_sensitive_request)])
REPORT_ROLES = ("propietario", "odontologo", "recepcion", "asistente")


class ReporteFechas(BaseModel):
    desde: date
    hasta: date
    alcance: str
    filas: list[dict[str, Any]]


class RecaudacionRead(BaseModel):
    desde: date
    hasta: date
    alcance: str
    senias_acreditadas: str
    cobros_cuenta_corriente: str
    total_cobrado: str
    cantidad_cobros_cuenta_corriente: int
    deuda_neta_planes: str
    por_profesional: list[dict[str, Any]]


def _default_range() -> tuple[date, date]:
    today = datetime.now(queries.AGENDA_TZ).date()
    return today.replace(day=1), today


async def _scope(session: AsyncSession, principal: Principal) -> tuple[str, Any]:
    return await queries.report_scope(
        session, principal.tenant_id, principal.roles, principal.sub
    )


@router.get("/ocupacion", response_model=ReporteFechas)
async def get_ocupacion(
    desde: date = Query(default_factory=lambda: _default_range()[0]),
    hasta: date = Query(default_factory=lambda: _default_range()[1]),
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(require_any(*REPORT_ROLES)),
) -> Any:
    alcance, profesional_id = await _scope(session, principal)
    filas = await queries.ocupacion(session, principal.tenant_id, desde, hasta, profesional_id)
    return {"desde": desde, "hasta": hasta, "alcance": alcance, "filas": filas}


@router.get("/ausentismo", response_model=ReporteFechas)
async def get_ausentismo(
    desde: date = Query(default_factory=lambda: _default_range()[0]),
    hasta: date = Query(default_factory=lambda: _default_range()[1]),
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(require_any(*REPORT_ROLES)),
) -> Any:
    alcance, profesional_id = await _scope(session, principal)
    filas = await queries.ausentismo(session, principal.tenant_id, desde, hasta, profesional_id)
    return {"desde": desde, "hasta": hasta, "alcance": alcance, "filas": filas}


@router.get("/recaudacion", response_model=RecaudacionRead)
async def get_recaudacion(
    desde: date = Query(default_factory=lambda: _default_range()[0]),
    hasta: date = Query(default_factory=lambda: _default_range()[1]),
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(require_any("propietario", "odontologo")),
) -> Any:
    alcance, profesional_id = await _scope(session, principal)
    if alcance not in {"total", "propio"}:
        raise AppError("forbidden", 403)
    result = await queries.recaudacion(session, principal.tenant_id, desde, hasta, profesional_id)
    return {"desde": desde, "hasta": hasta, "alcance": alcance, **result}


@router.get("/senias-pendientes", response_model=ReporteFechas)
async def get_senias_pendientes(
    desde: date = Query(default_factory=lambda: _default_range()[0]),
    hasta: date = Query(default_factory=lambda: _default_range()[1]),
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(require_any("propietario", "odontologo")),
) -> Any:
    alcance, profesional_id = await _scope(session, principal)
    filas = await queries.senias_pendientes(
        session, principal.tenant_id, desde, hasta, profesional_id
    )
    return {"desde": desde, "hasta": hasta, "alcance": alcance, "filas": filas}
