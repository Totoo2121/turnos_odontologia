"""Patient running account: derived balance, append-only movements.

C-14 records the debits created by accepted budgets. C-15 adds counter payments
as ``credito`` movements, keeping the ledger append-only and the balance always
derived (never cached): the ledger remains the single source of truth.

The payment medium and the idempotency key travel encoded in
``movimiento_cc.referencia`` as ``pago:{medio}:{clave}`` because C-15 adds no
migration; a single parser reads them back for receipts and the daily close.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Protocol

from app.application.auth_service import Principal
from app.application.money import money
from app.application.pacientes import PacienteRecord, PacienteStore
from app.application.rbac import authorize
from app.shared.exceptions import AppError

MONEDA = "ARS"

# Payment media accepted at the counter (C-15). ``mp`` records a payment that
# was already confirmed manually in Mercado Pago; online checkout stays C-10.
MEDIOS_PAGO: tuple[str, ...] = ("efectivo", "transferencia", "mp")

MEDIO_LABELS: dict[str, str] = {
    "efectivo": "Efectivo",
    "transferencia": "Transferencia",
    "mp": "Mercado Pago",
}

PAGO_PREFIX = "pago"
MAX_CLAVE_IDEMPOTENCIA = 48


def build_referencia_pago(medio: str, clave: str) -> str:
    """Encode the medium and idempotency key into the ledger reference."""
    return f"{PAGO_PREFIX}:{medio}:{clave}"


def parse_referencia_pago(
    referencia: str | None,
) -> tuple[str, str] | None:
    """Decode ``pago:{medio}:{clave}``; ``None`` for any other reference."""
    if not referencia:
        return None
    parts = referencia.split(":", 2)
    if len(parts) != 3 or parts[0] != PAGO_PREFIX:
        return None
    medio, clave = parts[1], parts[2]
    if medio not in MEDIOS_PAGO or not clave:
        return None
    return medio, clave


def _clave_idempotencia(value: str | None) -> str:
    """Validate the caller key or mint a fresh one (no dedupe without key)."""
    if value is None:
        return uuid.uuid4().hex
    clave = str(value).strip()
    if not clave or len(clave) > MAX_CLAVE_IDEMPOTENCIA:
        raise AppError("clave de idempotencia invalida", 422)
    if not all(char.isalnum() or char in "-_." for char in clave):
        raise AppError("clave de idempotencia invalida", 422)
    return clave


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _aware(value: datetime.datetime) -> datetime.datetime:
    """Normalize to UTC; naive ledger timestamps are treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


# --- Records ---------------------------------------------------------------


@dataclass(frozen=True)
class CuentaCorrienteRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    moneda: str = MONEDA
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None


@dataclass(frozen=True)
class MovimientoCCRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    cuenta_id: uuid.UUID
    tipo: str
    monto: Decimal
    descripcion: str
    referencia: str | None = None
    plan_tratamiento_id: uuid.UUID | None = None
    ocurrido_at: datetime.datetime | None = None
    created_at: datetime.datetime | None = None


@dataclass(frozen=True)
class CuentaCorrienteView:
    paciente_id: uuid.UUID
    moneda: str
    saldo: Decimal
    movimientos: list[MovimientoCCRecord]
    cuenta: CuentaCorrienteRecord | None = None


@dataclass(frozen=True)
class PagoView:
    """Result of registering a counter payment (credit + derived balance)."""

    movimiento: MovimientoCCRecord
    saldo: Decimal
    medio: str
    referencia: str


@dataclass(frozen=True)
class ReciboPagoView:
    """Payment receipt payload (patient + movement + resulting balance)."""

    movimiento: MovimientoCCRecord
    paciente: PacienteRecord
    medio: str
    clave: str
    saldo: Decimal


# --- Ports -----------------------------------------------------------------


class CuentaCorrienteStore(Protocol):
    async def add(self, cuenta: CuentaCorrienteRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> CuentaCorrienteRecord | None: ...

    async def get_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> CuentaCorrienteRecord | None: ...


class MovimientoCCStore(Protocol):
    async def add(self, movimiento: MovimientoCCRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, movimiento_id: uuid.UUID
    ) -> MovimientoCCRecord | None: ...

    async def get_by_referencia(
        self, tenant_id: uuid.UUID, referencia: str
    ) -> MovimientoCCRecord | None: ...

    async def list_by_cuenta(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> list[MovimientoCCRecord]: ...

    async def list_between(
        self,
        tenant_id: uuid.UUID,
        desde: datetime.datetime,
        hasta: datetime.datetime,
    ) -> list[MovimientoCCRecord]: ...

    async def saldo(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> Decimal: ...


# --- Memory stores ---------------------------------------------------------


class MemoryCuentaCorrienteStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, CuentaCorrienteRecord] = {}

    async def add(self, cuenta: CuentaCorrienteRecord) -> None:
        existing = await self.get_by_paciente(
            cuenta.tenant_id, cuenta.paciente_id
        )
        if existing is not None:
            return
        if cuenta.created_at is None:
            cuenta = replace(cuenta, created_at=_now(), updated_at=_now())
        self._rows[cuenta.id] = cuenta

    async def get(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> CuentaCorrienteRecord | None:
        row = self._rows.get(cuenta_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def get_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> CuentaCorrienteRecord | None:
        for row in self._rows.values():
            if row.tenant_id == tenant_id and row.paciente_id == paciente_id:
                return row
        return None

    def clear(self) -> None:
        self._rows.clear()


class MemoryMovimientoCCStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, MovimientoCCRecord] = {}

    async def add(self, movimiento: MovimientoCCRecord) -> None:
        if movimiento.referencia is not None:
            existing = await self.get_by_referencia(
                movimiento.tenant_id, movimiento.referencia
            )
            if existing is not None:
                return
        if movimiento.created_at is None:
            movimiento = replace(
                movimiento,
                ocurrido_at=movimiento.ocurrido_at or _now(),
                created_at=_now(),
            )
        self._rows[movimiento.id] = movimiento

    async def get(
        self, tenant_id: uuid.UUID, movimiento_id: uuid.UUID
    ) -> MovimientoCCRecord | None:
        row = self._rows.get(movimiento_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def get_by_referencia(
        self, tenant_id: uuid.UUID, referencia: str
    ) -> MovimientoCCRecord | None:
        for row in self._rows.values():
            if row.tenant_id == tenant_id and row.referencia == referencia:
                return row
        return None

    async def list_by_cuenta(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> list[MovimientoCCRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.cuenta_id == cuenta_id
        ]
        rows.sort(
            key=lambda row: (
                row.ocurrido_at or datetime.datetime.min.replace(
                    tzinfo=datetime.UTC
                ),
                row.created_at or datetime.datetime.min.replace(
                    tzinfo=datetime.UTC
                ),
                str(row.id),
            )
        )
        return rows

    async def list_between(
        self,
        tenant_id: uuid.UUID,
        desde: datetime.datetime,
        hasta: datetime.datetime,
    ) -> list[MovimientoCCRecord]:
        inicio, fin = _aware(desde), _aware(hasta)
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and inicio
            <= _aware(row.ocurrido_at or row.created_at or inicio)
            < fin
        ]
        rows.sort(
            key=lambda row: (
                _aware(row.ocurrido_at or row.created_at or inicio),
                str(row.id),
            )
        )
        return rows

    async def saldo(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> Decimal:
        total = Decimal("0.00")
        for row in await self.list_by_cuenta(tenant_id, cuenta_id):
            total += row.monto if row.tipo == "debito" else -row.monto
        return money(total)

    async def update(self, *_args: Any, **_kwargs: Any) -> None:
        raise AppError("movimientos de cuenta corriente son append-only", 409)

    async def delete(self, *_args: Any, **_kwargs: Any) -> None:
        raise AppError("movimientos de cuenta corriente son append-only", 409)

    def clear(self) -> None:
        self._rows.clear()


# --- SQLAlchemy stores -----------------------------------------------------


def _cuenta_from_row(row: Any) -> CuentaCorrienteRecord:
    return CuentaCorrienteRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        paciente_id=row.paciente_id,
        moneda=row.moneda,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _movimiento_from_row(row: Any) -> MovimientoCCRecord:
    return MovimientoCCRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        cuenta_id=row.cuenta_id,
        tipo=row.tipo,
        monto=money(row.monto),
        descripcion=row.descripcion,
        referencia=row.referencia,
        plan_tratamiento_id=row.plan_tratamiento_id,
        ocurrido_at=row.ocurrido_at,
        created_at=row.created_at,
    )


class DbCuentaCorrienteStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, cuenta: CuentaCorrienteRecord) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.domain.clinica.models import CuentaCorriente

        stmt = (
            insert(CuentaCorriente)
            .values(
                id=cuenta.id,
                tenant_id=self._tenant_id,
                paciente_id=cuenta.paciente_id,
                moneda=cuenta.moneda,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "paciente_id"])
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> CuentaCorrienteRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import CuentaCorriente

        stmt = select(CuentaCorriente).where(
            CuentaCorriente.tenant_id == self._tenant_id,
            CuentaCorriente.id == cuenta_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _cuenta_from_row(row) if row is not None else None

    async def get_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> CuentaCorrienteRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import CuentaCorriente

        stmt = select(CuentaCorriente).where(
            CuentaCorriente.tenant_id == self._tenant_id,
            CuentaCorriente.paciente_id == paciente_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _cuenta_from_row(row) if row is not None else None


class DbMovimientoCCStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, movimiento: MovimientoCCRecord) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.domain.clinica.models import MovimientoCC

        stmt = (
            insert(MovimientoCC)
            .values(
                id=movimiento.id,
                tenant_id=self._tenant_id,
                cuenta_id=movimiento.cuenta_id,
                plan_tratamiento_id=movimiento.plan_tratamiento_id,
                tipo=movimiento.tipo,
                monto=movimiento.monto,
                descripcion=movimiento.descripcion,
                referencia=movimiento.referencia,
                ocurrido_at=movimiento.ocurrido_at,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "referencia"]
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, movimiento_id: uuid.UUID
    ) -> MovimientoCCRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import MovimientoCC

        stmt = select(MovimientoCC).where(
            MovimientoCC.tenant_id == self._tenant_id,
            MovimientoCC.id == movimiento_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _movimiento_from_row(row) if row is not None else None

    async def get_by_referencia(
        self, tenant_id: uuid.UUID, referencia: str
    ) -> MovimientoCCRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import MovimientoCC

        stmt = select(MovimientoCC).where(
            MovimientoCC.tenant_id == self._tenant_id,
            MovimientoCC.referencia == referencia,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _movimiento_from_row(row) if row is not None else None

    async def list_by_cuenta(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> list[MovimientoCCRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import MovimientoCC

        stmt = (
            select(MovimientoCC)
            .where(
                MovimientoCC.tenant_id == self._tenant_id,
                MovimientoCC.cuenta_id == cuenta_id,
            )
            .order_by(
                MovimientoCC.ocurrido_at,
                MovimientoCC.created_at,
                MovimientoCC.id,
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_movimiento_from_row(row) for row in rows]

    async def list_between(
        self,
        tenant_id: uuid.UUID,
        desde: datetime.datetime,
        hasta: datetime.datetime,
    ) -> list[MovimientoCCRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import MovimientoCC

        stmt = (
            select(MovimientoCC)
            .where(
                MovimientoCC.tenant_id == self._tenant_id,
                MovimientoCC.ocurrido_at >= desde,
                MovimientoCC.ocurrido_at < hasta,
            )
            .order_by(MovimientoCC.ocurrido_at, MovimientoCC.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_movimiento_from_row(row) for row in rows]

    async def saldo(
        self, tenant_id: uuid.UUID, cuenta_id: uuid.UUID
    ) -> Decimal:
        from sqlalchemy import case, func, select

        from app.domain.clinica.models import MovimientoCC

        signed = case(
            (MovimientoCC.tipo == "debito", MovimientoCC.monto),
            else_=-MovimientoCC.monto,
        )
        stmt = select(func.coalesce(func.sum(signed), 0)).where(
            MovimientoCC.tenant_id == self._tenant_id,
            MovimientoCC.cuenta_id == cuenta_id,
        )
        value = (await self._session.execute(stmt)).scalar_one()
        return money(value or 0)

    async def update(self, *_args: Any, **_kwargs: Any) -> None:
        raise AppError("movimientos de cuenta corriente son append-only", 409)

    async def delete(self, *_args: Any, **_kwargs: Any) -> None:
        raise AppError("movimientos de cuenta corriente son append-only", 409)


# --- Service ---------------------------------------------------------------


class CuentaCorrienteService:
    """Derived balance, internal debits and counter payments (C-14/C-15)."""

    def __init__(
        self,
        cuentas: CuentaCorrienteStore,
        movimientos: MovimientoCCStore,
        pacientes: PacienteStore,
    ) -> None:
        self.cuentas = cuentas
        self.movimientos = movimientos
        self.pacientes = pacientes

    async def obtener_o_crear(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> CuentaCorrienteRecord:
        existing = await self.cuentas.get_by_paciente(tenant_id, paciente_id)
        if existing is not None:
            return existing
        created = CuentaCorrienteRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            paciente_id=paciente_id,
        )
        await self.cuentas.add(created)
        # Concurrent insert: the unique guard keeps one row; return the winner.
        return (
            await self.cuentas.get_by_paciente(tenant_id, paciente_id) or created
        )

    async def obtener(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> CuentaCorrienteView:
        authorize(tuple(principal.roles), "cobros", "R")
        paciente = await self.pacientes.get(principal.tenant_id, paciente_id)
        if paciente is None:
            raise AppError("paciente no encontrado", 404)
        cuenta = await self.cuentas.get_by_paciente(
            principal.tenant_id, paciente_id
        )
        if cuenta is None:
            return CuentaCorrienteView(
                paciente_id=paciente_id,
                moneda=MONEDA,
                saldo=Decimal("0.00"),
                movimientos=[],
            )
        return CuentaCorrienteView(
            paciente_id=paciente_id,
            moneda=cuenta.moneda,
            saldo=await self.movimientos.saldo(
                principal.tenant_id, cuenta.id
            ),
            movimientos=await self.movimientos.list_by_cuenta(
                principal.tenant_id, cuenta.id
            ),
            cuenta=cuenta,
        )

    async def registrar_debito(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        *,
        monto: Any,
        descripcion: str,
        referencia: str | None = None,
        plan_tratamiento_id: uuid.UUID | None = None,
    ) -> MovimientoCCRecord:
        if referencia is not None:
            existing = await self.movimientos.get_by_referencia(
                tenant_id, referencia
            )
            if existing is not None:
                return existing
        amount = money(monto)
        if amount <= 0:
            raise AppError("monto del movimiento debe ser positivo", 422)
        descripcion = (descripcion or "").strip()
        if not descripcion:
            raise AppError("descripcion del movimiento requerida", 422)
        cuenta = await self.obtener_o_crear(tenant_id, paciente_id)
        record = MovimientoCCRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            cuenta_id=cuenta.id,
            tipo="debito",
            monto=amount,
            descripcion=descripcion[:200],
            referencia=referencia,
            plan_tratamiento_id=plan_tratamiento_id,
            ocurrido_at=_now(),
        )
        await self.movimientos.add(record)
        if referencia is not None:
            return (
                await self.movimientos.get_by_referencia(tenant_id, referencia)
                or record
            )
        return record

    async def registrar_pago(
        self,
        principal: Principal,
        paciente_id: uuid.UUID,
        *,
        monto: Any,
        medio: str,
        idempotency_key: str | None = None,
        descripcion: str | None = None,
    ) -> PagoView:
        """Register a counter payment as an idempotent ``credito`` movement.

        ``efectivo|transferencia|mp`` are the accepted media. Repeating the same
        key returns the original movement (single credit) and the current
        derived balance; no key means a new payment every time.
        """
        authorize(tuple(principal.roles), "cobros", "C")
        normalized = (medio or "").strip().lower()
        if normalized not in MEDIOS_PAGO:
            raise AppError("medio de pago invalido", 422)
        paciente = await self.pacientes.get(principal.tenant_id, paciente_id)
        if paciente is None:
            raise AppError("paciente no encontrado", 404)
        clave = _clave_idempotencia(idempotency_key)
        referencia = build_referencia_pago(normalized, clave)
        existing = await self.movimientos.get_by_referencia(
            principal.tenant_id, referencia
        )
        if existing is not None:
            return PagoView(
                movimiento=existing,
                saldo=await self.movimientos.saldo(
                    principal.tenant_id, existing.cuenta_id
                ),
                medio=normalized,
                referencia=referencia,
            )
        amount = money(monto)
        if amount <= 0:
            raise AppError("monto del pago debe ser positivo", 422)
        cuenta = await self.obtener_o_crear(principal.tenant_id, paciente_id)
        texto = (descripcion or "").strip() or (
            f"Cobro en {MEDIO_LABELS[normalized]}"
        )
        record = MovimientoCCRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            cuenta_id=cuenta.id,
            tipo="credito",
            monto=amount,
            descripcion=texto[:200],
            referencia=referencia,
            ocurrido_at=_now(),
        )
        await self.movimientos.add(record)
        saved = (
            await self.movimientos.get_by_referencia(
                principal.tenant_id, referencia
            )
            or record
        )
        return PagoView(
            movimiento=saved,
            saldo=await self.movimientos.saldo(
                principal.tenant_id, cuenta.id
            ),
            medio=normalized,
            referencia=referencia,
        )

    async def recibo(
        self, principal: Principal, movimiento_id: uuid.UUID
    ) -> ReciboPagoView:
        """Receipt payload for a payment movement; 404 for anything else."""
        authorize(tuple(principal.roles), "cobros", "R")
        movimiento = await self.movimientos.get(
            principal.tenant_id, movimiento_id
        )
        parsed = (
            parse_referencia_pago(movimiento.referencia)
            if movimiento is not None
            else None
        )
        if movimiento is None or parsed is None:
            raise AppError("movimiento no encontrado", 404)
        cuenta = await self.cuentas.get(principal.tenant_id, movimiento.cuenta_id)
        if cuenta is None:
            raise AppError("movimiento no encontrado", 404)
        paciente = await self.pacientes.get(
            principal.tenant_id, cuenta.paciente_id
        )
        if paciente is None:
            raise AppError("movimiento no encontrado", 404)
        medio, clave = parsed
        return ReciboPagoView(
            movimiento=movimiento,
            paciente=paciente,
            medio=medio,
            clave=clave,
            saldo=await self.movimientos.saldo(
                principal.tenant_id, cuenta.id
            ),
        )
