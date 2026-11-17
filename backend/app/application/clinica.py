"""C-13 odontogram, attachments and signed-consent application service.

Rules live here (RN-HC-02/04/05) and persistence is behind ``Protocol`` ports
with in-memory doubles for tests and SQLAlchemy stores for the authenticated
API, mirroring the C-11/C-12 staged pattern. Bytes live behind
``StoragePort``; PDFs behind ``PdfWriter``.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from typing import Any, Protocol

from app.application.auth_service import Principal
from app.application.pacientes import (
    AccesoClinicoService,
    HistoriaRecord,
    HistoriaStore,
    PacienteStore,
)
from app.application.rbac import may_modify_evolution
from app.infrastructure.pdf import PdfWriter
from app.infrastructure.storage import SignedURL, StoragePort
from app.shared.exceptions import AppError

ESTADOS_PIEZA = frozenset(
    {
        "sano",
        "caries",
        "obturacion",
        "corona",
        "endodoncia",
        "extraccion",
        "implante",
        "sellador",
    }
)
SUPERFICIES = frozenset(
    {
        "oclusal",
        "mesial",
        "distal",
        "vestibular",
        "lingual",
        "palatina",
        "incisal",
    }
)
ESTADOS_CON_SUPERFICIE = frozenset({"caries", "obturacion", "sellador"})
ESTADOS_SIN_SUPERFICIE = frozenset(
    {"corona", "endodoncia", "extraccion", "implante"}
)
TIPOS_ADJUNTO = frozenset({"rx", "foto", "documento"})
TIPOS_CONSENTIMIENTO = frozenset(
    {"tratamiento", "invasivo", "cirugia", "ortodoncia", "datos"}
)
TIPOS_INVASIVOS = frozenset({"invasivo", "cirugia"})

_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _iso_utc(value: datetime.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC).isoformat(timespec="microseconds")


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _as_aware(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value


async def _historia_con_acceso(
    historias: HistoriaStore,
    acceso: AccesoClinicoService,
    principal: Principal,
    historia_id: uuid.UUID,
) -> HistoriaRecord:
    historia = await historias.get(principal.tenant_id, historia_id)
    if historia is None:
        raise AppError("historia clinica no encontrada", 404)
    if not await acceso.puede_acceder(principal, historia.paciente_id):
        raise AppError("forbidden", 403)
    return historia


# --- Records ---------------------------------------------------------------


@dataclass(frozen=True)
class OdontogramaRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None


@dataclass(frozen=True)
class EventoPiezaRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    odontograma_id: uuid.UUID
    pieza_fdi: int
    estado: str
    autor_usuario_id: uuid.UUID
    fecha: datetime.datetime
    superficie: str | None = None
    autor_profesional_id: uuid.UUID | None = None
    observaciones: str | None = None
    created_at: datetime.datetime | None = None


@dataclass(frozen=True)
class EstadoPiezaActual:
    pieza_fdi: int
    superficie: str | None
    estado: str
    fecha: datetime.datetime
    evento_id: uuid.UUID
    autor_usuario_id: uuid.UUID
    autor_profesional_id: uuid.UUID | None = None


@dataclass(frozen=True)
class OdontogramaView:
    odontograma: OdontogramaRecord
    estado_actual: list[EstadoPiezaActual]


@dataclass(frozen=True)
class AdjuntoRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    tipo: str
    storage_key: str
    nombre_original: str
    content_type: str
    size_bytes: int
    sha256: str
    origen: str | None = None
    subido_por_usuario_id: uuid.UUID | None = None
    created_at: datetime.datetime | None = None


@dataclass(frozen=True)
class ConsentimientoRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    tipo: str
    texto_version: str
    texto: str
    plan_invasivo: bool
    firmante_nombre: str
    firmado_at: datetime.datetime
    ip: str
    dispositivo: str
    firma_hash: str
    pdf_storage_key: str
    pdf_sha256: str
    firmante_dni: str | None = None
    created_by_usuario_id: uuid.UUID | None = None
    created_at: datetime.datetime | None = None


# --- Ports -----------------------------------------------------------------


class OdontogramaStore(Protocol):
    async def add(self, odontograma: OdontogramaRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, odontograma_id: uuid.UUID
    ) -> OdontogramaRecord | None: ...

    async def get_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> OdontogramaRecord | None: ...


class EventoPiezaStore(Protocol):
    async def add(self, evento: EventoPiezaRecord) -> None: ...

    async def list_by_odontograma(
        self, tenant_id: uuid.UUID, odontograma_id: uuid.UUID
    ) -> list[EventoPiezaRecord]: ...


class AdjuntoStore(Protocol):
    async def add(self, adjunto: AdjuntoRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, adjunto_id: uuid.UUID
    ) -> AdjuntoRecord | None: ...

    async def list_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> list[AdjuntoRecord]: ...


class ConsentimientoStore(Protocol):
    async def add(self, consentimiento: ConsentimientoRecord) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, consentimiento_id: uuid.UUID
    ) -> ConsentimientoRecord | None: ...

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[ConsentimientoRecord]: ...

    async def exists_invasivo(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool: ...


# --- Memory stores ---------------------------------------------------------


class MemoryOdontogramaStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, OdontogramaRecord] = {}

    async def add(self, odontograma: OdontogramaRecord) -> None:
        self._rows[odontograma.id] = odontograma

    async def get(
        self, tenant_id: uuid.UUID, odontograma_id: uuid.UUID
    ) -> OdontogramaRecord | None:
        row = self._rows.get(odontograma_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def get_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> OdontogramaRecord | None:
        for row in self._rows.values():
            if (
                row.tenant_id == tenant_id
                and row.historia_clinica_id == historia_id
            ):
                return row
        return None

    def clear(self) -> None:
        self._rows.clear()


class MemoryEventoPiezaStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, EventoPiezaRecord] = {}

    async def add(self, evento: EventoPiezaRecord) -> None:
        if evento.created_at is None:
            evento = replace(evento, created_at=_now())
        self._rows[evento.id] = evento

    async def list_by_odontograma(
        self, tenant_id: uuid.UUID, odontograma_id: uuid.UUID
    ) -> list[EventoPiezaRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and row.odontograma_id == odontograma_id
        ]
        rows.sort(
            key=lambda row: (
                _as_aware(row.fecha),
                _as_aware(row.created_at or _EPOCH),
                str(row.id),
            )
        )
        return rows

    def clear(self) -> None:
        self._rows.clear()


class MemoryAdjuntoStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, AdjuntoRecord] = {}

    async def add(self, adjunto: AdjuntoRecord) -> None:
        if adjunto.created_at is None:
            adjunto = replace(adjunto, created_at=_now())
        self._rows[adjunto.id] = adjunto

    async def get(
        self, tenant_id: uuid.UUID, adjunto_id: uuid.UUID
    ) -> AdjuntoRecord | None:
        row = self._rows.get(adjunto_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def list_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> list[AdjuntoRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and row.historia_clinica_id == historia_id
        ]
        rows.sort(
            key=lambda row: (
                _as_aware(row.created_at or _EPOCH),
                str(row.id),
            )
        )
        return rows

    def clear(self) -> None:
        self._rows.clear()


class MemoryConsentimientoStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, ConsentimientoRecord] = {}

    async def add(self, consentimiento: ConsentimientoRecord) -> None:
        if consentimiento.created_at is None:
            consentimiento = replace(consentimiento, created_at=_now())
        self._rows[consentimiento.id] = consentimiento

    async def get(
        self, tenant_id: uuid.UUID, consentimiento_id: uuid.UUID
    ) -> ConsentimientoRecord | None:
        row = self._rows.get(consentimiento_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[ConsentimientoRecord]:
        rows = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.paciente_id == paciente_id
        ]
        rows.sort(
            key=lambda row: (
                _as_aware(row.firmado_at),
                str(row.id),
            ),
            reverse=True,
        )
        return rows

    async def exists_invasivo(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool:
        return any(
            row.tenant_id == tenant_id
            and row.paciente_id == paciente_id
            and row.plan_invasivo
            for row in self._rows.values()
        )

    def clear(self) -> None:
        self._rows.clear()


# --- SQLAlchemy stores -----------------------------------------------------


def _odontograma_from_row(row: Any) -> OdontogramaRecord:
    return OdontogramaRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        historia_clinica_id=row.historia_clinica_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _evento_from_row(row: Any) -> EventoPiezaRecord:
    return EventoPiezaRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        odontograma_id=row.odontograma_id,
        pieza_fdi=row.pieza_fdi,
        estado=row.estado,
        autor_usuario_id=row.autor_usuario_id,
        fecha=row.fecha,
        superficie=row.superficie,
        autor_profesional_id=row.autor_profesional_id,
        observaciones=row.observaciones,
        created_at=row.created_at,
    )


def _adjunto_from_row(row: Any) -> AdjuntoRecord:
    return AdjuntoRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        historia_clinica_id=row.historia_clinica_id,
        tipo=row.tipo,
        storage_key=row.storage_key,
        nombre_original=row.nombre_original,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        origen=row.origen,
        subido_por_usuario_id=row.subido_por_usuario_id,
        created_at=row.created_at,
    )


def _consentimiento_from_row(row: Any) -> ConsentimientoRecord:
    return ConsentimientoRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        paciente_id=row.paciente_id,
        historia_clinica_id=row.historia_clinica_id,
        tipo=row.tipo,
        texto_version=row.texto_version,
        texto=row.texto,
        plan_invasivo=row.plan_invasivo,
        firmante_nombre=row.firmante_nombre,
        firmado_at=row.firmado_at,
        ip=row.ip,
        dispositivo=row.dispositivo,
        firma_hash=row.firma_hash,
        pdf_storage_key=row.pdf_storage_key,
        pdf_sha256=row.pdf_sha256,
        firmante_dni=row.firmante_dni,
        created_by_usuario_id=row.created_by_usuario_id,
        created_at=row.created_at,
    )


class DbOdontogramaStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, odontograma: OdontogramaRecord) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.domain.clinica.models import Odontograma

        stmt = (
            insert(Odontograma)
            .values(
                id=odontograma.id,
                tenant_id=self._tenant_id,
                historia_clinica_id=odontograma.historia_clinica_id,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "historia_clinica_id"]
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, odontograma_id: uuid.UUID
    ) -> OdontogramaRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import Odontograma

        stmt = select(Odontograma).where(
            Odontograma.tenant_id == self._tenant_id,
            Odontograma.id == odontograma_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _odontograma_from_row(row) if row is not None else None

    async def get_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> OdontogramaRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import Odontograma

        stmt = select(Odontograma).where(
            Odontograma.tenant_id == self._tenant_id,
            Odontograma.historia_clinica_id == historia_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _odontograma_from_row(row) if row is not None else None


class DbEventoPiezaStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, evento: EventoPiezaRecord) -> None:
        from app.domain.clinica.models import EventoPieza

        self._session.add(
            EventoPieza(
                id=evento.id,
                tenant_id=self._tenant_id,
                odontograma_id=evento.odontograma_id,
                pieza_fdi=evento.pieza_fdi,
                superficie=evento.superficie,
                estado=evento.estado,
                fecha=evento.fecha,
                autor_usuario_id=evento.autor_usuario_id,
                autor_profesional_id=evento.autor_profesional_id,
                observaciones=evento.observaciones,
            )
        )
        await self._session.flush()

    async def list_by_odontograma(
        self, tenant_id: uuid.UUID, odontograma_id: uuid.UUID
    ) -> list[EventoPiezaRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import EventoPieza

        stmt = (
            select(EventoPieza)
            .where(
                EventoPieza.tenant_id == self._tenant_id,
                EventoPieza.odontograma_id == odontograma_id,
            )
            .order_by(EventoPieza.fecha, EventoPieza.created_at, EventoPieza.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_evento_from_row(row) for row in rows]


class DbAdjuntoStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, adjunto: AdjuntoRecord) -> None:
        from app.domain.clinica.models import Adjunto

        self._session.add(
            Adjunto(
                id=adjunto.id,
                tenant_id=self._tenant_id,
                historia_clinica_id=adjunto.historia_clinica_id,
                tipo=adjunto.tipo,
                storage_key=adjunto.storage_key,
                nombre_original=adjunto.nombre_original,
                content_type=adjunto.content_type,
                size_bytes=adjunto.size_bytes,
                sha256=adjunto.sha256,
                origen=adjunto.origen,
                subido_por_usuario_id=adjunto.subido_por_usuario_id,
            )
        )
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, adjunto_id: uuid.UUID
    ) -> AdjuntoRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import Adjunto

        stmt = select(Adjunto).where(
            Adjunto.tenant_id == self._tenant_id,
            Adjunto.id == adjunto_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _adjunto_from_row(row) if row is not None else None

    async def list_by_historia(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> list[AdjuntoRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import Adjunto

        stmt = (
            select(Adjunto)
            .where(
                Adjunto.tenant_id == self._tenant_id,
                Adjunto.historia_clinica_id == historia_id,
            )
            .order_by(Adjunto.created_at, Adjunto.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_adjunto_from_row(row) for row in rows]


class DbConsentimientoStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, consentimiento: ConsentimientoRecord) -> None:
        from app.domain.clinica.models import Consentimiento

        self._session.add(
            Consentimiento(
                id=consentimiento.id,
                tenant_id=self._tenant_id,
                paciente_id=consentimiento.paciente_id,
                historia_clinica_id=consentimiento.historia_clinica_id,
                tipo=consentimiento.tipo,
                texto_version=consentimiento.texto_version,
                texto=consentimiento.texto,
                plan_invasivo=consentimiento.plan_invasivo,
                firmante_nombre=consentimiento.firmante_nombre,
                firmante_dni=consentimiento.firmante_dni,
                firmado_at=consentimiento.firmado_at,
                ip=consentimiento.ip,
                dispositivo=consentimiento.dispositivo,
                firma_hash=consentimiento.firma_hash,
                pdf_storage_key=consentimiento.pdf_storage_key,
                pdf_sha256=consentimiento.pdf_sha256,
                created_by_usuario_id=consentimiento.created_by_usuario_id,
            )
        )
        await self._session.flush()

    async def get(
        self, tenant_id: uuid.UUID, consentimiento_id: uuid.UUID
    ) -> ConsentimientoRecord | None:
        from sqlalchemy import select

        from app.domain.clinica.models import Consentimiento

        stmt = select(Consentimiento).where(
            Consentimiento.tenant_id == self._tenant_id,
            Consentimiento.id == consentimiento_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _consentimiento_from_row(row) if row is not None else None

    async def list_by_paciente(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> list[ConsentimientoRecord]:
        from sqlalchemy import select

        from app.domain.clinica.models import Consentimiento

        stmt = (
            select(Consentimiento)
            .where(
                Consentimiento.tenant_id == self._tenant_id,
                Consentimiento.paciente_id == paciente_id,
            )
            .order_by(Consentimiento.firmado_at.desc(), Consentimiento.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_consentimiento_from_row(row) for row in rows]

    async def exists_invasivo(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool:
        from sqlalchemy import select

        from app.domain.clinica.models import Consentimiento

        stmt = (
            select(Consentimiento.id)
            .where(
                Consentimiento.tenant_id == self._tenant_id,
                Consentimiento.paciente_id == paciente_id,
                Consentimiento.plan_invasivo.is_(True),
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).first() is not None


# --- Validation ------------------------------------------------------------


def validar_fdi(pieza_fdi: int) -> None:
    """Reusable FDI validation (C-13 events, C-14 budget lines)."""
    if not 11 <= pieza_fdi <= 48:
        raise AppError("pieza FDI invalida", 422)
    if not 1 <= pieza_fdi % 10 <= 8:
        raise AppError("pieza FDI invalida", 422)
    if not 1 <= pieza_fdi // 10 <= 4:
        raise AppError("pieza FDI invalida", 422)


def validar_superficie(superficie: str | None) -> None:
    """Reusable surface validation against the C-13 catalog."""
    if superficie is not None and superficie not in SUPERFICIES:
        raise AppError("superficie invalida", 422)


def _validar_evento(estado: str, superficie: str | None) -> None:
    if estado not in ESTADOS_PIEZA:
        raise AppError("estado de pieza invalido", 422)
    if superficie is not None and superficie not in SUPERFICIES:
        raise AppError("superficie invalida", 422)
    if estado in ESTADOS_CON_SUPERFICIE and superficie is None:
        raise AppError(f"estado {estado} requiere superficie", 422)
    if estado in ESTADOS_SIN_SUPERFICIE and superficie is not None:
        raise AppError(f"estado {estado} no admite superficie", 422)


def _proyectar_estado(
    eventos: list[EventoPiezaRecord],
) -> list[EstadoPiezaActual]:
    ordered = sorted(
        eventos,
        key=lambda row: (
            _as_aware(row.fecha),
            _as_aware(row.created_at or _EPOCH),
            str(row.id),
        ),
    )
    latest: dict[tuple[int, str | None], EventoPiezaRecord] = {}
    for evento in ordered:
        latest[(evento.pieza_fdi, evento.superficie)] = evento
    return [
        EstadoPiezaActual(
            pieza_fdi=evento.pieza_fdi,
            superficie=evento.superficie,
            estado=evento.estado,
            fecha=evento.fecha,
            evento_id=evento.id,
            autor_usuario_id=evento.autor_usuario_id,
            autor_profesional_id=evento.autor_profesional_id,
        )
        for evento in sorted(
            latest.values(),
            key=lambda row: (row.pieza_fdi, row.superficie or ""),
        )
    ]


def canonical_consent_payload(
    *,
    tenant_id: uuid.UUID,
    paciente_id: uuid.UUID,
    historia_clinica_id: uuid.UUID,
    tipo: str,
    plan_invasivo: bool,
    texto: str,
    texto_version: str,
    firmante_nombre: str,
    firmante_dni: str | None,
    firmado_at: datetime.datetime,
    ip: str,
    dispositivo: str,
) -> bytes:
    """Single canonical encoding used both to sign and to verify."""
    payload = {
        "tenant_id": str(tenant_id),
        "paciente_id": str(paciente_id),
        "historia_clinica_id": str(historia_clinica_id),
        "tipo": tipo,
        "plan_invasivo": bool(plan_invasivo),
        "texto": texto,
        "texto_version": texto_version,
        "firmante_nombre": firmante_nombre,
        "firmante_dni": firmante_dni or "",
        "firmado_at": _iso_utc(firmado_at),
        "ip": ip,
        "dispositivo": dispositivo,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# --- Services --------------------------------------------------------------


class OdontogramaService:
    """FDI odontogram with immutable events and derived current state."""

    def __init__(
        self,
        odontogramas: OdontogramaStore,
        eventos: EventoPiezaStore,
        historias: HistoriaStore,
        acceso: AccesoClinicoService,
    ) -> None:
        self.odontogramas = odontogramas
        self.eventos = eventos
        self.historias = historias
        self.acceso = acceso

    async def _historia(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> HistoriaRecord:
        return await _historia_con_acceso(
            self.historias, self.acceso, principal, historia_id
        )

    async def _obtener_o_crear(
        self, tenant_id: uuid.UUID, historia_id: uuid.UUID
    ) -> OdontogramaRecord:
        existente = await self.odontogramas.get_by_historia(
            tenant_id, historia_id
        )
        if existente is not None:
            return existente
        creado = OdontogramaRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            historia_clinica_id=historia_id,
        )
        await self.odontogramas.add(creado)
        # Concurrent insert: the unique guard keeps one row; return the winner.
        ganador = await self.odontogramas.get_by_historia(tenant_id, historia_id)
        return ganador or creado

    async def obtener(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> OdontogramaView:
        historia = await self._historia(principal, historia_id)
        odontograma = await self._obtener_o_crear(
            principal.tenant_id, historia.id
        )
        eventos = await self.eventos.list_by_odontograma(
            principal.tenant_id, odontograma.id
        )
        return OdontogramaView(
            odontograma=odontograma,
            estado_actual=_proyectar_estado(eventos),
        )

    async def listar_eventos(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> list[EventoPiezaRecord]:
        historia = await self._historia(principal, historia_id)
        odontograma = await self.odontogramas.get_by_historia(
            principal.tenant_id, historia.id
        )
        if odontograma is None:
            return []
        return await self.eventos.list_by_odontograma(
            principal.tenant_id, odontograma.id
        )

    async def registrar_evento(
        self,
        principal: Principal,
        historia_id: uuid.UUID,
        *,
        pieza_fdi: int,
        estado: str,
        superficie: str | None = None,
        fecha: datetime.datetime | None = None,
        observaciones: str | None = None,
    ) -> EventoPiezaRecord:
        if not may_modify_evolution(tuple(principal.roles)):
            raise AppError("forbidden", 403)
        historia = await self._historia(principal, historia_id)
        validar_fdi(pieza_fdi)
        _validar_evento(estado, superficie)
        autor_usuario_id = _as_uuid(principal.sub)
        if autor_usuario_id is None:
            raise AppError("usuario autenticado sin identificador", 422)
        momento = _as_aware(fecha) if fecha is not None else _now()
        if momento > _now() + datetime.timedelta(minutes=5):
            raise AppError("fecha del evento no puede ser futura", 422)
        odontograma = await self._obtener_o_crear(
            principal.tenant_id, historia.id
        )
        evento = EventoPiezaRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            odontograma_id=odontograma.id,
            pieza_fdi=pieza_fdi,
            estado=estado,
            autor_usuario_id=autor_usuario_id,
            fecha=momento,
            superficie=superficie,
            autor_profesional_id=await self.acceso.profesional_actual(principal),
            observaciones=(
                observaciones.strip() if observaciones is not None else None
            ),
        )
        await self.eventos.add(evento)
        return evento


class AdjuntoService:
    """Private RX/photo/document uploads bound to a clinical history."""

    def __init__(
        self,
        adjuntos: AdjuntoStore,
        historias: HistoriaStore,
        acceso: AccesoClinicoService,
        storage: StoragePort,
        *,
        max_bytes: int,
        mime_permitidos: tuple[str, ...],
    ) -> None:
        self.adjuntos = adjuntos
        self.historias = historias
        self.acceso = acceso
        self.storage = storage
        self.max_bytes = max_bytes
        self.mime_permitidos = frozenset(mime_permitidos)

    async def _historia(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> HistoriaRecord:
        return await _historia_con_acceso(
            self.historias, self.acceso, principal, historia_id
        )

    async def subir(
        self,
        principal: Principal,
        historia_id: uuid.UUID,
        *,
        tipo: str,
        nombre_original: str,
        content_type: str,
        data: bytes,
        origen: str | None = None,
    ) -> AdjuntoRecord:
        if not may_modify_evolution(tuple(principal.roles)):
            raise AppError("forbidden", 403)
        historia = await self._historia(principal, historia_id)
        if tipo not in TIPOS_ADJUNTO:
            raise AppError("tipo de adjunto invalido", 422)
        mime = (content_type or "").split(";")[0].strip().lower()
        if mime not in self.mime_permitidos:
            raise AppError("tipo de archivo no permitido", 422)
        if not data:
            raise AppError("archivo vacio", 422)
        if len(data) > self.max_bytes:
            raise AppError("archivo supera el tamano maximo", 422)
        nombre = (nombre_original or "archivo").strip() or "archivo"
        key = f"{principal.tenant_id}/{historia.id}/{uuid.uuid4().hex}"
        sha256 = hashlib.sha256(data).hexdigest()
        await self.storage.put(key, data, mime)
        record = AdjuntoRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            historia_clinica_id=historia.id,
            tipo=tipo,
            storage_key=key,
            nombre_original=nombre[:255],
            content_type=mime[:100],
            size_bytes=len(data),
            sha256=sha256,
            origen=(origen.strip()[:40] if origen else None),
            subido_por_usuario_id=_as_uuid(principal.sub),
        )
        try:
            await self.adjuntos.add(record)
        except Exception:
            await self.storage.delete(key)
            raise
        return record

    async def listar(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> list[AdjuntoRecord]:
        historia = await self._historia(principal, historia_id)
        return await self.adjuntos.list_by_historia(
            principal.tenant_id, historia.id
        )

    async def url_firmada(
        self, principal: Principal, adjunto_id: uuid.UUID
    ) -> SignedURL:
        adjunto = await self.adjuntos.get(principal.tenant_id, adjunto_id)
        if adjunto is None:
            raise AppError("adjunto no encontrado", 404)
        await self._historia(principal, adjunto.historia_clinica_id)
        return self.storage.signed_url(
            adjunto.storage_key, principal.tenant_id
        )


class ConsentimientoService:
    """Signed informed consents with canonical hash and generated PDF."""

    def __init__(
        self,
        consentimientos: ConsentimientoStore,
        historias: HistoriaStore,
        pacientes: PacienteStore,
        acceso: AccesoClinicoService,
        storage: StoragePort,
        pdf: PdfWriter,
    ) -> None:
        self.consentimientos = consentimientos
        self.historias = historias
        self.pacientes = pacientes
        self.acceso = acceso
        self.storage = storage
        self.pdf = pdf

    async def _historia(
        self, principal: Principal, historia_id: uuid.UUID
    ) -> HistoriaRecord:
        return await _historia_con_acceso(
            self.historias, self.acceso, principal, historia_id
        )

    @staticmethod
    def verificar(record: ConsentimientoRecord) -> bool:
        expected = canonical_consent_payload(
            tenant_id=record.tenant_id,
            paciente_id=record.paciente_id,
            historia_clinica_id=record.historia_clinica_id,
            tipo=record.tipo,
            plan_invasivo=record.plan_invasivo,
            texto=record.texto,
            texto_version=record.texto_version,
            firmante_nombre=record.firmante_nombre,
            firmante_dni=record.firmante_dni,
            firmado_at=record.firmado_at,
            ip=record.ip,
            dispositivo=record.dispositivo,
        )
        return hashlib.sha256(expected).hexdigest() == record.firma_hash

    @staticmethod
    def _pdf_lines(record: ConsentimientoRecord) -> list[str]:
        return [
            "CONSENTIMIENTO INFORMADO",
            "",
            f"Tipo: {record.tipo}",
            f"Version del texto: {record.texto_version}",
            f"Plan invasivo: {'si' if record.plan_invasivo else 'no'}",
            f"Paciente (id): {record.paciente_id}",
            f"Historia clinica (id): {record.historia_clinica_id}",
            f"Firmante: {record.firmante_nombre}",
            f"DNI firmante: {record.firmante_dni or '-'}",
            f"Fecha de firma (UTC): {_iso_utc(record.firmado_at)}",
            f"IP: {record.ip}",
            f"Dispositivo: {record.dispositivo}",
            "",
            "Texto aceptado:",
            record.texto,
            "",
            f"Hash SHA-256 de la firma: {record.firma_hash}",
            "",
            "Documento generado electronicamente. Firma electronica simple:",
            "el hash permite verificar que los datos no fueron alterados.",
        ]

    async def crear(
        self,
        principal: Principal,
        *,
        historia_id: uuid.UUID,
        tipo: str,
        texto: str,
        texto_version: str,
        firmante_nombre: str,
        ip: str,
        dispositivo: str,
        firmante_dni: str | None = None,
        plan_invasivo: bool | None = None,
    ) -> ConsentimientoRecord:
        if not may_modify_evolution(tuple(principal.roles)):
            raise AppError("forbidden", 403)
        historia = await self._historia(principal, historia_id)
        if tipo not in TIPOS_CONSENTIMIENTO:
            raise AppError("tipo de consentimiento invalido", 422)
        texto = (texto or "").strip()
        if not texto:
            raise AppError("texto del consentimiento requerido", 422)
        version = (texto_version or "").strip()
        if not version:
            raise AppError("version del texto requerida", 422)
        firmante = (firmante_nombre or "").strip()
        if not firmante:
            raise AppError("firmante requerido", 422)
        invasivo = (
            tipo in TIPOS_INVASIVOS if plan_invasivo is None else bool(plan_invasivo)
        )
        firmado_at = _now()
        payload = canonical_consent_payload(
            tenant_id=principal.tenant_id,
            paciente_id=historia.paciente_id,
            historia_clinica_id=historia.id,
            tipo=tipo,
            plan_invasivo=invasivo,
            texto=texto,
            texto_version=version,
            firmante_nombre=firmante,
            firmante_dni=firmante_dni,
            firmado_at=firmado_at,
            ip=ip,
            dispositivo=dispositivo,
        )
        firma_hash = hashlib.sha256(payload).hexdigest()
        record = ConsentimientoRecord(
            id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            paciente_id=historia.paciente_id,
            historia_clinica_id=historia.id,
            tipo=tipo,
            texto_version=version[:40],
            texto=texto,
            plan_invasivo=invasivo,
            firmante_nombre=firmante[:160],
            firmado_at=firmado_at,
            ip=ip[:64],
            dispositivo=dispositivo[:255],
            firma_hash=firma_hash,
            pdf_storage_key="",
            pdf_sha256="",
            firmante_dni=(firmante_dni.strip()[:20] if firmante_dni else None),
            created_by_usuario_id=_as_uuid(principal.sub),
        )
        pdf_bytes = self.pdf.render(self._pdf_lines(record))
        key = (
            f"{principal.tenant_id}/{historia.id}/consentimientos/"
            f"{uuid.uuid4().hex}.pdf"
        )
        record = replace(
            record,
            pdf_storage_key=key,
            pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        )
        await self.storage.put(key, pdf_bytes, "application/pdf")
        try:
            await self.consentimientos.add(record)
        except Exception:
            await self.storage.delete(key)
            raise
        return record

    async def obtener(
        self, principal: Principal, consentimiento_id: uuid.UUID
    ) -> tuple[ConsentimientoRecord, bool]:
        record = await self.consentimientos.get(
            principal.tenant_id, consentimiento_id
        )
        if record is None:
            raise AppError("consentimiento no encontrado", 404)
        await self._historia(principal, record.historia_clinica_id)
        return record, self.verificar(record)

    async def listar_por_paciente(
        self, principal: Principal, paciente_id: uuid.UUID
    ) -> list[ConsentimientoRecord]:
        paciente = await self.pacientes.get(principal.tenant_id, paciente_id)
        if paciente is None:
            raise AppError("paciente no encontrado", 404)
        if not await self.acceso.puede_acceder(principal, paciente_id):
            raise AppError("forbidden", 403)
        return await self.consentimientos.list_by_paciente(
            principal.tenant_id, paciente_id
        )

    async def pdf_url(
        self, principal: Principal, consentimiento_id: uuid.UUID
    ) -> SignedURL:
        record, _valid = await self.obtener(principal, consentimiento_id)
        return self.storage.signed_url(
            record.pdf_storage_key, principal.tenant_id
        )

    async def tiene_consentimiento_invasivo(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> bool:
        """Contract for C-14: invasive plan requires a signed consent."""
        return await self.consentimientos.exists_invasivo(
            tenant_id, paciente_id
        )

    async def consentimiento_invasivo(
        self, tenant_id: uuid.UUID, paciente_id: uuid.UUID
    ) -> ConsentimientoRecord | None:
        """Most recent invasive consent, used to trace an accepted plan."""
        rows = await self.consentimientos.list_by_paciente(
            tenant_id, paciente_id
        )
        return next((row for row in rows if row.plan_invasivo), None)
