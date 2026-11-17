"""C-15 daily cash close read model (no new table, no migration).

The close is derived from two existing sources: the append-only running account
(``movimiento_cc``) for what was charged and generated that day, and the
agenda (``turno``) for the appointments the clinic actually attended. Payments
are recognized by their ``pago:{medio}:{clave}`` reference, so credits with any
other origin never inflate the cash total.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.application.agenda_cobros import AGENDA_TZ
from app.application.auth_service import Principal
from app.application.cuenta_corriente import (
    MEDIOS_PAGO,
    MONEDA,
    MovimientoCCRecord,
    MovimientoCCStore,
    parse_referencia_pago,
)
from app.application.money import money
from app.application.rbac import authorize


def rango_caja(fecha: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """Half-open ``[desde, hasta)`` day bounds in the clinic timezone."""
    desde = datetime.datetime.combine(
        fecha, datetime.time.min, tzinfo=AGENDA_TZ
    )
    return desde, desde + datetime.timedelta(days=1)


@dataclass(frozen=True)
class TurnoDia:
    """Appointment as seen by the daily close (agenda read model)."""

    id: uuid.UUID
    inicio: datetime.datetime
    fin: datetime.datetime
    estado: str
    paciente_id: uuid.UUID | None = None
    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None


@dataclass(frozen=True)
class CierreCajaView:
    fecha: datetime.date
    desde: datetime.datetime
    hasta: datetime.datetime
    moneda: str
    cobrado_total: Decimal
    por_medio: dict[str, Decimal]
    cantidad_pagos: int
    deuda_generada: Decimal
    diferencia_caja: Decimal
    turnos_atendidos: int
    movimientos: list[MovimientoCCRecord]
    turnos: list[TurnoDia]


class TurnoDiaStore(Protocol):
    async def list_between(
        self,
        tenant_id: uuid.UUID,
        desde: datetime.datetime,
        hasta: datetime.datetime,
    ) -> list[TurnoDia]: ...


class MemoryTurnoDiaStore:
    """In-memory agenda rows for unit/HTTP tests (no live DB)."""

    def __init__(self, turnos: list[TurnoDia] | None = None) -> None:
        self._turnos: list[TurnoDia] = list(turnos or ())

    def add(self, turno: TurnoDia) -> None:
        self._turnos.append(turno)

    async def list_between(
        self,
        tenant_id: uuid.UUID,
        desde: datetime.datetime,
        hasta: datetime.datetime,
    ) -> list[TurnoDia]:
        rows = [
            turno
            for turno in self._turnos
            if desde
            <= _aware(turno.inicio)
            < hasta
        ]
        rows.sort(key=lambda turno: _aware(turno.inicio))
        return rows

    def clear(self) -> None:
        self._turnos.clear()


def _aware(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=AGENDA_TZ)
    return value.astimezone(AGENDA_TZ)


class DbTurnoDiaStore:
    """DB-backed agenda reader, always tenant-pinned (defense in depth)."""

    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_between(
        self,
        tenant_id: uuid.UUID,
        desde: datetime.datetime,
        hasta: datetime.datetime,
    ) -> list[TurnoDia]:
        from sqlalchemy import select

        from app.domain.agenda.models import Turno

        stmt = (
            select(Turno)
            .where(
                Turno.tenant_id == self._tenant_id,
                Turno.inicio >= desde,
                Turno.inicio < hasta,
            )
            .order_by(Turno.inicio.asc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            TurnoDia(
                id=row.id,
                inicio=row.inicio,
                fin=row.fin,
                estado=row.estado,
                paciente_id=row.paciente_id,
                profesional_id=row.profesional_id,
                sillon_id=row.sillon_id,
            )
            for row in rows
        ]


class CajaService:
    """Daily cash close for the counter (cobros read role)."""

    def __init__(
        self, movimientos: MovimientoCCStore, turnos: TurnoDiaStore
    ) -> None:
        self.movimientos = movimientos
        self.turnos = turnos

    async def cerrar(
        self, principal: Principal, fecha: datetime.date
    ) -> CierreCajaView:
        authorize(tuple(principal.roles), "cobros", "R")
        desde, hasta = rango_caja(fecha)
        movimientos = await self.movimientos.list_between(
            principal.tenant_id, desde, hasta
        )
        turnos = await self.turnos.list_between(
            principal.tenant_id, desde, hasta
        )
        por_medio = {medio: Decimal("0.00") for medio in MEDIOS_PAGO}
        cobrado = Decimal("0.00")
        deuda = Decimal("0.00")
        cantidad = 0
        for movimiento in movimientos:
            if movimiento.tipo == "debito":
                deuda += movimiento.monto
                continue
            parsed = parse_referencia_pago(movimiento.referencia)
            if parsed is None:
                continue
            medio, _clave = parsed
            por_medio[medio] += movimiento.monto
            cobrado += movimiento.monto
            cantidad += 1
        cobrado = money(cobrado)
        deuda = money(deuda)
        return CierreCajaView(
            fecha=fecha,
            desde=desde,
            hasta=hasta,
            moneda=MONEDA,
            cobrado_total=cobrado,
            por_medio={medio: money(total) for medio, total in por_medio.items()},
            cantidad_pagos=cantidad,
            deuda_generada=deuda,
            diferencia_caja=money(cobrado - deuda),
            turnos_atendidos=sum(
                1 for turno in turnos if turno.estado == "atendido"
            ),
            movimientos=movimientos,
            turnos=turnos,
        )
