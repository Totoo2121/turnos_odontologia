"""C-10 cobros service: creates a Mercado Pago order linked to a turno.

Strict TDD: this module is the application seam; persistence is abstracted
behind ``CobroStore`` and the MP SDK behind ``MercadoPagoClient`` so both can
be faked in unit tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.shared.exceptions import AppError


class CobroError(AppError):
    """Cobro creation failed."""


# Estados de cobro (tabla `pago`) y de turno resultantes (design.md C-10,
# secciones "Estados de turno" y tabla `pago`).
ESTADO_COBRO_PENDIENTE = "pendiente"
ESTADO_COBRO_ACREDITADO = "acreditado"
ESTADO_COBRO_VENCIDO = "vencido"
ESTADO_COBRO_RECHAZADO = "rechazado"

ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO = "reservado-pendiente-pago"
ESTADO_TURNO_CONFIRMADO = "confirmado"
ESTADO_TURNO_CANCELADO = "cancelado"


@dataclass(frozen=True)
class PagoRecord:
    """In-memory mirror of a ``pago`` row (C-10)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    turno_id: uuid.UUID
    mp_order_id: str | None = None
    mp_payment_id: str | None = None
    monto: float = 0.0
    moneda: str = "ARS"
    estado: str = ESTADO_COBRO_PENDIENTE
    checkout_url: str | None = None
    acreditado_at: datetime | None = None
    created_at: datetime | None = None


class CobroStore(Protocol):
    async def record(self, pago: PagoRecord) -> None: ...
    async def find_by_turno(self, turno_id: uuid.UUID) -> PagoRecord | None: ...
    async def find_by_mp_payment_id(self, mp_payment_id: str) -> PagoRecord | None: ...
    async def list_pendientes(self) -> list[PagoRecord]: ...


class MemoryCobroStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, PagoRecord] = {}

    async def record(self, pago: PagoRecord) -> None:
        self._rows[pago.id] = pago

    async def find_by_turno(self, turno_id: uuid.UUID) -> PagoRecord | None:
        for p in self._rows.values():
            if p.turno_id == turno_id:
                return p
        return None

    async def find_by_mp_payment_id(self, mp_payment_id: str) -> PagoRecord | None:
        for p in self._rows.values():
            if p.mp_payment_id == mp_payment_id:
                return p
        return None

    async def list_pendientes(self) -> list[PagoRecord]:
        return [p for p in self._rows.values() if p.estado == ESTADO_COBRO_PENDIENTE]


class MercadoPagoClient(Protocol):
    async def create_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class CobroService:
    def __init__(
        self,
        *,
        store: CobroStore | None = None,
        client: MercadoPagoClient | None = None,
        turnos: dict[uuid.UUID, str] | None = None,
    ) -> None:
        self.store: CobroStore = store if store is not None else MemoryCobroStore()
        self.client: MercadoPagoClient | None = client
        # C-10 scaffold: registro in-memory turno -> estado (ruta DB pendiente).
        self.turnos: dict[uuid.UUID, str] = dict(turnos) if turnos is not None else {}
        # C-10 scaffold: huecos liberados por anulación/vencimiento (RN-AD-04).
        self._liberados: set[uuid.UUID] = set()

    def estado_turno(self, turno_id: uuid.UUID) -> str | None:
        """Estado vigente del turno (scaffold in-memory; None si nunca se movió)."""
        return self.turnos.get(turno_id)

    def liberar_hueco(self, turno_id: uuid.UUID) -> bool:
        """Devuelve el hueco a la grilla tras anular la reserva (RN-AD-04).

        Returns True si el turno tenía reserva vigente que liberar.
        """
        estaba_reservado = self.turnos.get(turno_id) in (
            ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO,
            "reservado",
        )
        self._liberados.add(turno_id)
        return estaba_reservado

    def hueco_liberado(self, turno_id: uuid.UUID) -> bool:
        """True si el hueco del turno fue liberado (vencido/rechazado/anulado)."""
        return turno_id in self._liberados

    async def acreditar(
        self,
        *,
        turno_id: uuid.UUID,
        tenant_id: uuid.UUID,
        mp_payment_id: str,
        mp_order_id: str | None = None,
        monto: float = 0.0,
        moneda: str = "ARS",
    ) -> PagoRecord:
        """C-10 task 3.2: IPN con pago aprobado → `pago` acreditado + turno `confirmado`."""
        ahora = datetime.now(UTC)
        # Transición de la MISMA orden creada al reservar: se conserva su fila
        # (id, orden MP, checkout y monto) para no duplicar el `pago` del turno.
        anterior = await self.store.find_by_turno(turno_id)
        pago = PagoRecord(
            id=anterior.id if anterior is not None else uuid.uuid4(),
            # la orden ya creada manda: el tenant del pago no se toma del IPN
            tenant_id=anterior.tenant_id if anterior is not None else tenant_id,
            turno_id=turno_id,
            mp_order_id=mp_order_id
            or (anterior.mp_order_id if anterior is not None else None),
            mp_payment_id=mp_payment_id,
            monto=monto if monto > 0 else (anterior.monto if anterior else 0.0),
            moneda=moneda,
            estado=ESTADO_COBRO_ACREDITADO,
            checkout_url=anterior.checkout_url if anterior is not None else None,
            acreditado_at=ahora,
            created_at=anterior.created_at if anterior is not None else ahora,
        )
        await self.store.record(pago)
        self.turnos[turno_id] = ESTADO_TURNO_CONFIRMADO
        # el hueco queda ocupado por el turno confirmado
        self._liberados.discard(turno_id)
        return pago

    async def anular(
        self,
        *,
        turno_id: uuid.UUID,
        tenant_id: uuid.UUID,
        mp_payment_id: str | None,
        monto: float = 0.0,
        moneda: str = "ARS",
        motivo: str = "vencido",
    ) -> PagoRecord:
        """C-10 task 3.2: orden vencido/rechazado → `pago` vencido/rechazado + turno `cancelado` + liberar hueco (RN-AD-04)."""
        estado = ESTADO_COBRO_VENCIDO if motivo == "vencido" else ESTADO_COBRO_RECHAZADO
        ahora = datetime.now(UTC)
        anterior = await self.store.find_by_turno(turno_id)
        # transición de la misma orden: se reusa el registro previo (id) si existe
        pago = PagoRecord(
            id=anterior.id if anterior is not None else uuid.uuid4(),
            tenant_id=anterior.tenant_id if anterior is not None else tenant_id,
            turno_id=turno_id,
            mp_order_id=anterior.mp_order_id if anterior is not None else None,
            mp_payment_id=(
                mp_payment_id or (anterior.mp_payment_id if anterior is not None else None)
            ),
            monto=monto,
            moneda=moneda,
            estado=estado,
            created_at=ahora,
        )
        await self.store.record(pago)
        self.turnos[turno_id] = ESTADO_TURNO_CANCELADO
        # anulación/vencimiento → liberar el hueco (RN-AD-04 por encima de RN-TU-04 / RN-G-02)
        self._liberados.add(turno_id)
        return pago

    async def crear_orden(
        self,
        *,
        turno_id: uuid.UUID,
        tenant_id: uuid.UUID,
        monto: float,
        moneda: str = "ARS",
        descripcion: str | None = None,
    ) -> PagoRecord:
        if self.client is None:
            raise CobroError("mercado pago client not configured", 500)
        if monto <= 0:
            raise CobroError("monto must be positive", 400)

        payload = {
            "turno_id": str(turno_id),
            "tenant_id": str(tenant_id),
            "monto": monto,
            "moneda": moneda,
            "descripcion": descripcion or "Seña turno odontológico",
        }
        result = await self.client.create_order(payload)
        ahora = datetime.now(UTC)
        pago = PagoRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            turno_id=turno_id,
            mp_order_id=result.get("id"),
            monto=monto,
            moneda=moneda,
            estado="pendiente",
            checkout_url=result.get("checkout_url") or result.get("init_point"),
            created_at=ahora,
        )
        await self.store.record(pago)
        return pago

    async def reservar_con_sena(
        self,
        *,
        turno_id: uuid.UUID,
        tenant_id: uuid.UUID,
        monto: float,
        moneda: str = "ARS",
        descripcion: str | None = None,
    ) -> PagoRecord:
        """C-10 task 6.1: reserva con seña → orden MP + turno pendiente de pago.

        Encadena la creación de la orden (Checkout Pro) con el estado de agenda
        que exige la spec: la reserva queda pendiente hasta que el IPN acredite.
        """
        pago = await self.crear_orden(
            turno_id=turno_id,
            tenant_id=tenant_id,
            monto=monto,
            moneda=moneda,
            descripcion=descripcion,
        )
        self.turnos[turno_id] = ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO
        return pago

    async def pendientes(self) -> list[PagoRecord]:
        """C-10 task 4.1: órdenes pendientes sin acreditar (para vencimiento)."""
        return await self.store.list_pendientes()