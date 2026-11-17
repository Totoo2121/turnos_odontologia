"""C-15 counter cash API: payments, receipts and the daily close.

The routes reuse the C-14 ledger (payments are append-only credits) and the
C-06 agenda table (attended appointments); no new tables or migrations.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_current_principal, tenant_session
from app.api.audit import audit_sensitive_request
from app.application.agenda_cobros import AGENDA_TZ
from app.application.auth_service import Principal
from app.application.caja import CajaService, CierreCajaView, DbTurnoDiaStore, TurnoDia
from app.application.cuenta_corriente import (
    MEDIO_LABELS,
    CuentaCorrienteService,
    DbCuentaCorrienteStore,
    DbMovimientoCCStore,
    MovimientoCCRecord,
    PagoView,
    ReciboPagoView,
)
from app.application.pacientes import DbPacienteStore
from app.infrastructure.pdf import SimplePdfWriter

__all__ = ["router", "get_caja_services"]

router = APIRouter(tags=["caja"], dependencies=[Depends(audit_sensitive_request)])


@dataclass(frozen=True)
class CajaServices:
    cuentas: CuentaCorrienteService
    caja: CajaService
    pdf: SimplePdfWriter


async def get_caja_services(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> CajaServices:
    """Production services pinned to the JWT tenant (D11/D14)."""
    tenant = principal.tenant_id
    pacientes = DbPacienteStore(session, tenant)
    movimientos = DbMovimientoCCStore(session, tenant)
    cuentas = CuentaCorrienteService(
        DbCuentaCorrienteStore(session, tenant), movimientos, pacientes
    )
    return CajaServices(
        cuentas=cuentas,
        caja=CajaService(movimientos, DbTurnoDiaStore(session, tenant)),
        pdf=SimplePdfWriter(),
    )


# --- Schemas ---------------------------------------------------------------


class PagoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monto: Decimal = Field(gt=0)
    medio: Literal["efectivo", "transferencia", "mp"]
    idempotency_key: str | None = Field(default=None, max_length=48)
    descripcion: str | None = Field(default=None, max_length=200)


class MovimientoCCRead(BaseModel):
    id: uuid.UUID
    tipo: str
    monto: Decimal
    descripcion: str
    referencia: str | None = None
    plan_tratamiento_id: uuid.UUID | None = None
    ocurrido_at: datetime.datetime | None = None
    created_at: datetime.datetime | None = None


class PagoRead(BaseModel):
    movimiento: MovimientoCCRead
    saldo: Decimal
    medio: str
    referencia: str


class TurnoDiaRead(BaseModel):
    id: uuid.UUID
    inicio: datetime.datetime
    fin: datetime.datetime
    estado: str
    paciente_id: uuid.UUID | None = None
    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None


class CierreCajaRead(BaseModel):
    fecha: datetime.date
    moneda: str
    cobrado_total: Decimal
    por_medio: dict[str, Decimal]
    cantidad_pagos: int
    deuda_generada: Decimal
    diferencia_caja: Decimal
    turnos_atendidos: int
    movimientos: list[MovimientoCCRead] = Field(default_factory=list)
    turnos: list[TurnoDiaRead] = Field(default_factory=list)


# --- Mapping helpers -------------------------------------------------------


def _movimiento_read(movimiento: MovimientoCCRecord) -> MovimientoCCRead:
    return MovimientoCCRead(
        id=movimiento.id,
        tipo=movimiento.tipo,
        monto=movimiento.monto,
        descripcion=movimiento.descripcion,
        referencia=movimiento.referencia,
        plan_tratamiento_id=movimiento.plan_tratamiento_id,
        ocurrido_at=movimiento.ocurrido_at,
        created_at=movimiento.created_at,
    )


def _pago_read(view: PagoView) -> PagoRead:
    return PagoRead(
        movimiento=_movimiento_read(view.movimiento),
        saldo=view.saldo,
        medio=view.medio,
        referencia=view.referencia,
    )


def _turno_read(turno: TurnoDia) -> TurnoDiaRead:
    return TurnoDiaRead(
        id=turno.id,
        inicio=turno.inicio,
        fin=turno.fin,
        estado=turno.estado,
        paciente_id=turno.paciente_id,
        profesional_id=turno.profesional_id,
        sillon_id=turno.sillon_id,
    )


def _cierre_read(view: CierreCajaView) -> CierreCajaRead:
    return CierreCajaRead(
        fecha=view.fecha,
        moneda=view.moneda,
        cobrado_total=view.cobrado_total,
        por_medio=view.por_medio,
        cantidad_pagos=view.cantidad_pagos,
        deuda_generada=view.deuda_generada,
        diferencia_caja=view.diferencia_caja,
        turnos_atendidos=view.turnos_atendidos,
        movimientos=[_movimiento_read(mov) for mov in view.movimientos],
        turnos=[_turno_read(turno) for turno in view.turnos],
    )


def render_recibo(view: ReciboPagoView) -> bytes:
    """Deterministic payment receipt (no generated-at timestamp)."""
    movimiento = view.movimiento
    fecha = (
        movimiento.ocurrido_at.astimezone(AGENDA_TZ).strftime("%Y-%m-%d %H:%M")
        if movimiento.ocurrido_at is not None
        else "-"
    )
    lines = [
        "RECIBO DE PAGO",
        "",
        f"Paciente: {view.paciente.nombre}",
        f"Documento: {view.paciente.dni or '-'}",
        f"Monto: $ {format(movimiento.monto, '.2f')}",
        f"Medio: {MEDIO_LABELS.get(view.medio, view.medio)}",
        f"Fecha: {fecha}",
        f"Referencia: {movimiento.referencia or '-'}",
        f"Saldo resultante: $ {format(view.saldo, '.2f')}",
        f"Movimiento: {movimiento.id}",
        "",
        "Comprobante de pago registrado en la cuenta corriente del paciente.",
    ]
    return SimplePdfWriter().render(lines)


# --- Routes ----------------------------------------------------------------


@router.post(
    "/pacientes/{paciente_id}/cuenta-corriente/pagos",
    response_model=PagoRead,
    status_code=201,
    summary="Registrar un pago de saldo",
)
async def registrar_pago(
    paciente_id: uuid.UUID,
    body: PagoCreate,
    services: CajaServices = Depends(get_caja_services),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    view = await services.cuentas.registrar_pago(
        principal,
        paciente_id,
        monto=body.monto,
        medio=body.medio,
        idempotency_key=body.idempotency_key,
        descripcion=body.descripcion,
    )
    return _pago_read(view)


@router.get(
    "/movimientos-cc/{movimiento_id}/recibo",
    summary="Recibo PDF de un pago",
    responses={404: {"description": "movimiento no encontrado"}},
)
async def get_recibo(
    movimiento_id: uuid.UUID,
    services: CajaServices = Depends(get_caja_services),
    principal: Principal = Depends(get_current_principal),
) -> Response:
    view = await services.cuentas.recibo(principal, movimiento_id)
    return Response(
        content=render_recibo(view),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="recibo-{movimiento_id}.pdf"'
            )
        },
    )


@router.get(
    "/caja/cierre",
    response_model=CierreCajaRead,
    summary="Cierre de caja del dia",
)
async def get_cierre(
    fecha: datetime.date | None = Query(default=None),
    services: CajaServices = Depends(get_caja_services),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    objetivo = fecha or datetime.datetime.now(AGENDA_TZ).date()
    view = await services.caja.cerrar(principal, objetivo)
    return _cierre_read(view)
