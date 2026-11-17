"""C-15 minimal appointment lifecycle over the C-06 model.

C-06 shipped the ``turno`` table, its GIST anti-overlap constraints and RLS, but
never mounted the HTTP lifecycle. This module adds the minimum C-15 needs:
create a turno with the server-computed ``fin``, change its state and cancel it
with the deposit policy. Reprogramming and overbooking remain open C-06 debt.

Ports keep production on SQLAlchemy (tenant-pinned + flush) and tests on memory.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, replace
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError

from app.application.agenda_cobros import AGENDA_TZ
from app.application.auth_service import Principal
from app.application.pacientes import PacienteStore
from app.application.rbac import authorize
from app.shared.exceptions import AppError

ESTADOS_TURNO: tuple[str, ...] = (
    "pendiente",
    "confirmado",
    "reservado-pendiente-pago",
    "atendido",
    "ausente",
    "cancelado",
)

ESTADOS_TERMINALES = frozenset({"atendido", "ausente", "cancelado"})

# Explicit state machine: terminal states never move again.
TRANSICIONES: dict[str, frozenset[str]] = {
    "pendiente": frozenset(
        {"confirmado", "atendido", "ausente", "cancelado"}
    ),
    "confirmado": frozenset({"atendido", "ausente", "cancelado"}),
    "reservado-pendiente-pago": frozenset(
        {"confirmado", "atendido", "ausente", "cancelado"}
    ),
}

ORIGENES = ("recepcion", "control", "mostrador", "portal")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _aware(value: datetime.datetime) -> datetime.datetime:
    """Naive clinic timestamps are clock-local (AGENDA_TZ)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=AGENDA_TZ)
    return value


@dataclass(frozen=True)
class TurnoRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    profesional_id: uuid.UUID
    sillon_id: uuid.UUID
    prestacion_id: uuid.UUID
    inicio: datetime.datetime
    fin: datetime.datetime
    estado: str = "pendiente"
    origen: str = "recepcion"
    paciente_id: uuid.UUID | None = None
    sobreturno: bool = False
    token_portal: str | None = None
    sena_id: uuid.UUID | None = None
    mp_order_id: str | None = None
    contacto_whatsapp: str | None = None
    contacto_email: str | None = None
    confirmado_at: datetime.datetime | None = None


@dataclass(frozen=True)
class PrestacionAgenda:
    id: uuid.UUID
    tenant_id: uuid.UUID
    nombre: str
    duracion_min: int
    buffer_min: int = 0
    sena_obligatoria: bool = False
    monto_sena: Any = None
    anticipacion_min_cancel_hs: int = 24
    intervalo_control_dias: int | None = None

    @property
    def duracion_total(self) -> int:
        """RN-AG-03: ``fin = inicio + duracion_min + buffer``."""
        return self.duracion_min + self.buffer_min


@dataclass(frozen=True)
class ProfesionalAgenda:
    id: uuid.UUID
    tenant_id: uuid.UUID
    nombre: str
    activo: bool = True


@dataclass(frozen=True)
class SillonAgenda:
    id: uuid.UUID
    tenant_id: uuid.UUID
    nombre: str
    activo: bool = True


@dataclass(frozen=True)
class BloqueoAgenda:
    id: uuid.UUID
    tenant_id: uuid.UUID
    inicio: datetime.datetime
    fin: datetime.datetime
    motivo: str
    profesional_id: uuid.UUID | None = None
    sillon_id: uuid.UUID | None = None


@dataclass(frozen=True)
class CancelacionView:
    turno: TurnoRecord
    cancelacion_tardia: bool
    senia_perdida: bool


class TurnoStore(Protocol):
    async def add(self, turno: TurnoRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, turno_id: uuid.UUID
    ) -> TurnoRecord | None: ...

    async def update(self, turno: TurnoRecord) -> None: ...

    async def list_overlaps(
        self,
        tenant_id: uuid.UUID,
        *,
        profesional_id: uuid.UUID,
        sillon_id: uuid.UUID,
        inicio: datetime.datetime,
        fin: datetime.datetime,
    ) -> list[TurnoRecord]: ...


class TurnoCatalogStore(Protocol):
    async def get_prestacion(
        self, tenant_id: uuid.UUID, prestacion_id: uuid.UUID
    ) -> PrestacionAgenda | None: ...

    async def get_profesional(
        self, tenant_id: uuid.UUID, profesional_id: uuid.UUID
    ) -> ProfesionalAgenda | None: ...

    async def get_sillon(
        self, tenant_id: uuid.UUID, sillon_id: uuid.UUID
    ) -> SillonAgenda | None: ...


class BloqueoStore(Protocol):
    async def first_overlap(
        self,
        tenant_id: uuid.UUID,
        *,
        profesional_id: uuid.UUID | None,
        sillon_id: uuid.UUID | None,
        inicio: datetime.datetime,
        fin: datetime.datetime,
    ) -> BloqueoAgenda | None: ...


# --- Memory stores ---------------------------------------------------------


class MemoryTurnoStore:
    def __init__(self, turnos: list[TurnoRecord] | None = None) -> None:
        self._rows: dict[uuid.UUID, TurnoRecord] = {
            turno.id: turno for turno in (turnos or ())
        }

    async def add(self, turno: TurnoRecord) -> None:
        self._rows[turno.id] = turno

    async def get(
        self, tenant_id: uuid.UUID, turno_id: uuid.UUID
    ) -> TurnoRecord | None:
        row = self._rows.get(turno_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def update(self, turno: TurnoRecord) -> None:
        self._rows[turno.id] = turno

    async def list_overlaps(
        self,
        tenant_id: uuid.UUID,
        *,
        profesional_id: uuid.UUID,
        sillon_id: uuid.UUID,
        inicio: datetime.datetime,
        fin: datetime.datetime,
    ) -> list[TurnoRecord]:
        inicio, fin = _aware(inicio), _aware(fin)
        return [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and row.estado != "cancelado"
            and _aware(row.inicio) < fin
            and _aware(row.fin) > inicio
            and (
                row.profesional_id == profesional_id
                or row.sillon_id == sillon_id
            )
        ]

    def clear(self) -> None:
        self._rows.clear()


class MemoryTurnoCatalogStore:
    def __init__(
        self,
        *,
        prestaciones: list[PrestacionAgenda] | None = None,
        profesionales: list[ProfesionalAgenda] | None = None,
        sillones: list[SillonAgenda] | None = None,
    ) -> None:
        self.prestaciones = {
            row.id: row for row in (prestaciones or ())
        }
        self.profesionales = {
            row.id: row for row in (profesionales or ())
        }
        self.sillones = {row.id: row for row in (sillones or ())}

    async def get_prestacion(
        self, tenant_id: uuid.UUID, prestacion_id: uuid.UUID
    ) -> PrestacionAgenda | None:
        row = self.prestaciones.get(prestacion_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def get_profesional(
        self, tenant_id: uuid.UUID, profesional_id: uuid.UUID
    ) -> ProfesionalAgenda | None:
        row = self.profesionales.get(profesional_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def get_sillon(
        self, tenant_id: uuid.UUID, sillon_id: uuid.UUID
    ) -> SillonAgenda | None:
        row = self.sillones.get(sillon_id)
        return row if row is not None and row.tenant_id == tenant_id else None


class MemoryBloqueoStore:
    def __init__(self, bloqueos: list[BloqueoAgenda] | None = None) -> None:
        self._rows: list[BloqueoAgenda] = list(bloqueos or ())

    def add(self, bloqueo: BloqueoAgenda) -> None:
        self._rows.append(bloqueo)

    async def first_overlap(
        self,
        tenant_id: uuid.UUID,
        *,
        profesional_id: uuid.UUID | None,
        sillon_id: uuid.UUID | None,
        inicio: datetime.datetime,
        fin: datetime.datetime,
    ) -> BloqueoAgenda | None:
        inicio, fin = _aware(inicio), _aware(fin)
        candidatos = [
            row
            for row in self._rows
            if row.tenant_id == tenant_id
            and _aware(row.inicio) < fin
            and _aware(row.fin) > inicio
            and (
                (profesional_id is not None and row.profesional_id == profesional_id)
                or (sillon_id is not None and row.sillon_id == sillon_id)
            )
        ]
        candidatos.sort(key=lambda row: _aware(row.inicio))
        return candidatos[0] if candidatos else None


# --- SQLAlchemy stores -----------------------------------------------------


def _turno_from_row(row: Any) -> TurnoRecord:
    return TurnoRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        profesional_id=row.profesional_id,
        sillon_id=row.sillon_id,
        prestacion_id=row.prestacion_id,
        inicio=row.inicio,
        fin=row.fin,
        estado=row.estado,
        origen=row.origen,
        paciente_id=row.paciente_id,
        sobreturno=row.sobreturno,
        token_portal=row.token_portal,
        sena_id=row.sena_id,
        mp_order_id=row.mp_order_id,
        contacto_whatsapp=row.contacto_whatsapp,
        contacto_email=row.contacto_email,
        confirmado_at=row.confirmado_at,
    )


class DbTurnoStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, turno: TurnoRecord) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.domain.agenda.models import Turno

        stmt = insert(Turno).values(
            id=turno.id,
            tenant_id=self._tenant_id,
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
        await self._session.execute(stmt)
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, turno_id: uuid.UUID
    ) -> TurnoRecord | None:
        from sqlalchemy import select

        from app.domain.agenda.models import Turno

        stmt = select(Turno).where(
            Turno.tenant_id == self._tenant_id, Turno.id == turno_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _turno_from_row(row) if row is not None else None

    async def update(self, turno: TurnoRecord) -> None:
        from sqlalchemy import update

        from app.domain.agenda.models import Turno

        stmt = (
            update(Turno)
            .where(
                Turno.tenant_id == self._tenant_id,
                Turno.id == turno.id,
            )
            .values(estado=turno.estado, confirmado_at=turno.confirmado_at)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_overlaps(
        self,
        tenant_id: uuid.UUID,
        *,
        profesional_id: uuid.UUID,
        sillon_id: uuid.UUID,
        inicio: datetime.datetime,
        fin: datetime.datetime,
    ) -> list[TurnoRecord]:
        from sqlalchemy import or_, select

        from app.domain.agenda.models import Turno

        stmt = select(Turno).where(
            Turno.tenant_id == self._tenant_id,
            Turno.estado != "cancelado",
            Turno.inicio < fin,
            Turno.fin > inicio,
            or_(
                Turno.profesional_id == profesional_id,
                Turno.sillon_id == sillon_id,
            ),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_turno_from_row(row) for row in rows]


class DbTurnoCatalogStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def get_prestacion(
        self, tenant_id: uuid.UUID, prestacion_id: uuid.UUID
    ) -> PrestacionAgenda | None:
        from sqlalchemy import select

        from app.domain.agenda.models import Prestacion

        stmt = select(Prestacion).where(
            Prestacion.tenant_id == self._tenant_id,
            Prestacion.id == prestacion_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return PrestacionAgenda(
            id=row.id,
            tenant_id=row.tenant_id,
            nombre=row.nombre,
            duracion_min=row.duracion_min,
            buffer_min=row.buffer_min,
            sena_obligatoria=row.sena_obligatoria,
            monto_sena=row.monto_sena,
            anticipacion_min_cancel_hs=row.anticipacion_min_cancel_hs,
            intervalo_control_dias=row.intervalo_control_dias,
        )

    async def get_profesional(
        self, tenant_id: uuid.UUID, profesional_id: uuid.UUID
    ) -> ProfesionalAgenda | None:
        from sqlalchemy import select

        from app.domain.agenda.models import Profesional

        stmt = select(Profesional).where(
            Profesional.tenant_id == self._tenant_id,
            Profesional.id == profesional_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ProfesionalAgenda(
            id=row.id,
            tenant_id=row.tenant_id,
            nombre=row.nombre,
            activo=row.activo,
        )

    async def get_sillon(
        self, tenant_id: uuid.UUID, sillon_id: uuid.UUID
    ) -> SillonAgenda | None:
        from sqlalchemy import select

        from app.domain.agenda.models import Sillon

        stmt = select(Sillon).where(
            Sillon.tenant_id == self._tenant_id, Sillon.id == sillon_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return SillonAgenda(
            id=row.id,
            tenant_id=row.tenant_id,
            nombre=row.nombre,
            activo=row.activo,
        )


class DbBloqueoStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def first_overlap(
        self,
        tenant_id: uuid.UUID,
        *,
        profesional_id: uuid.UUID | None,
        sillon_id: uuid.UUID | None,
        inicio: datetime.datetime,
        fin: datetime.datetime,
    ) -> BloqueoAgenda | None:
        from sqlalchemy import or_, select

        from app.domain.agenda.models import Bloqueo

        conditions = []
        if profesional_id is not None:
            conditions.append(Bloqueo.profesional_id == profesional_id)
        if sillon_id is not None:
            conditions.append(Bloqueo.sillon_id == sillon_id)
        if not conditions:
            return None
        stmt = (
            select(Bloqueo)
            .where(
                Bloqueo.tenant_id == self._tenant_id,
                Bloqueo.inicio < fin,
                Bloqueo.fin > inicio,
                or_(*conditions),
            )
            .order_by(Bloqueo.inicio.asc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return BloqueoAgenda(
            id=row.id,
            tenant_id=row.tenant_id,
            inicio=row.inicio,
            fin=row.fin,
            motivo=row.motivo,
            profesional_id=row.profesional_id,
            sillon_id=row.sillon_id,
        )


# --- Service ---------------------------------------------------------------


class TurnoService:
    """Minimal lifecycle: create, change state and cancel (C-15)."""

    def __init__(
        self,
        turnos: TurnoStore,
        catalogo: TurnoCatalogStore,
        bloqueos: BloqueoStore,
        pacientes: PacienteStore,
    ) -> None:
        self.turnos = turnos
        self.catalogo = catalogo
        self.bloqueos = bloqueos
        self.pacientes = pacientes

    async def crear(
        self,
        principal: Principal,
        *,
        paciente_id: uuid.UUID,
        profesional_id: uuid.UUID,
        sillon_id: uuid.UUID,
        prestacion_id: uuid.UUID,
        inicio: datetime.datetime,
        origen: str = "recepcion",
    ) -> TurnoRecord:
        authorize(tuple(principal.roles), "agenda", "C")
        tenant = principal.tenant_id
        if origen not in ORIGENES:
            raise AppError("origen de turno invalido", 422)
        prestacion = await self.catalogo.get_prestacion(
            tenant, prestacion_id
        )
        if prestacion is None:
            raise AppError("prestacion inexistente en el tenant", 422)
        profesional = await self.catalogo.get_profesional(
            tenant, profesional_id
        )
        if profesional is None:
            raise AppError("profesional inexistente en el tenant", 422)
        if not profesional.activo:
            raise AppError("profesional inactivo", 422)
        sillon = await self.catalogo.get_sillon(tenant, sillon_id)
        if sillon is None:
            raise AppError("sillon inexistente en el tenant", 422)
        if not sillon.activo:
            raise AppError("sillon inactivo", 422)
        if await self.pacientes.get(tenant, paciente_id) is None:
            raise AppError("paciente no encontrado", 404)

        inicio = _aware(inicio)
        fin = inicio + datetime.timedelta(minutes=prestacion.duracion_total)
        bloqueo = await self.bloqueos.first_overlap(
            tenant,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            inicio=inicio,
            fin=fin,
        )
        if bloqueo is not None:
            raise AppError(f"horario bloqueado: {bloqueo.motivo}", 409)
        if await self.turnos.list_overlaps(
            tenant,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            inicio=inicio,
            fin=fin,
        ):
            raise AppError("el horario se solapa con otro turno", 409)

        turno = TurnoRecord(
            id=uuid.uuid4(),
            tenant_id=tenant,
            paciente_id=paciente_id,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            prestacion_id=prestacion_id,
            inicio=inicio,
            fin=fin,
            estado="pendiente",
            origen=origen,
        )
        try:
            await self.turnos.add(turno)
        except IntegrityError:
            raise AppError(
                "el horario se solapa con otro turno", 409
            ) from None
        return await self.turnos.get(tenant, turno.id) or turno

    async def cambiar_estado(
        self, principal: Principal, turno_id: uuid.UUID, estado: str
    ) -> TurnoRecord:
        authorize(tuple(principal.roles), "agenda", "U")
        if estado not in ESTADOS_TURNO:
            raise AppError("estado de turno invalido", 422)
        turno = await self._get(principal.tenant_id, turno_id)
        if turno.estado == estado:
            return turno
        if turno.estado in ESTADOS_TERMINALES:
            raise AppError(
                f"transicion invalida desde {turno.estado}", 409
            )
        if estado not in TRANSICIONES.get(turno.estado, frozenset()):
            raise AppError(
                f"transicion invalida desde {turno.estado}", 409
            )
        if estado == "cancelado":
            return (await self.cancelar(principal, turno_id)).turno
        actualizado = replace(
            turno,
            estado=estado,
            confirmado_at=(
                _now() if estado == "confirmado" else turno.confirmado_at
            ),
        )
        await self.turnos.update(actualizado)
        return actualizado

    async def cancelar(
        self,
        principal: Principal,
        turno_id: uuid.UUID,
        *,
        ahora: datetime.datetime | None = None,
    ) -> CancelacionView:
        authorize(tuple(principal.roles), "agenda", "U")
        turno = await self._get(principal.tenant_id, turno_id)
        if turno.estado == "cancelado":
            return CancelacionView(
                turno=turno,
                cancelacion_tardia=False,
                senia_perdida=False,
            )
        if turno.estado in ESTADOS_TERMINALES:
            raise AppError(
                f"no se puede cancelar un turno {turno.estado}", 409
            )
        prestacion = await self.catalogo.get_prestacion(
            principal.tenant_id, turno.prestacion_id
        )
        anticipacion = (
            prestacion.anticipacion_min_cancel_hs if prestacion else 24
        )
        obligatoria = bool(prestacion and prestacion.sena_obligatoria)
        referencia = ahora or _now()
        limite = _aware(turno.inicio) - datetime.timedelta(hours=anticipacion)
        tardia = _aware(referencia) > limite
        actualizado = replace(turno, estado="cancelado")
        await self.turnos.update(actualizado)
        return CancelacionView(
            turno=actualizado,
            cancelacion_tardia=tardia,
            senia_perdida=tardia and obligatoria,
        )

    async def obtener(
        self, principal: Principal, turno_id: uuid.UUID
    ) -> TurnoRecord:
        authorize(tuple(principal.roles), "agenda", "R")
        return await self._get(principal.tenant_id, turno_id)

    async def _get(
        self, tenant_id: uuid.UUID, turno_id: uuid.UUID
    ) -> TurnoRecord:
        turno = await self.turnos.get(tenant_id, turno_id)
        if turno is None:
            raise AppError("turno no encontrado", 404)
        return turno
