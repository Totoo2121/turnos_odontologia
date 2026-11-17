"""C-14 budgets, staged treatment plans and acceptance (RN-AD-01/02).

A budget is an issued offer: line prices and descriptions are snapshotted so a
later catalog change never rewrites a quote. Acceptance is idempotent and
produces exactly one staged plan and one debit movement, guarded by two unique
constraints (plan per budget, movement reference). Money is ``Decimal`` end to
end and always quantized half-up in ARS.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Protocol

from app.application.auth_service import Principal
from app.application.clinica import (
    ConsentimientoService,
    validar_fdi,
    validar_superficie,
)
from app.application.cuenta_corriente import (
    CuentaCorrienteService,
    MovimientoCCRecord,
)
from app.application.money import money
from app.application.pacientes import (
    AccesoClinicoService,
    HistoriaStore,
    PacienteStore,
)
from app.application.rbac import may_modify_evolution
from app.shared.exceptions import AppError

MONEDA = "ARS"
ESTADO_BORRADOR = "borrador"
ESTADO_ENVIADO = "enviado"
ESTADO_ACEPTADO = "aceptado"
ESTADO_RECHAZADO = "rechazado"
MAX_ETAPA = 20
TRANSICIONES: dict[str, frozenset[str]] = {
    ESTADO_BORRADOR: frozenset({ESTADO_ENVIADO}),
    ESTADO_ENVIADO: frozenset({ESTADO_ACEPTADO, ESTADO_RECHAZADO}),
}


class _Unset:
    """Sentinel distinguishing "not sent" from an explicit ``None``."""


UNSET: Any = _Unset()

_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _hoy() -> datetime.date:
    """Local calendar day, matching the clinic's validity window."""
    return datetime.date.today()


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


# --- Records ---------------------------------------------------------------


@dataclass(frozen=True)
class PrestacionSnapshot:
    """Catalog data copied into a budget line (never re-read later)."""

    id: uuid.UUID
    nombre: str
    precio: Decimal | None = None
    requiere_consentimiento: bool = False


@dataclass(frozen=True)
class ItemInput:
    """Input for one budget line (create or bulk create)."""

    prestacion_id: uuid.UUID
    cantidad: int = 1
    precio_unitario: Decimal | None = None
    descripcion: str | None = None
    pieza_fdi: int | None = None
    superficie: str | None = None
    etapa: int = 1


@dataclass(frozen=True)
class PresupuestoRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    creado_por_usuario_id: uuid.UUID
    estado: str = ESTADO_BORRADOR
    moneda: str = MONEDA
    total: Decimal = Decimal("0.00")
    validez_hasta: datetime.date | None = None
    enviado_at: datetime.datetime | None = None
    aceptado_at: datetime.datetime | None = None
    rechazado_at: datetime.datetime | None = None
    observaciones: str | None = None
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None


@dataclass(frozen=True)
class PresupuestoItemRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    presupuesto_id: uuid.UUID
    prestacion_id: uuid.UUID
    descripcion: str
    cantidad: int
    precio_unitario: Decimal
    importe: Decimal
    etapa: int = 1
    requiere_consentimiento: bool = False
    pieza_fdi: int | None = None
    superficie: str | None = None
    created_at: datetime.datetime | None = None


@dataclass(frozen=True)
class PlanTratamientoRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    presupuesto_id: uuid.UUID
    paciente_id: uuid.UUID
    total: Decimal
    etapas: int
    consentimiento_id: uuid.UUID | None = None
    estado: str = "activo"
    etapa_actual: int = 1
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None


@dataclass(frozen=True)
class PresupuestoView:
    presupuesto: PresupuestoRecord
    items: list[PresupuestoItemRecord]


@dataclass(frozen=True)
class PlanEtapaView:
    etapa: int
    subtotal: Decimal
    items: list[PresupuestoItemRecord]


@dataclass(frozen=True)
class PlanTratamientoView:
    plan: PlanTratamientoRecord
    etapas: list[PlanEtapaView]


@dataclass(frozen=True)
class AceptacionView:
    presupuesto: PresupuestoRecord
    items: list[PresupuestoItemRecord]
    plan: PlanTratamientoRecord
    movimiento: MovimientoCCRecord | None = None


# --- Ports -----------------------------------------------------------------


class PresupuestoStore(Protocol):
    async def add(self, presupuesto: PresupuestoRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> PresupuestoRecord | None: ...

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        paciente_id: uuid.UUID | None = None,
        estado: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PresupuestoRecord]: ...

    async def update(self, presupuesto: PresupuestoRecord) -> None: ...

    async def delete(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> None: ...


class PresupuestoItemStore(Protocol):
    async def add(self, item: PresupuestoItemRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> PresupuestoItemRecord | None: ...

    async def list_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> list[PresupuestoItemRecord]: ...

    async def update(self, item: PresupuestoItemRecord) -> None: ...

    async def delete(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> None: ...

    async def delete_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> None: ...


class PlanTratamientoStore(Protocol):
    async def add(self, plan: PlanTratamientoRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, plan_id: uuid.UUID
    ) -> PlanTratamientoRecord | None: ...

    async def get_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> PlanTratamientoRecord | None: ...

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[PlanTratamientoRecord]: ...


class PrestacionReader(Protocol):
    async def get(
        self, tenant_id: uuid.UUID, prestacion_id: uuid.UUID
    ) -> PrestacionSnapshot | None: ...


# --- Memory stores ---------------------------------------------------------


class MemoryPresupuestoStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, PresupuestoRecord] = {}

    async def add(self, presupuesto: PresupuestoRecord) -> None:
        if presupuesto.created_at is None:
            presupuesto = replace(
                presupuesto, created_at=_now(), updated_at=_now()
            )
        self._rows[presupuesto.id] = presupuesto

    async def get(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> PresupuestoRecord | None:
        row = self._rows.get(presupuesto_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        paciente_id: uuid.UUID | None = None,
        estado: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PresupuestoRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and (paciente_id is None or row.paciente_id == paciente_id)
            and (estado is None or row.estado == estado)
        ]
        rows.sort(
            key=lambda row: (row.created_at or _EPOCH, str(row.id)),
            reverse=True,
        )
        return rows[offset : offset + limit]

    async def update(self, presupuesto: PresupuestoRecord) -> None:
        if presupuesto.id in self._rows:
            self._rows[presupuesto.id] = presupuesto

    async def delete(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> None:
        row = await self.get(tenant_id, presupuesto_id)
        if row is not None:
            del self._rows[row.id]

    def clear(self) -> None:
        self._rows.clear()


class MemoryPresupuestoItemStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, PresupuestoItemRecord] = {}

    async def add(self, item: PresupuestoItemRecord) -> None:
        if item.created_at is None:
            item = replace(item, created_at=_now())
        self._rows[item.id] = item

    async def get(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> PresupuestoItemRecord | None:
        row = self._rows.get(item_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def list_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> list[PresupuestoItemRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and row.presupuesto_id == presupuesto_id
        ]
        rows.sort(
            key=lambda row: (row.etapa, row.created_at or _EPOCH, str(row.id))
        )
        return rows

    async def update(self, item: PresupuestoItemRecord) -> None:
        if item.id in self._rows:
            self._rows[item.id] = item

    async def delete(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
        row = await self.get(tenant_id, item_id)
        if row is not None:
            del self._rows[row.id]

    async def delete_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> None:
        rows = await self.list_by_presupuesto(tenant_id, presupuesto_id)
        for row in rows:
            del self._rows[row.id]

    def clear(self) -> None:
        self._rows.clear()


class MemoryPlanTratamientoStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, PlanTratamientoRecord] = {}

    async def add(self, plan: PlanTratamientoRecord) -> None:
        existing = await self.get_by_presupuesto(
            plan.tenant_id, plan.presupuesto_id
        )
        if existing is not None:
            return
        if plan.created_at is None:
            plan = replace(plan, created_at=_now(), updated_at=_now())
        self._rows[plan.id] = plan

    async def get(
        self, tenant_id: uuid.UUID, plan_id: uuid.UUID
    ) -> PlanTratamientoRecord | None:
        row = self._rows.get(plan_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def get_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> PlanTratamientoRecord | None:
        for row in self._rows.values():
            if (
                row.tenant_id == tenant_id
                and row.presupuesto_id == presupuesto_id
            ):
                return row
        return None

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[PlanTratamientoRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.paciente_id == paciente_id
        ]
        rows.sort(
            key=lambda row: (row.created_at or _EPOCH, str(row.id)),
            reverse=True,
        )
        return rows

    def clear(self) -> None:
        self._rows.clear()


class MemoryPrestacionReader:
    """In-memory catalog snapshots used by tests instead of the DB reader."""

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, PrestacionSnapshot] = {}

    def add(self, prestacion: PrestacionSnapshot) -> None:
        self._rows[prestacion.id] = prestacion

    async def get(
        self, tenant_id: uuid.UUID, prestacion_id: uuid.UUID
    ) -> PrestacionSnapshot | None:
        return self._rows.get(prestacion_id)

    def clear(self) -> None:
        self._rows.clear()


# --- SQLAlchemy stores -----------------------------------------------------


def _presupuesto_from_row(row: Any) -> PresupuestoRecord:
    return PresupuestoRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        paciente_id=row.paciente_id,
        historia_clinica_id=row.historia_clinica_id,
        creado_por_usuario_id=row.creado_por_usuario_id,
        estado=row.estado,
        moneda=row.moneda,
        total=money(row.total),
        validez_hasta=row.validez_hasta,
        enviado_at=row.enviado_at,
        aceptado_at=row.aceptado_at,
        rechazado_at=row.rechazado_at,
        observaciones=row.observaciones,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _item_from_row(row: Any) -> PresupuestoItemRecord:
    return PresupuestoItemRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        presupuesto_id=row.presupuesto_id,
        prestacion_id=row.prestacion_id,
        descripcion=row.descripcion,
        cantidad=row.cantidad,
        precio_unitario=money(row.precio_unitario),
        importe=money(row.importe),
        etapa=row.etapa,
        requiere_consentimiento=row.requiere_consentimiento,
        pieza_fdi=row.pieza_fdi,
        superficie=row.superficie,
        created_at=row.created_at,
    )


def _plan_from_row(row: Any) -> PlanTratamientoRecord:
    return PlanTratamientoRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        presupuesto_id=row.presupuesto_id,
        paciente_id=row.paciente_id,
        total=money(row.total),
        etapas=row.etapas,
        consentimiento_id=row.consentimiento_id,
        estado=row.estado,
        etapa_actual=row.etapa_actual,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class DbPresupuestoStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, presupuesto: PresupuestoRecord) -> None:
        from app.domain.clinica.models import Presupuesto

        self._session.add(
            Presupuesto(
                id=presupuesto.id,
                tenant_id=self._tenant_id,
                paciente_id=presupuesto.paciente_id,
                historia_clinica_id=presupuesto.historia_clinica_id,
                creado_por_usuario_id=presupuesto.creado_por_usuario_id,
                estado=presupuesto.estado,
                moneda=presupuesto.moneda,
                total=presupuesto.total,
                validez_hasta=presupuesto.validez_hasta,
                enviado_at=presupuesto.enviado_at,
                aceptado_at=presupuesto.aceptado_at,
                rechazado_at=presupuesto.rechazado_at,
                observaciones=presupuesto.observaciones,
            )
        )
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> PresupuestoRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import Presupuesto

        stmt = select(Presupuesto).where(
            Presupuesto.tenant_id == self._tenant_id,
            Presupuesto.id == presupuesto_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _presupuesto_from_row(row) if row is not None else None

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        paciente_id: uuid.UUID | None = None,
        estado: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PresupuestoRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import Presupuesto

        stmt = select(Presupuesto).where(
            Presupuesto.tenant_id == self._tenant_id
        )
        if paciente_id is not None:
            stmt = stmt.where(Presupuesto.paciente_id == paciente_id)
        if estado is not None:
            stmt = stmt.where(Presupuesto.estado == estado)
        stmt = (
            stmt.order_by(
                Presupuesto.created_at.desc(), Presupuesto.id
            )
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_presupuesto_from_row(row) for row in rows]

    async def update(self, presupuesto: PresupuestoRecord) -> None:
        from sqlalchemy import select

        from app.domain.clinica.models import Presupuesto

        stmt = select(Presupuesto).where(
            Presupuesto.tenant_id == self._tenant_id,
            Presupuesto.id == presupuesto.id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return
        row.estado = presupuesto.estado
        row.moneda = presupuesto.moneda
        row.total = presupuesto.total
        row.validez_hasta = presupuesto.validez_hasta
        row.enviado_at = presupuesto.enviado_at
        row.aceptado_at = presupuesto.aceptado_at
        row.rechazado_at = presupuesto.rechazado_at
        row.observaciones = presupuesto.observaciones
        await self._session.flush()

    async def delete(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> None:
        from sqlalchemy import select

        from app.domain.clinica.models import Presupuesto

        stmt = select(Presupuesto).where(
            Presupuesto.tenant_id == self._tenant_id,
            Presupuesto.id == presupuesto_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class DbPresupuestoItemStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, item: PresupuestoItemRecord) -> None:
        from app.domain.clinica.models import PresupuestoItem

        self._session.add(
            PresupuestoItem(
                id=item.id,
                tenant_id=self._tenant_id,
                presupuesto_id=item.presupuesto_id,
                prestacion_id=item.prestacion_id,
                pieza_fdi=item.pieza_fdi,
                superficie=item.superficie,
                descripcion=item.descripcion,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
                importe=item.importe,
                etapa=item.etapa,
                requiere_consentimiento=item.requiere_consentimiento,
            )
        )
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> PresupuestoItemRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import PresupuestoItem

        stmt = select(PresupuestoItem).where(
            PresupuestoItem.tenant_id == self._tenant_id,
            PresupuestoItem.id == item_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _item_from_row(row) if row is not None else None

    async def list_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> list[PresupuestoItemRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import PresupuestoItem

        stmt = (
            select(PresupuestoItem)
            .where(
                PresupuestoItem.tenant_id == self._tenant_id,
                PresupuestoItem.presupuesto_id == presupuesto_id,
            )
            .order_by(
                PresupuestoItem.etapa,
                PresupuestoItem.created_at,
                PresupuestoItem.id,
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_item_from_row(row) for row in rows]

    async def update(self, item: PresupuestoItemRecord) -> None:
        from sqlalchemy import select

        from app.domain.clinica.models import PresupuestoItem

        stmt = select(PresupuestoItem).where(
            PresupuestoItem.tenant_id == self._tenant_id,
            PresupuestoItem.id == item.id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return
        row.pieza_fdi = item.pieza_fdi
        row.superficie = item.superficie
        row.descripcion = item.descripcion
        row.cantidad = item.cantidad
        row.precio_unitario = item.precio_unitario
        row.importe = item.importe
        row.etapa = item.etapa
        row.requiere_consentimiento = item.requiere_consentimiento
        await self._session.flush()

    async def delete(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
        from sqlalchemy import select

        from app.domain.clinica.models import PresupuestoItem

        stmt = select(PresupuestoItem).where(
            PresupuestoItem.tenant_id == self._tenant_id,
            PresupuestoItem.id == item_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def delete_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> None:
        for item in await self.list_by_presupuesto(
            tenant_id, presupuesto_id
        ):
            await self.delete(tenant_id, item.id)


class DbPlanTratamientoStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, plan: PlanTratamientoRecord) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.domain.clinica.models import PlanTratamiento

        stmt = (
            insert(PlanTratamiento)
            .values(
                id=plan.id,
                tenant_id=self._tenant_id,
                presupuesto_id=plan.presupuesto_id,
                paciente_id=plan.paciente_id,
                consentimiento_id=plan.consentimiento_id,
                estado=plan.estado,
                total=plan.total,
                etapas=plan.etapas,
                etapa_actual=plan.etapa_actual,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "presupuesto_id"]
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, plan_id: uuid.UUID
    ) -> PlanTratamientoRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import PlanTratamiento

        stmt = select(PlanTratamiento).where(
            PlanTratamiento.tenant_id == self._tenant_id,
            PlanTratamiento.id == plan_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _plan_from_row(row) if row is not None else None

    async def get_by_presupuesto(
        self, tenant_id: uuid.UUID, presupuesto_id: uuid.UUID
    ) -> PlanTratamientoRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import PlanTratamiento

        stmt = select(PlanTratamiento).where(
            PlanTratamiento.tenant_id == self._tenant_id,
            PlanTratamiento.presupuesto_id == presupuesto_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _plan_from_row(row) if row is not None else None

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[PlanTratamientoRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import PlanTratamiento

        stmt = (
            select(PlanTratamiento)
            .where(
                PlanTratamiento.tenant_id == self._tenant_id,
                PlanTratamiento.paciente_id == paciente_id,
            )
            .order_by(
                PlanTratamiento.created_at.desc(), PlanTratamiento.id
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_plan_from_row(row) for row in rows]


class DbPrestacionReader:
    """Read-only catalog view used to snapshot a budget line."""

    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def get(
        self, tenant_id: uuid.UUID, prestacion_id: uuid.UUID
    ) -> PrestacionSnapshot | None:
        from sqlalchemy import select

        from app.domain.agenda.models import Prestacion

        stmt = select(Prestacion).where(
            Prestacion.tenant_id == self._tenant_id,
            Prestacion.id == prestacion_id,
            Prestacion.is_active.is_(True),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return PrestacionSnapshot(
            id=row.id,
            nombre=row.nombre,
            precio=money(row.precio) if row.precio is not None else None,
            requiere_consentimiento=bool(row.requiere_consentimiento),
        )


# --- Service ---------------------------------------------------------------


class PresupuestoService:
    """Budget lifecycle, exact totals and idempotent acceptance."""

    def __init__(
        self,
        presupuestos: PresupuestoStore,
        items: PresupuestoItemStore,
        planes: PlanTratamientoStore,
        prestaciones: PrestacionReader,
        historias: HistoriaStore,
        pacientes: PacienteStore,
        acceso: AccesoClinicoService,
        cuenta: CuentaCorrienteService,
        consentimientos: ConsentimientoService,
        *,
        validez_dias: int = 30,
    ) -> None:
        self.presupuestos = presupuestos
        self.items = items
        self.planes = planes
        self.prestaciones = prestaciones
        self.historias = historias
        self.pacientes = pacientes
        self.acceso = acceso
        self.cuenta = cuenta
        self.consentimientos = consentimientos
        self.validez_dias = validez_dias

    # --- Guards ---------------------------------------------------------

    @staticmethod
    def _require_escritura(principal: Principal) -> None:
        if not may_modify_evolution(tuple(principal.roles)):
            raise AppError("forbidden", 403)

    @staticmethod
    def _exigir_borrador(record: PresupuestoRecord) -> None:
        if record.estado != ESTADO_BORRADOR:
            raise AppError(
                "solo un presupuesto en borrador puede modificarse", 409
            )

    async def _con_acceso(
        self, principal: Principal, presupuesto_id: uuid.UUID
    ) -> PresupuestoRecord:
        record = await self.presupuestos.get(
            principal.tenant_id, presupuesto_id
        )
        if record is None:
            raise AppError("presupuesto no encontrado", 404)
        if not await self.acceso.puede_acceder(
            principal, record.paciente_id
        ):
            raise AppError("forbidden", 403)
        return record

    async def _historia(
        self,
        principal: Principal,
        paciente_id: uuid.UUID,
        historia_clinica_id: uuid.UUID | None,
    ):
        if historia_clinica_id is not None:
            historia = await self.historias.get(
                principal.tenant_id, historia_clinica_id
            )
            if historia is None or historia.paciente_id != paciente_id:
                raise AppError(
                    "historia clinica no corresponde al paciente", 422
                )
            return historia
        historia = await self.historias.get_by_paciente(
            principal.tenant_id, paciente_id
        )
        if historia is None:
            raise AppError("historia clinica no encontrada", 422)
        return historia

    # --- Items ----------------------------------------------------------

    async def _preparar_item(
        self,
        principal: Principal,
        presupuesto_id: uuid.UUID,
        data: ItemInput,
    ) -> PresupuestoItemRecord:
        if data.cantidad <= 0:
            raise AppError("cantidad invalida", 422)
        if not 1 <= data.etapa <= MAX_ETAPA:
            raise AppError("etapa invalida", 422)
        if data.pieza_fdi is not None:
            validar_fdi(data.pieza_fdi)
        validar_superficie(data.superficie)
        if data.superficie is not None and data.pieza_fdi is None:
            raise AppError("superficie requiere pieza", 422)
        prestacion = await self.prestaciones.get(
            principal.tenant_id, data.prestacion_id
        )
        if prestacion is None:
            raise AppError("prestacion inexistente en el tenant", 422)
        precio = (
            data.precio_unitario
            if data.precio_unitario is not None
            else prestacion.precio
        )
        if precio is None:
            raise AppError("precio requerido", 422)
        unitario = money(precio)
        if unitario < 0:
            raise AppError("precio invalido", 422)
        descripcion = (
            data.descripcion
            if data.descripcion is not None
            else prestacion.nombre
        )
        descripcion = (descripcion or "").strip()
        if not descripcion:
            raise AppError("descripcion requerida", 422)
        return PresupuestoItemRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            presupuesto_id=presupuesto_id,
            prestacion_id=prestacion.id,
            descripcion=descripcion[:200],
            cantidad=data.cantidad,
            precio_unitario=unitario,
            importe=money(unitario * data.cantidad),
            etapa=data.etapa,
            requiere_consentimiento=prestacion.requiere_consentimiento,
            pieza_fdi=data.pieza_fdi,
            superficie=data.superficie,
        )

    async def _recalcular(
        self, record: PresupuestoRecord
    ) -> PresupuestoRecord:
        items = await self.items.list_by_presupuesto(
            record.tenant_id, record.id
        )
        total = money(
            sum((item.importe for item in items), Decimal("0.00"))
        )
        if total != record.total:
            record = replace(record, total=total)
            await self.presupuestos.update(record)
        return record

    async def _view(self, record: PresupuestoRecord) -> PresupuestoView:
        items = await self.items.list_by_presupuesto(
            record.tenant_id, record.id
        )
        return PresupuestoView(presupuesto=record, items=items)

    # --- Budgets --------------------------------------------------------

    async def crear(
        self,
        principal: Principal,
        *,
        paciente_id: uuid.UUID,
        historia_clinica_id: uuid.UUID | None = None,
        validez_hasta: datetime.date | None = None,
        observaciones: str | None = None,
        items: list[ItemInput] | tuple[ItemInput, ...] = (),
    ) -> PresupuestoView:
        self._require_escritura(principal)
        autor = _as_uuid(principal.sub)
        if autor is None:
            raise AppError("usuario autenticado invalido", 422)
        paciente = await self.pacientes.get(
            principal.tenant_id, paciente_id
        )
        if paciente is None:
            raise AppError("paciente no encontrado", 404)
        if not await self.acceso.puede_acceder(principal, paciente_id):
            raise AppError("forbidden", 403)
        historia = await self._historia(
            principal, paciente_id, historia_clinica_id
        )
        if validez_hasta is None:
            validez_hasta = _hoy() + datetime.timedelta(
                days=self.validez_dias
            )
        record = PresupuestoRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            paciente_id=paciente_id,
            historia_clinica_id=historia.id,
            creado_por_usuario_id=autor,
            estado=ESTADO_BORRADOR,
            moneda=MONEDA,
            total=Decimal("0.00"),
            validez_hasta=validez_hasta,
            observaciones=(
                observaciones.strip()[:2000] if observaciones else None
            ),
        )
        prepared = [
            await self._preparar_item(principal, record.id, data)
            for data in items
        ]
        total = money(
            sum((item.importe for item in prepared), Decimal("0.00"))
        )
        record = replace(record, total=total)
        await self.presupuestos.add(record)
        for item in prepared:
            await self.items.add(item)
        return PresupuestoView(presupuesto=record, items=prepared)

    async def obtener(
        self, principal: Principal, presupuesto_id: uuid.UUID
    ) -> PresupuestoView:
        record = await self._con_acceso(principal, presupuesto_id)
        return await self._view(record)

    async def listar(
        self,
        principal: Principal,
        *,
        paciente_id: uuid.UUID | None = None,
        estado: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PresupuestoView]:
        if estado is not None and estado not in TRANSICIONES and (
            estado not in (ESTADO_ACEPTADO, ESTADO_RECHAZADO)
        ):
            raise AppError("estado invalido", 422)
        if paciente_id is not None:
            paciente = await self.pacientes.get(
                principal.tenant_id, paciente_id
            )
            if paciente is None:
                raise AppError("paciente no encontrado", 404)
            if not await self.acceso.puede_acceder(
                principal, paciente_id
            ):
                raise AppError("forbidden", 403)
        elif "propietario" not in principal.roles:
            raise AppError("paciente_id requerido", 422)
        rows = await self.presupuestos.list(
            principal.tenant_id,
            paciente_id=paciente_id,
            estado=estado,
            limit=limit,
            offset=offset,
        )
        return [await self._view(row) for row in rows]

    async def editar(
        self,
        principal: Principal,
        presupuesto_id: uuid.UUID,
        *,
        validez_hasta: Any = UNSET,
        observaciones: Any = UNSET,
    ) -> PresupuestoView:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        self._exigir_borrador(record)
        changes: dict[str, Any] = {}
        if validez_hasta is not UNSET:
            changes["validez_hasta"] = validez_hasta
        if observaciones is not UNSET:
            changes["observaciones"] = (
                observaciones.strip()[:2000] if observaciones else None
            )
        if changes:
            record = replace(record, **changes)
            await self.presupuestos.update(record)
        return await self._view(record)

    async def eliminar(
        self, principal: Principal, presupuesto_id: uuid.UUID
    ) -> None:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        self._exigir_borrador(record)
        await self.items.delete_by_presupuesto(
            record.tenant_id, record.id
        )
        await self.presupuestos.delete(record.tenant_id, record.id)

    # --- Items ----------------------------------------------------------

    async def agregar_item(
        self,
        principal: Principal,
        presupuesto_id: uuid.UUID,
        data: ItemInput,
    ) -> PresupuestoView:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        self._exigir_borrador(record)
        item = await self._preparar_item(
            principal, record.id, data
        )
        await self.items.add(item)
        record = await self._recalcular(record)
        return await self._view(record)

    async def editar_item(
        self,
        principal: Principal,
        presupuesto_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        cantidad: int | None = None,
        precio_unitario: Decimal | None = None,
        descripcion: str | None = None,
        pieza_fdi: Any = UNSET,
        superficie: Any = UNSET,
        etapa: int | None = None,
    ) -> PresupuestoView:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        self._exigir_borrador(record)
        item = await self.items.get(principal.tenant_id, item_id)
        if item is None or item.presupuesto_id != record.id:
            raise AppError("item no encontrado", 404)
        if cantidad is not None and cantidad <= 0:
            raise AppError("cantidad invalida", 422)
        if etapa is not None and not 1 <= etapa <= MAX_ETAPA:
            raise AppError("etapa invalida", 422)
        nueva_pieza = item.pieza_fdi if pieza_fdi is UNSET else pieza_fdi
        nueva_superficie = (
            item.superficie if superficie is UNSET else superficie
        )
        if nueva_pieza is not None:
            validar_fdi(nueva_pieza)
        validar_superficie(nueva_superficie)
        if nueva_superficie is not None and nueva_pieza is None:
            raise AppError("superficie requiere pieza", 422)
        unitario = item.precio_unitario
        if precio_unitario is not None:
            unitario = money(precio_unitario)
            if unitario < 0:
                raise AppError("precio invalido", 422)
        texto = item.descripcion
        if descripcion is not None:
            texto = descripcion.strip()[:200]
            if not texto:
                raise AppError("descripcion requerida", 422)
        cantidad_final = item.cantidad if cantidad is None else cantidad
        item = replace(
            item,
            cantidad=cantidad_final,
            precio_unitario=unitario,
            descripcion=texto,
            importe=money(unitario * cantidad_final),
            etapa=item.etapa if etapa is None else etapa,
            pieza_fdi=nueva_pieza,
            superficie=nueva_superficie,
        )
        await self.items.update(item)
        record = await self._recalcular(record)
        return await self._view(record)

    async def quitar_item(
        self,
        principal: Principal,
        presupuesto_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> PresupuestoView:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        self._exigir_borrador(record)
        item = await self.items.get(principal.tenant_id, item_id)
        if item is None or item.presupuesto_id != record.id:
            raise AppError("item no encontrado", 404)
        await self.items.delete(principal.tenant_id, item.id)
        record = await self._recalcular(record)
        return await self._view(record)

    # --- Transitions ----------------------------------------------------

    async def enviar(
        self, principal: Principal, presupuesto_id: uuid.UUID
    ) -> PresupuestoView:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        self._transicion(record, ESTADO_ENVIADO)
        items = await self.items.list_by_presupuesto(
            record.tenant_id, record.id
        )
        if not items:
            raise AppError("presupuesto sin items", 422)
        record = replace(
            record,
            estado=ESTADO_ENVIADO,
            enviado_at=_now(),
            total=money(
                sum((item.importe for item in items), Decimal("0.00"))
            ),
        )
        await self.presupuestos.update(record)
        return PresupuestoView(presupuesto=record, items=items)

    async def rechazar(
        self, principal: Principal, presupuesto_id: uuid.UUID
    ) -> PresupuestoView:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        self._transicion(record, ESTADO_RECHAZADO)
        record = replace(
            record, estado=ESTADO_RECHAZADO, rechazado_at=_now()
        )
        await self.presupuestos.update(record)
        return await self._view(record)

    async def aceptar(
        self, principal: Principal, presupuesto_id: uuid.UUID
    ) -> AceptacionView:
        record = await self._con_acceso(principal, presupuesto_id)
        self._require_escritura(principal)
        if record.estado == ESTADO_ACEPTADO:
            return await self._aceptacion_existente(record)
        self._transicion(record, ESTADO_ACEPTADO)
        if (
            record.validez_hasta is not None
            and record.validez_hasta < _hoy()
        ):
            raise AppError("presupuesto vencido", 409)
        items = await self.items.list_by_presupuesto(
            record.tenant_id, record.id
        )
        if not items:
            raise AppError("presupuesto sin items", 422)
        total = money(
            sum((item.importe for item in items), Decimal("0.00"))
        )
        consentimiento_id = await self._gate_consentimiento(
            record, items
        )
        plan = PlanTratamientoRecord(
            id=uuid.uuid4(),
            tenant_id=record.tenant_id,
            presupuesto_id=record.id,
            paciente_id=record.paciente_id,
            consentimiento_id=consentimiento_id,
            estado="activo",
            total=total,
            etapas=max(item.etapa for item in items),
            etapa_actual=1,
        )
        await self.planes.add(plan)
        plan = (
            await self.planes.get_by_presupuesto(
                record.tenant_id, record.id
            )
            or plan
        )
        movimiento = None
        if total > 0:
            movimiento = await self.cuenta.registrar_debito(
                record.tenant_id,
                record.paciente_id,
                monto=total,
                descripcion=f"Presupuesto aceptado {record.id}"[:200],
                referencia=f"presupuesto:{record.id}",
                plan_tratamiento_id=plan.id,
            )
        record = replace(
            record, estado=ESTADO_ACEPTADO, aceptado_at=_now(), total=total
        )
        await self.presupuestos.update(record)
        return AceptacionView(
            presupuesto=record,
            items=items,
            plan=plan,
            movimiento=movimiento,
        )

    async def _aceptacion_existente(
        self, record: PresupuestoRecord
    ) -> AceptacionView:
        plan = await self.planes.get_by_presupuesto(
            record.tenant_id, record.id
        )
        if plan is None:
            raise AppError("plan de tratamiento no encontrado", 404)
        movimiento = await self.cuenta.movimientos.get_by_referencia(
            record.tenant_id, f"presupuesto:{record.id}"
        )
        items = await self.items.list_by_presupuesto(
            record.tenant_id, record.id
        )
        return AceptacionView(
            presupuesto=record,
            items=items,
            plan=plan,
            movimiento=movimiento,
        )

    async def _gate_consentimiento(
        self,
        record: PresupuestoRecord,
        items: list[PresupuestoItemRecord],
    ) -> uuid.UUID | None:
        if not any(item.requiere_consentimiento for item in items):
            return None
        tiene = await self.consentimientos.tiene_consentimiento_invasivo(
            record.tenant_id, record.paciente_id
        )
        if not tiene:
            raise AppError("consentimiento_requerido", 409)
        consentimiento = (
            await self.consentimientos.consentimiento_invasivo(
                record.tenant_id, record.paciente_id
            )
        )
        return consentimiento.id if consentimiento is not None else None

    @staticmethod
    def _transicion(
        record: PresupuestoRecord, destino: str
    ) -> None:
        if destino not in TRANSICIONES.get(record.estado, frozenset()):
            raise AppError("transicion invalida", 409)

    # --- Plans ----------------------------------------------------------

    async def obtener_plan(
        self, principal: Principal, plan_id: uuid.UUID
    ) -> PlanTratamientoView:
        plan = await self.planes.get(principal.tenant_id, plan_id)
        if plan is None:
            raise AppError("plan de tratamiento no encontrado", 404)
        if not await self.acceso.puede_acceder(
            principal, plan.paciente_id
        ):
            raise AppError("forbidden", 403)
        return await self._plan_view(plan)

    async def listar_planes(
        self, principal: Principal, *, paciente_id: uuid.UUID
    ) -> list[PlanTratamientoView]:
        paciente = await self.pacientes.get(
            principal.tenant_id, paciente_id
        )
        if paciente is None:
            raise AppError("paciente no encontrado", 404)
        if not await self.acceso.puede_acceder(
            principal, paciente_id
        ):
            raise AppError("forbidden", 403)
        rows = await self.planes.list_by_paciente(
            principal.tenant_id, paciente_id
        )
        return [await self._plan_view(row) for row in rows]

    async def _plan_view(
        self, plan: PlanTratamientoRecord
    ) -> PlanTratamientoView:
        items = await self.items.list_by_presupuesto(
            plan.tenant_id, plan.presupuesto_id
        )
        agrupadas: dict[int, list[PresupuestoItemRecord]] = {}
        for item in items:
            agrupadas.setdefault(item.etapa, []).append(item)
        etapas = [
            PlanEtapaView(
                etapa=numero,
                subtotal=money(
                    sum(
                        (item.importe for item in agrupadas[numero]),
                        Decimal("0.00"),
                    )
                ),
                items=sorted(
                    agrupadas[numero],
                    key=lambda item: (
                        item.created_at or _EPOCH,
                        str(item.id),
                    ),
                ),
            )
            for numero in sorted(agrupadas)
        ]
        return PlanTratamientoView(plan=plan, etapas=etapas)
