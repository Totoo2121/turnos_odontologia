"""C-10 task 5.1: estado de cobro en la agenda y reporte de senas pendientes.

Read-model del modulo ``cobros``: la agenda del mostrador necesita ver, por
cada turno, tanto su estado de agenda como su **estado de cobro** de Mercado
Pago (patron FLAP). El reporte de senas pendientes lista las ordenes creadas
que todavia no fueron acreditadas, para que recepcion haga seguimiento antes
del vencimiento (RN-AD-04 / RN-TU-04).

Persistencia detras del puerto ``AgendaCobroStore``: produccion usa
``DbAgendaCobroStore`` (Turno + Pago, tenant-pinned + RLS); los tests inyectan
``MemoryAgendaCobroStore``. Toda query filtra ``tenant_id`` de forma explicita
(defensa en profundidad sobre la RLS, regla dura del proyecto).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import Select, and_, select

from app.application.cobros import (
    ESTADO_COBRO_ACREDITADO,
    ESTADO_COBRO_PENDIENTE,
    ESTADO_COBRO_RECHAZADO,
    ESTADO_COBRO_VENCIDO,
    PagoRecord,
)
from app.domain.agenda.models import Pago, Turno
from app.infrastructure.repository import TenantScopeError, coerce_tenant_id

# Turno sin senia obligatoria: no hay orden de cobro que mostrar en agenda.
ESTADO_COBRO_SIN_SENA = "sin-sena"

# Estados de cobro que la agenda puede exponer (tabla `pago`).
ESTADOS_COBRO = frozenset(
    {
        ESTADO_COBRO_PENDIENTE,
        ESTADO_COBRO_ACREDITADO,
        ESTADO_COBRO_VENCIDO,
        ESTADO_COBRO_RECHAZADO,
    }
)

VISTAS = ("dia", "semana")

# La agenda es un calendario local de la clinica (Argentina, UTC-3, sin DST).
# Se fija como constante para que los limites del dia sean deterministas.
AGENDA_TZ = timezone(timedelta(hours=-3), "America/Argentina/Buenos_Aires")


def rango_agenda(fecha: date, vista: str = "dia") -> tuple[datetime, datetime]:
    """Rango half-open ``[desde, hasta)`` del dia o de la semana de ``fecha``."""
    if vista not in VISTAS:
        raise ValueError(f"vista invalida: {vista!r} (esperado dia|semana)")
    desde = datetime.combine(fecha, time.min, tzinfo=AGENDA_TZ)
    dias = 7 if vista == "semana" else 1
    return desde, desde + timedelta(days=dias)


def _as_local(value: datetime) -> datetime:
    """Normalize datetimes to AGENDA_TZ (naive values are clock-local)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=AGENDA_TZ)
    return value.astimezone(AGENDA_TZ)


def _sort_key(value: datetime | None) -> datetime:
    """Sort key tolerant of None/naive timestamps."""
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class AgendaTurno:
    """Turno tal como lo muestra la agenda, con su estado de cobro resuelto."""

    id: uuid.UUID
    inicio: datetime
    fin: datetime
    estado: str
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    prestacion_id: uuid.UUID | None = None
    paciente_id: uuid.UUID | None = None
    sobreturno: bool = False
    cobro_estado: str | None = None
    cobro_monto: float | None = None
    cobro_moneda: str | None = None
    cobro_mp_order_id: str | None = None
    cobro_acreditado_at: datetime | None = None

    @property
    def cobro(self) -> str:
        """Estado de cobro visible: pendiente/acreditado/vencido/rechazado/sin-sena."""
        return self.cobro_estado or ESTADO_COBRO_SIN_SENA


@dataclass(frozen=True)
class SeniaPendiente:
    """Orden de senia sin acreditar, con los datos de agenda del turno."""

    pago_id: uuid.UUID
    turno_id: uuid.UUID
    monto: float
    moneda: str
    estado: str
    mp_order_id: str | None = None
    created_at: datetime | None = None
    turno_inicio: datetime | None = None
    turno_estado: str | None = None


def _con_cobro(turno: AgendaTurno, pago: PagoRecord | None) -> AgendaTurno:
    """Attach the latest pago state to a turno (no pago ⇒ ``sin-sena``)."""
    if pago is None:
        return turno
    return replace(
        turno,
        cobro_estado=pago.estado,
        cobro_monto=pago.monto,
        cobro_moneda=pago.moneda,
        cobro_mp_order_id=pago.mp_order_id,
        cobro_acreditado_at=pago.acreditado_at,
    )


def _ultimo_pago_por_turno(pagos: Iterable[PagoRecord]) -> dict[uuid.UUID, PagoRecord]:
    """Latest pago per turno (webhook may rewrite the same order's state)."""
    ultimos: dict[uuid.UUID, PagoRecord] = {}
    for pago in pagos:
        previo = ultimos.get(pago.turno_id)
        if previo is None or _sort_key(pago.created_at) >= _sort_key(previo.created_at):
            ultimos[pago.turno_id] = pago
    return ultimos


class AgendaCobroStore(Protocol):
    """Persistence port for the agenda read model and pending-seña report."""

    async def list_turnos(
        self,
        *,
        desde: datetime,
        hasta: datetime,
        profesional_id: uuid.UUID | None = None,
        sillon_id: uuid.UUID | None = None,
    ) -> list[AgendaTurno]: ...

    async def list_senias_pendientes(
        self, *, limit: int = 100
    ) -> list[SeniaPendiente]: ...


class MemoryAgendaCobroStore:
    """In-memory fake for unit/HTTP tests (no live DB)."""

    def __init__(
        self,
        *,
        turnos: Iterable[AgendaTurno] | None = None,
        pagos: Iterable[PagoRecord] | None = None,
    ) -> None:
        self._turnos: list[AgendaTurno] = list(turnos or ())
        self._pagos: list[PagoRecord] = list(pagos or ())

    def add_turno(self, turno: AgendaTurno) -> None:
        self._turnos.append(turno)

    def add_pago(self, pago: PagoRecord) -> None:
        self._pagos.append(pago)

    async def list_turnos(
        self,
        *,
        desde: datetime,
        hasta: datetime,
        profesional_id: uuid.UUID | None = None,
        sillon_id: uuid.UUID | None = None,
    ) -> list[AgendaTurno]:
        seleccionados = [
            turno for turno in self._turnos if desde <= _as_local(turno.inicio) < hasta
        ]
        if profesional_id is not None:
            seleccionados = [
                turno
                for turno in seleccionados
                if turno.profesional_id == profesional_id
            ]
        if sillon_id is not None:
            seleccionados = [
                turno for turno in seleccionados if turno.sillon_id == sillon_id
            ]
        seleccionados.sort(key=lambda turno: _as_local(turno.inicio))
        ultimos = _ultimo_pago_por_turno(self._pagos)
        return [_con_cobro(turno, ultimos.get(turno.id)) for turno in seleccionados]

    async def list_senias_pendientes(
        self, *, limit: int = 100
    ) -> list[SeniaPendiente]:
        turnos = {turno.id: turno for turno in self._turnos}
        pendientes = [
            pago for pago in self._pagos if pago.estado == ESTADO_COBRO_PENDIENTE
        ]
        pendientes.sort(key=lambda pago: _sort_key(pago.created_at))
        return [
            _senia_desde_pago(pago, turnos.get(pago.turno_id))
            for pago in pendientes[:limit]
        ]


def _senia_desde_pago(
    pago: PagoRecord, turno: AgendaTurno | None
) -> SeniaPendiente:
    return SeniaPendiente(
        pago_id=pago.id,
        turno_id=pago.turno_id,
        monto=pago.monto,
        moneda=pago.moneda,
        estado=pago.estado,
        mp_order_id=pago.mp_order_id,
        created_at=pago.created_at,
        turno_inicio=turno.inicio if turno is not None else None,
        turno_estado=turno.estado if turno is not None else None,
    )


class DbAgendaCobroStore:
    """DB-backed store: Turno + Pago, always tenant-scoped (defense in depth)."""

    def __init__(self, session: Any, tenant_id: uuid.UUID | str | None) -> None:
        self._session = session
        self._tenant_id = coerce_tenant_id(tenant_id)

    @property
    def tenant_id(self) -> uuid.UUID:
        return self._tenant_id

    def _require_session(self) -> Any:
        if self._session is None:
            raise TenantScopeError("store has no session (query-only instance)")
        return self._session

    def _stmt_turnos(
        self,
        *,
        desde: datetime,
        hasta: datetime,
        profesional_id: uuid.UUID | None = None,
        sillon_id: uuid.UUID | None = None,
    ) -> Select[Any]:
        stmt = (
            select(Turno)
            .where(
                Turno.tenant_id == self._tenant_id,
                Turno.inicio >= desde,
                Turno.inicio < hasta,
            )
            .order_by(Turno.inicio.asc())
        )
        if profesional_id is not None:
            stmt = stmt.where(Turno.profesional_id == profesional_id)
        if sillon_id is not None:
            stmt = stmt.where(Turno.sillon_id == sillon_id)
        return stmt

    def _stmt_pagos(self, turno_ids: Iterable[uuid.UUID]) -> Select[Any]:
        return select(Pago).where(
            Pago.tenant_id == self._tenant_id,
            Pago.turno_id.in_(list(turno_ids)),
        )

    def _stmt_senias_pendientes(self, *, limit: int = 100) -> Select[Any]:
        return (
            select(Pago, Turno.inicio, Turno.estado)
            .outerjoin(
                Turno,
                and_(
                    Turno.id == Pago.turno_id,
                    Turno.tenant_id == Pago.tenant_id,
                ),
            )
            .where(
                Pago.tenant_id == self._tenant_id,
                Pago.estado == ESTADO_COBRO_PENDIENTE,
            )
            .order_by(Pago.created_at.asc())
            .limit(limit)
        )

    async def list_turnos(
        self,
        *,
        desde: datetime,
        hasta: datetime,
        profesional_id: uuid.UUID | None = None,
        sillon_id: uuid.UUID | None = None,
    ) -> list[AgendaTurno]:
        session = self._require_session()
        resultado = await session.execute(
            self._stmt_turnos(
                desde=desde,
                hasta=hasta,
                profesional_id=profesional_id,
                sillon_id=sillon_id,
            )
        )
        turnos: list[Turno] = list(resultado.scalars().all())
        if not turnos:
            return []
        pagos_resultado = await session.execute(
            self._stmt_pagos(turno.id for turno in turnos)
        )
        ultimos = _ultimo_pago_por_turno(
            _pago_record(pago) for pago in pagos_resultado.scalars()
        )
        return [
            _con_cobro(_agenda_turno(turno), ultimos.get(turno.id))
            for turno in turnos
        ]

    async def list_senias_pendientes(
        self, *, limit: int = 100
    ) -> list[SeniaPendiente]:
        session = self._require_session()
        resultado = await session.execute(
            self._stmt_senias_pendientes(limit=limit)
        )
        return [
            SeniaPendiente(
                pago_id=pago.id,
                turno_id=pago.turno_id,
                monto=float(pago.monto),
                moneda=pago.moneda,
                estado=pago.estado,
                mp_order_id=pago.mp_order_id,
                created_at=pago.created_at,
                turno_inicio=inicio,
                turno_estado=estado,
            )
            for pago, inicio, estado in resultado.all()
        ]


def _agenda_turno(turno: Turno) -> AgendaTurno:
    return AgendaTurno(
        id=turno.id,
        inicio=turno.inicio,
        fin=turno.fin,
        estado=turno.estado,
        profesional_id=turno.profesional_id,
        sillon_id=turno.sillon_id,
        prestacion_id=turno.prestacion_id,
        paciente_id=turno.paciente_id,
        sobreturno=turno.sobreturno,
    )


def _pago_record(pago: Pago) -> PagoRecord:
    return PagoRecord(
        id=pago.id,
        tenant_id=pago.tenant_id,
        turno_id=pago.turno_id,
        mp_order_id=pago.mp_order_id,
        mp_payment_id=pago.mp_payment_id,
        monto=float(pago.monto),
        moneda=pago.moneda,
        estado=pago.estado,
        acreditado_at=pago.acreditado_at,
        created_at=pago.created_at,
    )


class AgendaCobroService:
    """Application seam: agenda with cobro + pending-seña report."""

    def __init__(self, store: AgendaCobroStore) -> None:
        self.store = store

    async def agenda(
        self,
        *,
        fecha: date,
        vista: str = "dia",
        profesional_id: uuid.UUID | None = None,
        sillon_id: uuid.UUID | None = None,
    ) -> list[AgendaTurno]:
        desde, hasta = rango_agenda(fecha, vista)
        return await self.store.list_turnos(
            desde=desde,
            hasta=hasta,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
        )

    async def senias_pendientes(self, *, limit: int = 100) -> list[SeniaPendiente]:
        return await self.store.list_senias_pendientes(limit=limit)
