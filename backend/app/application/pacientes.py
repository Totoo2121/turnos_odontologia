"""C-12 pacientes + HCE application service.

Rules live here (RN-HC-01, RN-SE-02/03) and persistence is behind
``Protocol`` ports with in-memory doubles for tests and SQLAlchemy stores for
the authenticated API, mirroring the C-11 staged pattern.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, replace
from typing import Any, Protocol

from app.application.auth_service import Principal
from app.application.rbac import may_modify_evolution
from app.shared.exceptions import AppError

STAFF_ROLES = frozenset({"propietario", "odontologo", "recepcion", "asistente"})
CLINICAL_ROLES = frozenset({"propietario", "odontologo"})


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


# --- Records ---------------------------------------------------------------


@dataclass(frozen=True)
class PacienteRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    nombre: str
    telefono: str
    dni: str | None = None
    email: str | None = None
    obra_social: str | None = None
    consentimiento_datos: bool = False
    consentimiento_at: datetime.datetime | None = None
    is_active: bool = True
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None
    deleted_at: datetime.datetime | None = None


@dataclass(frozen=True)
class HistoriaRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    alergias: str | None = None
    medicacion: str | None = None
    antecedentes: str | None = None
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None


@dataclass(frozen=True)
class EvolucionRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    autor_usuario_id: uuid.UUID
    contenido: str
    autor_profesional_id: uuid.UUID | None = None
    corrige_evolucion_id: uuid.UUID | None = None
    created_at: datetime.datetime | None = None


@dataclass(frozen=True)
class DerivacionRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    hacia_profesional_id: uuid.UUID
    desde_profesional_id: uuid.UUID | None = None
    motivo: str | None = None
    created_by_usuario_id: uuid.UUID | None = None
    created_at: datetime.datetime | None = None


# --- Ports -----------------------------------------------------------------


class PacienteStore(Protocol):
    async def add(self, paciente: PacienteRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> PacienteRecord | None: ...

    async def by_dni(
        self, tenant_id: uuid.UUID, dni: str
    ) -> PacienteRecord | None: ...

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> list[PacienteRecord]: ...

    async def update(self, paciente: PacienteRecord) -> None: ...

    async def soft_delete(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> None: ...

    async def tiene_turnos(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool: ...

    async def tiene_evoluciones(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool: ...


class HistoriaStore(Protocol):
    async def add(self, historia: HistoriaRecord) -> None: ...

    async def get_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> HistoriaRecord | None: ...

    async def get(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> HistoriaRecord | None: ...

    async def update_anamnesis(self, historia: HistoriaRecord) -> None: ...


class EvolucionStore(Protocol):
    async def add(self, evolucion: EvolucionRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, evolucion_id: uuid.UUID
    ) -> EvolucionRecord | None: ...

    async def list_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> list[EvolucionRecord]: ...


class DerivacionStore(Protocol):
    async def add(self, derivacion: DerivacionRecord) -> None: ...

    async def exists(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        hacia_profesional_id: uuid.UUID,
    ) -> bool: ...

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[DerivacionRecord]: ...


class AccesoClinicoStore(Protocol):
    async def profesional_id_for_usuario(
        self, tenant_id: uuid.UUID, usuario_id: uuid.UUID
    ) -> uuid.UUID | None: ...

    async def tiene_turno(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        profesional_id: uuid.UUID,
    ) -> bool: ...


# --- Memory stores ---------------------------------------------------------


class MemoryPacienteStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, PacienteRecord] = {}
        self._turnos: set[tuple[uuid.UUID, uuid.UUID]] = set()
        self._evoluciones: set[tuple[uuid.UUID, uuid.UUID]] = set()

    async def add(self, paciente: PacienteRecord) -> None:
        self._rows[paciente.id] = paciente

    async def get(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> PacienteRecord | None:
        row = self._rows.get(paciente_id)
        if row is None or row.tenant_id != tenant_id or not row.is_active:
            return None
        return row

    async def by_dni(
        self, tenant_id: uuid.UUID, dni: str
    ) -> PacienteRecord | None:
        for row in self._rows.values():
            if row.tenant_id == tenant_id and row.is_active and row.dni == dni:
                return row
        return None

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> list[PacienteRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.is_active
        ]
        if q:
            needle = q.lower()
            rows = [
                row
                for row in rows
                if needle in row.nombre.lower()
                or (row.dni is not None and needle in row.dni.lower())
            ]
        rows.sort(key=lambda row: (row.nombre.lower(), str(row.id)))
        return rows[offset : offset + limit]

    async def update(self, paciente: PacienteRecord) -> None:
        self._rows[paciente.id] = paciente

    async def soft_delete(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> None:
        row = self._rows.get(paciente_id)
        if row is None or row.tenant_id != tenant_id:
            return
        self._rows[paciente_id] = replace(
            row, is_active=False, deleted_at=_now()
        )

    async def tiene_turnos(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool:
        return (tenant_id, paciente_id) in self._turnos

    async def tiene_evoluciones(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool:
        return (tenant_id, paciente_id) in self._evoluciones

    # Test helpers ---------------------------------------------------------
    def registrar_turno(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> None:
        self._turnos.add((tenant_id, paciente_id))

    def registrar_evolucion(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> None:
        self._evoluciones.add((tenant_id, paciente_id))

    def clear(self) -> None:
        self._rows.clear()
        self._turnos.clear()
        self._evoluciones.clear()


class MemoryHistoriaStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, HistoriaRecord] = {}

    async def add(self, historia: HistoriaRecord) -> None:
        self._rows[historia.id] = historia

    async def get_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> HistoriaRecord | None:
        for row in self._rows.values():
            if row.tenant_id == tenant_id and row.paciente_id == paciente_id:
                return row
        return None

    async def get(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> HistoriaRecord | None:
        row = self._rows.get(historia_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def update_anamnesis(self, historia: HistoriaRecord) -> None:
        self._rows[historia.id] = historia

    def clear(self) -> None:
        self._rows.clear()


class MemoryEvolucionStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, EvolucionRecord] = {}

    async def add(self, evolucion: EvolucionRecord) -> None:
        if evolucion.created_at is None:
            evolucion = replace(evolucion, created_at=_now())
        self._rows[evolucion.id] = evolucion

    async def get(
        self, tenant_id: uuid.UUID, evolucion_id: uuid.UUID
    ) -> EvolucionRecord | None:
        row = self._rows.get(evolucion_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def list_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> list[EvolucionRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and row.historia_clinica_id == historia_id
        ]
        rows.sort(
            key=lambda row: (row.created_at or _now(), str(row.id))
        )
        return rows

    def clear(self) -> None:
        self._rows.clear()


class MemoryDerivacionStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, DerivacionRecord] = {}

    async def add(self, derivacion: DerivacionRecord) -> None:
        if derivacion.created_at is None:
            derivacion = replace(derivacion, created_at=_now())
        self._rows[derivacion.id] = derivacion

    async def exists(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        hacia_profesional_id: uuid.UUID,
    ) -> bool:
        return any(
            row.tenant_id == tenant_id
            and row.paciente_id == paciente_id
            and row.hacia_profesional_id == hacia_profesional_id
            for row in self._rows.values()
        )

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[DerivacionRecord]:
        return [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.paciente_id == paciente_id
        ]

    def clear(self) -> None:
        self._rows.clear()


class MemoryAccesoClinicoStore:
    def __init__(self) -> None:
        self._profesional_by_usuario: dict[uuid.UUID, uuid.UUID] = {}
        self._turnos: set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = set()

    async def profesional_id_for_usuario(
        self, tenant_id: uuid.UUID, usuario_id: uuid.UUID
    ) -> uuid.UUID | None:
        return self._profesional_by_usuario.get(usuario_id)

    async def tiene_turno(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        profesional_id: uuid.UUID,
    ) -> bool:
        return (tenant_id, paciente_id, profesional_id) in self._turnos

    # Test helpers ---------------------------------------------------------
    def registrar_profesional(
        self, usuario_id: uuid.UUID, profesional_id: uuid.UUID
    ) -> None:
        self._profesional_by_usuario[usuario_id] = profesional_id

    def registrar_turno(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        profesional_id: uuid.UUID,
    ) -> None:
        self._turnos.add((tenant_id, paciente_id, profesional_id))

    def clear(self) -> None:
        self._profesional_by_usuario.clear()
        self._turnos.clear()


# --- SQLAlchemy stores -----------------------------------------------------


def _paciente_from_row(row: Any) -> PacienteRecord:
    return PacienteRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        nombre=row.nombre,
        telefono=row.telefono,
        dni=row.dni,
        email=row.email,
        obra_social=row.obra_social,
        consentimiento_datos=row.consentimiento_datos,
        consentimiento_at=row.consentimiento_at,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _historia_from_row(row: Any) -> HistoriaRecord:
    return HistoriaRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        paciente_id=row.paciente_id,
        alergias=row.alergias,
        medicacion=row.medicacion,
        antecedentes=row.antecedentes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _evolucion_from_row(row: Any) -> EvolucionRecord:
    return EvolucionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        historia_clinica_id=row.historia_clinica_id,
        autor_usuario_id=row.autor_usuario_id,
        contenido=row.contenido,
        autor_profesional_id=row.autor_profesional_id,
        corrige_evolucion_id=row.corrige_evolucion_id,
        created_at=row.created_at,
    )


def _derivacion_from_row(row: Any) -> DerivacionRecord:
    return DerivacionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        paciente_id=row.paciente_id,
        hacia_profesional_id=row.hacia_profesional_id,
        desde_profesional_id=row.desde_profesional_id,
        motivo=row.motivo,
        created_by_usuario_id=row.created_by_usuario_id,
        created_at=row.created_at,
    )


class DbPacienteStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, paciente: PacienteRecord) -> None:
        from app.domain.pacientes.models import Paciente

        self._session.add(
            Paciente(
                id=paciente.id,
                tenant_id=self._tenant_id,
                nombre=paciente.nombre,
                telefono=paciente.telefono,
                dni=paciente.dni,
                email=paciente.email,
                obra_social=paciente.obra_social,
                consentimiento_datos=paciente.consentimiento_datos,
                consentimiento_at=paciente.consentimiento_at,
            )
        )
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> PacienteRecord | None:
        from sqlalchemy import select

        from app.domain.pacientes.models import Paciente

        stmt = select(Paciente).where(
            Paciente.tenant_id == self._tenant_id,
            Paciente.id == paciente_id,
            Paciente.is_active.is_(True),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _paciente_from_row(row) if row is not None else None

    async def by_dni(
        self, tenant_id: uuid.UUID, dni: str
    ) -> PacienteRecord | None:
        from sqlalchemy import select

        from app.domain.pacientes.models import Paciente

        stmt = select(Paciente).where(
            Paciente.tenant_id == self._tenant_id,
            Paciente.dni == dni,
            Paciente.is_active.is_(True),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _paciente_from_row(row) if row is not None else None

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> list[PacienteRecord]:
        from sqlalchemy import or_, select

        from app.domain.pacientes.models import Paciente

        stmt = select(Paciente).where(
            Paciente.tenant_id == self._tenant_id,
            Paciente.is_active.is_(True),
        )
        if q:
            needle = f"%{q}%"
            stmt = stmt.where(
                or_(Paciente.nombre.ilike(needle), Paciente.dni.ilike(needle))
            )
        stmt = (
            stmt.order_by(Paciente.nombre, Paciente.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_paciente_from_row(row) for row in rows]

    async def update(self, paciente: PacienteRecord) -> None:
        from sqlalchemy import select

        from app.domain.pacientes.models import Paciente

        stmt = select(Paciente).where(
            Paciente.tenant_id == self._tenant_id,
            Paciente.id == paciente.id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return
        row.nombre = paciente.nombre
        row.telefono = paciente.telefono
        row.dni = paciente.dni
        row.email = paciente.email
        row.obra_social = paciente.obra_social
        row.consentimiento_datos = paciente.consentimiento_datos
        row.consentimiento_at = paciente.consentimiento_at
        await self._session.flush()

    async def soft_delete(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> None:
        from sqlalchemy import select

        from app.domain.pacientes.models import Paciente

        stmt = select(Paciente).where(
            Paciente.tenant_id == self._tenant_id,
            Paciente.id == paciente_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return
        row.is_active = False
        row.deleted_at = _now()
        await self._session.flush()

    async def tiene_turnos(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool:
        from sqlalchemy import select

        from app.domain.agenda.models import Turno

        stmt = (
            select(Turno.id)
            .where(
                Turno.tenant_id == self._tenant_id,
                Turno.paciente_id == paciente_id,
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).first() is not None

    async def tiene_evoluciones(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool:
        from sqlalchemy import select

        from app.domain.pacientes.models import Evolucion, HistoriaClinica

        stmt = (
            select(Evolucion.id)
            .join(
                HistoriaClinica,
                Evolucion.historia_clinica_id == HistoriaClinica.id,
            )
            .where(
                Evolucion.tenant_id == self._tenant_id,
                HistoriaClinica.paciente_id == paciente_id,
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).first() is not None


class DbHistoriaStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, historia: HistoriaRecord) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.domain.pacientes.models import HistoriaClinica

        stmt = (
            insert(HistoriaClinica)
            .values(
                id=historia.id,
                tenant_id=self._tenant_id,
                paciente_id=historia.paciente_id,
                alergias=historia.alergias,
                medicacion=historia.medicacion,
                antecedentes=historia.antecedentes,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "paciente_id"]
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> HistoriaRecord | None:
        from sqlalchemy import select

        from app.domain.pacientes.models import HistoriaClinica

        stmt = select(HistoriaClinica).where(
            HistoriaClinica.tenant_id == self._tenant_id,
            HistoriaClinica.paciente_id == paciente_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _historia_from_row(row) if row is not None else None

    async def get(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> HistoriaRecord | None:
        from sqlalchemy import select

        from app.domain.pacientes.models import HistoriaClinica

        stmt = select(HistoriaClinica).where(
            HistoriaClinica.tenant_id == self._tenant_id,
            HistoriaClinica.id == historia_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _historia_from_row(row) if row is not None else None

    async def update_anamnesis(self, historia: HistoriaRecord) -> None:
        from sqlalchemy import select

        from app.domain.pacientes.models import HistoriaClinica

        stmt = select(HistoriaClinica).where(
            HistoriaClinica.tenant_id == self._tenant_id,
            HistoriaClinica.id == historia.id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return
        row.alergias = historia.alergias
        row.medicacion = historia.medicacion
        row.antecedentes = historia.antecedentes
        await self._session.flush()


class DbEvolucionStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, evolucion: EvolucionRecord) -> None:
        from app.domain.pacientes.models import Evolucion

        self._session.add(
            Evolucion(
                id=evolucion.id,
                tenant_id=self._tenant_id,
                historia_clinica_id=evolucion.historia_clinica_id,
                autor_usuario_id=evolucion.autor_usuario_id,
                autor_profesional_id=evolucion.autor_profesional_id,
                contenido=evolucion.contenido,
                corrige_evolucion_id=evolucion.corrige_evolucion_id,
            )
        )
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, evolucion_id: uuid.UUID
    ) -> EvolucionRecord | None:
        from sqlalchemy import select

        from app.domain.pacientes.models import Evolucion

        stmt = select(Evolucion).where(
            Evolucion.tenant_id == self._tenant_id,
            Evolucion.id == evolucion_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _evolucion_from_row(row) if row is not None else None

    async def list_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> list[EvolucionRecord]:
        from sqlalchemy import select

        from app.domain.pacientes.models import Evolucion

        stmt = (
            select(Evolucion)
            .where(
                Evolucion.tenant_id == self._tenant_id,
                Evolucion.historia_clinica_id == historia_id,
            )
            .order_by(Evolucion.created_at, Evolucion.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_evolucion_from_row(row) for row in rows]


class DbDerivacionStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, derivacion: DerivacionRecord) -> None:
        from app.domain.pacientes.models import DerivacionHCE

        self._session.add(
            DerivacionHCE(
                id=derivacion.id,
                tenant_id=self._tenant_id,
                paciente_id=derivacion.paciente_id,
                desde_profesional_id=derivacion.desde_profesional_id,
                hacia_profesional_id=derivacion.hacia_profesional_id,
                motivo=derivacion.motivo,
                created_by_usuario_id=derivacion.created_by_usuario_id,
            )
        )
        await self._session.flush()

    async def exists(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        hacia_profesional_id: uuid.UUID,
    ) -> bool:
        from sqlalchemy import select

        from app.domain.pacientes.models import DerivacionHCE

        stmt = (
            select(DerivacionHCE.id)
            .where(
                DerivacionHCE.tenant_id == self._tenant_id,
                DerivacionHCE.paciente_id == paciente_id,
                DerivacionHCE.hacia_profesional_id == hacia_profesional_id,
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).first() is not None

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[DerivacionRecord]:
        from sqlalchemy import select

        from app.domain.pacientes.models import DerivacionHCE

        stmt = select(DerivacionHCE).where(
            DerivacionHCE.tenant_id == self._tenant_id,
            DerivacionHCE.paciente_id == paciente_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_derivacion_from_row(row) for row in rows]


class DbAccesoClinicoStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def profesional_id_for_usuario(
        self, tenant_id: uuid.UUID, usuario_id: uuid.UUID
    ) -> uuid.UUID | None:
        from sqlalchemy import select

        from app.domain.agenda.models import Profesional

        stmt = (
            select(Profesional.id)
            .where(
                Profesional.tenant_id == self._tenant_id,
                Profesional.usuario_id == usuario_id,
                Profesional.is_active.is_(True),
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def tiene_turno(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        profesional_id: uuid.UUID,
    ) -> bool:
        from sqlalchemy import select

        from app.domain.agenda.models import Turno

        stmt = (
            select(Turno.id)
            .where(
                Turno.tenant_id == self._tenant_id,
                Turno.paciente_id == paciente_id,
                Turno.profesional_id == profesional_id,
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).first() is not None


# --- Services --------------------------------------------------------------


class AccesoClinicoService:
    """RN-SE-02: owner, treating professional or explicit derivation."""

    def __init__(
        self,
        acceso: AccesoClinicoStore,
        derivaciones: DerivacionStore,
    ) -> None:
        self.acceso = acceso
        self.derivaciones = derivaciones

    async def profesional_actual(
        self, principal: Principal
    ) -> uuid.UUID | None:
        usuario_id = _as_uuid(principal.sub)
        if usuario_id is None:
            return None
        return await self.acceso.profesional_id_for_usuario(
            principal.tenant_id, usuario_id
        )

    async def es_tratante(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> bool:
        if not (CLINICAL_ROLES & set(principal.roles)):
            return False
        profesional_id = await self.profesional_actual(principal)
        if profesional_id is None:
            return False
        if await self.acceso.tiene_turno(
            principal.tenant_id, paciente_id, profesional_id
        ):
            return True
        return await self.derivaciones.exists(
            principal.tenant_id, paciente_id, profesional_id
        )

    async def puede_acceder(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> bool:
        if "propietario" in principal.roles:
            return True
        return await self.es_tratante(principal, paciente_id)

    async def puede_derivar(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> bool:
        if "propietario" in principal.roles:
            return True
        if not (CLINICAL_ROLES & set(principal.roles)):
            return False
        profesional_id = await self.profesional_actual(principal)
        if profesional_id is None:
            return False
        return await self.acceso.tiene_turno(
            principal.tenant_id, paciente_id, profesional_id
        )


class PacienteService:
    """Patient CRUD with tenant scoping, DNI uniqueness and soft delete."""

    def __init__(self, pacientes: PacienteStore) -> None:
        self.pacientes = pacientes

    @staticmethod
    def _limpiar_dni(dni: str | None) -> str | None:
        if dni is None:
            return None
        cleaned = dni.strip()
        return cleaned or None

    @staticmethod
    def _validar_consentimiento(
        consentimiento_datos: bool,
        consentimiento_at: datetime.datetime | None,
    ) -> None:
        if consentimiento_datos and consentimiento_at is None:
            raise AppError("consentimiento requiere fecha", 422)
        if not consentimiento_datos and consentimiento_at is not None:
            raise AppError(
                "consentimiento_at requiere consentimiento_datos", 422
            )

    async def crear(
        self,
        *,
        tenant_id: uuid.UUID,
        nombre: str,
        telefono: str,
        dni: str | None = None,
        email: str | None = None,
        obra_social: str | None = None,
        consentimiento_datos: bool = False,
        consentimiento_at: datetime.datetime | None = None,
    ) -> PacienteRecord:
        nombre = nombre.strip()
        telefono = telefono.strip()
        if not nombre:
            raise AppError("nombre requerido", 422)
        if not telefono:
            raise AppError("telefono requerido", 422)
        dni = self._limpiar_dni(dni)
        if dni is not None and await self.pacientes.by_dni(tenant_id, dni):
            raise AppError("dni duplicado en el tenant", 409)
        self._validar_consentimiento(consentimiento_datos, consentimiento_at)
        paciente = PacienteRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            nombre=nombre,
            telefono=telefono,
            dni=dni,
            email=email,
            obra_social=obra_social,
            consentimiento_datos=consentimiento_datos,
            consentimiento_at=consentimiento_at,
        )
        await self.pacientes.add(paciente)
        return paciente

    async def obtener(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> PacienteRecord:
        paciente = await self.pacientes.get(tenant_id, paciente_id)
        if paciente is None:
            raise AppError("paciente no encontrado", 404)
        return paciente

    async def listar(
        self,
        tenant_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> list[PacienteRecord]:
        return await self.pacientes.list(
            tenant_id, limit=limit, offset=offset, q=q
        )

    async def actualizar(
        self,
        tenant_id: uuid.UUID,
        paciente_id: uuid.UUID,
        cambios: dict[str, Any],
    ) -> PacienteRecord:
        actual = await self.obtener(tenant_id, paciente_id)
        nombre = cambios.get("nombre", actual.nombre)
        telefono = cambios.get("telefono", actual.telefono)
        if not isinstance(nombre, str) or not nombre.strip():
            raise AppError("nombre requerido", 422)
        if not isinstance(telefono, str) or not telefono.strip():
            raise AppError("telefono requerido", 422)
        dni = (
            self._limpiar_dni(cambios["dni"])
            if "dni" in cambios
            else actual.dni
        )
        if dni is not None and dni != actual.dni:
            existente = await self.pacientes.by_dni(tenant_id, dni)
            if existente is not None and existente.id != actual.id:
                raise AppError("dni duplicado en el tenant", 409)
        consentimiento_datos = cambios.get("consentimiento_datos")
        if consentimiento_datos is None:
            consentimiento_datos = actual.consentimiento_datos
        consentimiento_at = cambios.get(
            "consentimiento_at", actual.consentimiento_at
        )
        if "consentimiento_datos" in cambios and not consentimiento_datos:
            consentimiento_at = None
        self._validar_consentimiento(
            consentimiento_datos, consentimiento_at
        )
        actualizado = replace(
            actual,
            nombre=nombre.strip(),
            telefono=telefono.strip(),
            dni=dni,
            email=cambios.get("email", actual.email),
            obra_social=cambios.get("obra_social", actual.obra_social),
            consentimiento_datos=consentimiento_datos,
            consentimiento_at=consentimiento_at,
        )
        await self.pacientes.update(actualizado)
        return actualizado

    async def borrar(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> None:
        await self.obtener(tenant_id, paciente_id)
        if await self.pacientes.tiene_turnos(tenant_id, paciente_id):
            raise AppError(
                "no se puede borrar un paciente con turnos", 409
            )
        if await self.pacientes.tiene_evoluciones(tenant_id, paciente_id):
            raise AppError(
                "no se puede borrar un paciente con evoluciones", 409
            )
        await self.pacientes.soft_delete(tenant_id, paciente_id)


class HistoriaClinicaService:
    """Single history per patient plus append-only evolutions."""

    def __init__(
        self,
        historias: HistoriaStore,
        pacientes: PacienteStore,
        evoluciones: EvolucionStore,
        derivaciones: DerivacionStore,
        acceso: AccesoClinicoService,
    ) -> None:
        self.historias = historias
        self.pacientes = pacientes
        self.evoluciones = evoluciones
        self.derivaciones = derivaciones
        self.acceso = acceso

    async def _exigir_acceso(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> None:
        if not await self.acceso.puede_acceder(principal, paciente_id):
            raise AppError("forbidden", 403)

    async def _historia(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> HistoriaRecord:
        historia = await self.historias.get(
            principal.tenant_id, historia_id
        )
        if historia is None:
            raise AppError("historia clinica no encontrada", 404)
        await self._exigir_acceso(principal, historia.paciente_id)
        return historia

    async def obtener_o_crear(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> HistoriaRecord:
        paciente = await self.pacientes.get(
            principal.tenant_id, paciente_id
        )
        if paciente is None:
            raise AppError("paciente no encontrado", 404)
        await self._exigir_acceso(principal, paciente_id)
        existente = await self.historias.get_by_paciente(
            principal.tenant_id, paciente_id
        )
        if existente is not None:
            return existente
        historia = HistoriaRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            paciente_id=paciente_id,
        )
        await self.historias.add(historia)
        # Concurrent insert: the unique guard keeps one row; return the winner.
        creada = await self.historias.get_by_paciente(
            principal.tenant_id, paciente_id
        )
        return creada or historia

    async def obtener(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> HistoriaRecord:
        return await self._historia(principal, historia_id)

    async def actualizar_anamnesis(
        self,
        principal: Principal,
        historia_id: uuid.UUID,
        cambios: dict[str, Any],
    ) -> HistoriaRecord:
        if not may_modify_evolution(tuple(principal.roles)):
            raise AppError("forbidden", 403)
        historia = await self._historia(principal, historia_id)
        actualizada = replace(
            historia,
            alergias=cambios.get("alergias", historia.alergias),
            medicacion=cambios.get("medicacion", historia.medicacion),
            antecedentes=cambios.get(
                "antecedentes", historia.antecedentes
            ),
        )
        await self.historias.update_anamnesis(actualizada)
        return actualizada

    async def listar_evoluciones(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> list[EvolucionRecord]:
        await self._historia(principal, historia_id)
        return await self.evoluciones.list_by_historia(
            principal.tenant_id, historia_id
        )

    async def registrar_evolucion(
        self,
        principal: Principal,
        historia_id: uuid.UUID,
        *,
        contenido: str,
        corrige_evolucion_id: uuid.UUID | None = None,
    ) -> EvolucionRecord:
        if not may_modify_evolution(tuple(principal.roles)):
            raise AppError("forbidden", 403)
        historia = await self._historia(principal, historia_id)
        if not contenido.strip():
            raise AppError("contenido requerido", 422)
        autor_usuario_id = _as_uuid(principal.sub)
        if autor_usuario_id is None:
            raise AppError("usuario autenticado sin identificador", 422)
        if corrige_evolucion_id is not None:
            original = await self.evoluciones.get(
                principal.tenant_id, corrige_evolucion_id
            )
            if (
                original is None
                or original.historia_clinica_id != historia.id
            ):
                raise AppError("evolucion a corregir inexistente", 404)
        autor_profesional_id = await self.acceso.profesional_actual(
            principal
        )
        evolucion = EvolucionRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            historia_clinica_id=historia.id,
            autor_usuario_id=autor_usuario_id,
            contenido=contenido.strip(),
            autor_profesional_id=autor_profesional_id,
            corrige_evolucion_id=corrige_evolucion_id,
        )
        await self.evoluciones.add(evolucion)
        return evolucion

    async def registrar_derivacion(
        self,
        principal: Principal,
        historia_id: uuid.UUID,
        *,
        hacia_profesional_id: uuid.UUID,
        desde_profesional_id: uuid.UUID | None = None,
        motivo: str | None = None,
    ) -> DerivacionRecord:
        historia = await self._historia(principal, historia_id)
        if not await self.acceso.puede_derivar(
            principal, historia.paciente_id
        ):
            raise AppError("forbidden", 403)
        desde = desde_profesional_id
        if desde is None:
            desde = await self.acceso.profesional_actual(principal)
        derivacion = DerivacionRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            paciente_id=historia.paciente_id,
            hacia_profesional_id=hacia_profesional_id,
            desde_profesional_id=desde,
            motivo=motivo,
            created_by_usuario_id=_as_uuid(principal.sub),
        )
        await self.derivaciones.add(derivacion)
        return derivacion
