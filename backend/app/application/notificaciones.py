"""C-11 notification application service.

Rules live here (RN-NO-01..05) and external channels are ports:
``WhatsAppClient`` / ``EmailClient``. Persistence is behind
``RecordatorioStore`` / ``PlantillaStore`` with in-memory doubles for tests
and SQLAlchemy stores for the authenticated API.

The worker turn scanner is an in-memory registry (same staged pattern used by
C-09/C-10) so jobs are testable without a live multi-tenant session.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.infrastructure.smtp import (
    EmailClient,
    EmailError,
    PermanentEmailError,
    TransientEmailError,
)
from app.infrastructure.whatsapp_bsp import (
    PermanentWhatsAppError,
    TransientWhatsAppError,
    WhatsAppClient,
    WhatsAppError,
)
from app.shared.exceptions import AppError

# --- Channels / types / states (mirror the DB CHECK constraints) -------------
CANAL_WHATSAPP = "whatsapp"
CANAL_EMAIL = "email"
CANAL_INTERNO = "interno"

TIPO_T48H = "t48h"
TIPO_T24H = "t24h"
TIPO_CONFIRMACION = "confirmacion"
TIPO_RECALL_AUSENTE = "recall_ausente"
TIPO_CONTROL = "control"
TIPO_AVISO_RECEPCION = "aviso_recepcion"

ESTADO_PENDIENTE = "pendiente"
ESTADO_ENVIADO = "enviado"
ESTADO_FALLIDO = "fallido"
ESTADO_CONFIRMADO = "confirmado"
ESTADO_CANCELADO = "cancelado"

ESTADOS_TURNO_ACTIVOS = frozenset(
    {"pendiente", "reservado", "confirmado", "reservado-pendiente-pago"}
)

PLANTILLA_POR_TIPO: dict[str, str] = {
    TIPO_T48H: "recordatorio_t48h",
    TIPO_T24H: "recordatorio_t24h",
    TIPO_CONFIRMACION: "confirmacion",
    TIPO_RECALL_AUSENTE: "recall_ausente",
    TIPO_CONTROL: "control",
    TIPO_AVISO_RECEPCION: "aviso_recepcion",
}

# Platform-provided default templates live under this synthetic tenant id.
PLANTILLA_GLOBAL_TENANT = uuid.UUID(int=0)


class NotificacionError(AppError):
    """Base notification application error."""


@dataclass(frozen=True)
class PlantillaRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    clave: str
    canal: str
    idioma: str
    version: int
    cuerpo: str
    meta_template_name: str | None = None
    activo: bool = True


@dataclass
class RecordatorioRecord:
    id: uuid.UUID
    tenant_id: uuid.UUID
    turno_id: uuid.UUID
    canal: str
    tipo: str
    plantilla: str
    enviar_at: datetime.datetime
    estado: str = ESTADO_PENDIENTE
    paciente_id: uuid.UUID | None = None
    destinatario: str | None = None
    intentos: int = 0
    ultimo_error: str | None = None
    confirmado_at: datetime.datetime | None = None
    created_at: datetime.datetime | None = None


@dataclass(frozen=True)
class TurnoNotificable:
    """Minimal turno projection needed by notification jobs."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    inicio: datetime.datetime
    fin: datetime.datetime
    estado: str
    paciente_id: uuid.UUID | None = None
    contacto_whatsapp: str | None = None
    contacto_email: str | None = None
    confirmado_at: datetime.datetime | None = None
    intervalo_control_dias: int | None = None
    prestacion_id: uuid.UUID | None = None
    token_portal: str | None = None


class PlantillaStore(Protocol):
    async def get_activa(
        self, *, tenant_id: uuid.UUID, clave: str, canal: str, idioma: str = "es"
    ) -> PlantillaRecord | None: ...

    async def list_plantillas(self, tenant_id: uuid.UUID) -> list[PlantillaRecord]: ...

    async def add(self, plantilla: PlantillaRecord) -> None: ...


class RecordatorioStore(Protocol):
    async def add(self, rec: RecordatorioRecord) -> None: ...

    async def find(
        self, *, turno_id: uuid.UUID, canal: str, tipo: str
    ) -> RecordatorioRecord | None: ...

    async def update(self, rec: RecordatorioRecord) -> None: ...

    async def list_by_tenant(
        self, tenant_id: uuid.UUID, *, tipo: str | None = None, limit: int = 100
    ) -> list[RecordatorioRecord]: ...


class TurnoNotificacionStore(Protocol):
    async def add(self, turno: TurnoNotificable) -> None: ...

    async def get(self, turno_id: uuid.UUID) -> TurnoNotificable | None: ...

    async def find_by_token(self, token: str) -> TurnoNotificable | None: ...

    async def list_activos(self) -> list[TurnoNotificable]: ...

    async def list_por_estado(self, estado: str) -> list[TurnoNotificable]: ...

    async def list_por_paciente(
        self, paciente_id: uuid.UUID
    ) -> list[TurnoNotificable]: ...


def _aware(value: datetime.datetime) -> datetime.datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=datetime.UTC)


class MemoryPlantillaStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[Any, ...], PlantillaRecord] = {}

    @staticmethod
    def _key(p: PlantillaRecord) -> tuple[Any, ...]:
        return (p.tenant_id, p.clave, p.canal, p.idioma, p.version)

    async def add(self, plantilla: PlantillaRecord) -> None:
        self._rows[self._key(plantilla)] = plantilla

    async def get_activa(
        self, *, tenant_id: uuid.UUID, clave: str, canal: str, idioma: str = "es"
    ) -> PlantillaRecord | None:
        def match(scope: uuid.UUID) -> list[PlantillaRecord]:
            return [
                p
                for p in self._rows.values()
                if p.tenant_id == scope
                and p.clave == clave
                and p.canal == canal
                and p.idioma == idioma
                and p.activo
            ]

        # Tenant override first; platform-provided defaults as fallback.
        matches = match(tenant_id) or match(PLANTILLA_GLOBAL_TENANT)
        return max(matches, key=lambda p: p.version) if matches else None

    async def list_plantillas(self, tenant_id: uuid.UUID) -> list[PlantillaRecord]:
        rows = [p for p in self._rows.values() if p.tenant_id == tenant_id]
        return sorted(rows, key=lambda p: (p.clave, p.canal, p.version))

    def clear(self) -> None:
        self._rows.clear()


class MemoryRecordatorioStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[uuid.UUID, str, str], RecordatorioRecord] = {}

    async def add(self, rec: RecordatorioRecord) -> None:
        self._rows[(rec.turno_id, rec.canal, rec.tipo)] = rec

    async def find(
        self, *, turno_id: uuid.UUID, canal: str, tipo: str
    ) -> RecordatorioRecord | None:
        return self._rows.get((turno_id, canal, tipo))

    async def update(self, rec: RecordatorioRecord) -> None:
        self._rows[(rec.turno_id, rec.canal, rec.tipo)] = rec

    async def list_by_tenant(
        self, tenant_id: uuid.UUID, *, tipo: str | None = None, limit: int = 100
    ) -> list[RecordatorioRecord]:
        rows = [r for r in self._rows.values() if r.tenant_id == tenant_id]
        if tipo is not None:
            rows = [r for r in rows if r.tipo == tipo]
        return sorted(
            rows, key=lambda r: _aware(r.created_at or r.enviar_at), reverse=True
        )[:limit]

    def clear(self) -> None:
        self._rows.clear()


class MemoryTurnoNotificacionStore:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, TurnoNotificable] = {}

    async def add(self, turno: TurnoNotificable) -> None:
        self._rows[turno.id] = turno

    async def get(self, turno_id: uuid.UUID) -> TurnoNotificable | None:
        return self._rows.get(turno_id)

    async def find_by_token(self, token: str) -> TurnoNotificable | None:
        for turno in self._rows.values():
            if turno.token_portal == token:
                return turno
        return None

    async def list_activos(self) -> list[TurnoNotificable]:
        return [t for t in self._rows.values() if t.estado in ESTADOS_TURNO_ACTIVOS]

    async def list_por_estado(self, estado: str) -> list[TurnoNotificable]:
        return [t for t in self._rows.values() if t.estado == estado]

    async def list_por_paciente(
        self, paciente_id: uuid.UUID
    ) -> list[TurnoNotificable]:
        rows = [t for t in self._rows.values() if t.paciente_id == paciente_id]
        return sorted(rows, key=lambda t: _aware(t.fin), reverse=True)

    def reset(self) -> None:
        self._rows.clear()


# --- SQLAlchemy stores (authenticated API / production) ---------------------


def _plantilla_from_row(row: Any) -> PlantillaRecord:
    return PlantillaRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        clave=row.clave,
        canal=row.canal,
        idioma=row.idioma,
        version=row.version,
        cuerpo=row.cuerpo,
        meta_template_name=row.meta_template_name,
        activo=row.activo,
    )


def _recordatorio_from_row(row: Any) -> RecordatorioRecord:
    return RecordatorioRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        turno_id=row.turno_id,
        canal=row.canal,
        tipo=row.tipo,
        plantilla=row.plantilla,
        enviar_at=row.enviar_at,
        estado=row.estado,
        paciente_id=row.paciente_id,
        destinatario=row.destinatario,
        intentos=row.intentos,
        ultimo_error=row.ultimo_error,
        confirmado_at=row.confirmado_at,
        created_at=row.created_at,
    )


class DbPlantillaStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def get_activa(
        self, *, tenant_id: uuid.UUID, clave: str, canal: str, idioma: str = "es"
    ) -> PlantillaRecord | None:
        from sqlalchemy import select

        from app.domain.notificaciones.models import PlantillaMensaje

        stmt = (
            select(PlantillaMensaje)
            .where(
                PlantillaMensaje.tenant_id == self._tenant_id,
                PlantillaMensaje.clave == clave,
                PlantillaMensaje.canal == canal,
                PlantillaMensaje.idioma == idioma,
                PlantillaMensaje.activo.is_(True),
            )
            .order_by(PlantillaMensaje.version.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _plantilla_from_row(row) if row is not None else None

    async def list_plantillas(self, tenant_id: uuid.UUID) -> list[PlantillaRecord]:
        from sqlalchemy import select

        from app.domain.notificaciones.models import PlantillaMensaje

        stmt = (
            select(PlantillaMensaje)
            .where(PlantillaMensaje.tenant_id == self._tenant_id)
            .order_by(
                PlantillaMensaje.clave,
                PlantillaMensaje.canal,
                PlantillaMensaje.version,
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_plantilla_from_row(row) for row in rows]

    async def add(self, plantilla: PlantillaRecord) -> None:
        from app.domain.notificaciones.models import PlantillaMensaje

        self._session.add(
            PlantillaMensaje(
                id=plantilla.id,
                tenant_id=self._tenant_id,
                clave=plantilla.clave,
                canal=plantilla.canal,
                idioma=plantilla.idioma,
                version=plantilla.version,
                cuerpo=plantilla.cuerpo,
                meta_template_name=plantilla.meta_template_name,
                activo=plantilla.activo,
            )
        )
        await self._session.flush()


class DbRecordatorioStore:
    def __init__(self, session: Any, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(self, rec: RecordatorioRecord) -> None:
        from app.domain.notificaciones.models import Recordatorio

        self._session.add(
            Recordatorio(
                id=rec.id,
                tenant_id=self._tenant_id,
                turno_id=rec.turno_id,
                paciente_id=rec.paciente_id,
                canal=rec.canal,
                tipo=rec.tipo,
                plantilla=rec.plantilla,
                destinatario=rec.destinatario,
                enviar_at=rec.enviar_at,
                estado=rec.estado,
                intentos=rec.intentos,
                ultimo_error=rec.ultimo_error,
                confirmado_at=rec.confirmado_at,
            )
        )
        await self._session.flush()

    async def find(
        self, *, turno_id: uuid.UUID, canal: str, tipo: str
    ) -> RecordatorioRecord | None:
        from sqlalchemy import select

        from app.domain.notificaciones.models import Recordatorio

        stmt = select(Recordatorio).where(
            Recordatorio.tenant_id == self._tenant_id,
            Recordatorio.turno_id == turno_id,
            Recordatorio.canal == canal,
            Recordatorio.tipo == tipo,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _recordatorio_from_row(row) if row is not None else None

    async def update(self, rec: RecordatorioRecord) -> None:
        from sqlalchemy import select

        from app.domain.notificaciones.models import Recordatorio

        stmt = select(Recordatorio).where(
            Recordatorio.tenant_id == self._tenant_id,
            Recordatorio.id == rec.id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return
        row.estado = rec.estado
        row.intentos = rec.intentos
        row.ultimo_error = rec.ultimo_error
        row.confirmado_at = rec.confirmado_at
        row.destinatario = rec.destinatario
        await self._session.flush()

    async def list_by_tenant(
        self, tenant_id: uuid.UUID, *, tipo: str | None = None, limit: int = 100
    ) -> list[RecordatorioRecord]:
        from sqlalchemy import select

        from app.domain.notificaciones.models import Recordatorio

        stmt = select(Recordatorio).where(
            Recordatorio.tenant_id == self._tenant_id
        )
        if tipo is not None:
            stmt = stmt.where(Recordatorio.tipo == tipo)
        stmt = stmt.order_by(Recordatorio.created_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_recordatorio_from_row(row) for row in rows]


# --- Service ---------------------------------------------------------------


class NotificacionService:
    """Orchestrates template lookup, delivery, retries, fallback and audit."""

    def __init__(
        self,
        *,
        recordatorios: RecordatorioStore,
        plantillas: PlantillaStore,
        whatsapp: WhatsAppClient,
        email: EmailClient,
        max_intentos: int = 3,
        backoff_base_s: float = 0.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.recordatorios = recordatorios
        self.plantillas = plantillas
        self.whatsapp = whatsapp
        self.email = email
        self.max_intentos = max(1, max_intentos)
        self.backoff_base_s = max(0.0, backoff_base_s)
        self._sleep = sleep

    async def _wait(self, seconds: float) -> None:
        if self._sleep is not None:
            await self._sleep(seconds)
        elif seconds > 0:
            import asyncio

            await asyncio.sleep(seconds)

    async def existe(self, *, turno_id: uuid.UUID, canal: str, tipo: str) -> bool:
        return await self.recordatorios.find(
            turno_id=turno_id, canal=canal, tipo=tipo
        ) is not None

    async def programar(
        self,
        *,
        turno_id: uuid.UUID,
        tenant_id: uuid.UUID,
        tipo: str,
        canal: str,
        destinatario: str | None,
        enviar_at: datetime.datetime,
        paciente_id: uuid.UUID | None = None,
        plantilla: str | None = None,
    ) -> RecordatorioRecord:
        existing = await self.recordatorios.find(
            turno_id=turno_id, canal=canal, tipo=tipo
        )
        if existing is not None:
            return existing
        rec = RecordatorioRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            turno_id=turno_id,
            canal=canal,
            tipo=tipo,
            plantilla=plantilla or PLANTILLA_POR_TIPO.get(tipo, tipo),
            destinatario=destinatario,
            enviar_at=enviar_at,
        )
        await self.recordatorios.add(rec)
        return rec

    async def _alerta_recepcion(self, rec: RecordatorioRecord, motivo: str) -> None:
        """Create an internal reception alert for a failed/at-risk delivery."""
        if rec.tipo == TIPO_AVISO_RECEPCION:
            return
        alert = await self.programar(
            turno_id=rec.turno_id,
            tenant_id=rec.tenant_id,
            tipo=TIPO_AVISO_RECEPCION,
            canal=CANAL_INTERNO,
            destinatario=None,
            enviar_at=datetime.datetime.now(datetime.UTC),
            paciente_id=rec.paciente_id,
            plantilla="aviso_recepcion",
        )
        if alert.estado == ESTADO_PENDIENTE and alert.ultimo_error is None:
            alert.ultimo_error = motivo
            await self.recordatorios.update(alert)

    async def enviar(self, rec: RecordatorioRecord) -> RecordatorioRecord:
        if rec.canal == CANAL_INTERNO:
            # Internal alerts are consumed by reception, not delivered.
            return rec
        plantilla = await self.plantillas.get_activa(
            tenant_id=rec.tenant_id, clave=rec.plantilla, canal=rec.canal
        )
        if plantilla is None or not plantilla.activo:
            rec.estado = ESTADO_FALLIDO
            rec.ultimo_error = (
                f"plantilla '{rec.plantilla}' inexistente o inactiva "
                f"para canal {rec.canal}"
            )
            await self.recordatorios.update(rec)
            await self._alerta_recepcion(rec, rec.ultimo_error)
            return rec

        last_error: Exception | None = None
        for intento in range(1, self.max_intentos + 1):
            try:
                await self._send(rec, plantilla, canal=rec.canal)
            except (TransientWhatsAppError, TransientEmailError) as exc:
                last_error = exc
                rec.intentos = intento
                if intento < self.max_intentos:
                    await self._wait(self.backoff_base_s * (2 ** (intento - 1)))
                    continue
                break
            except (
                PermanentWhatsAppError,
                PermanentEmailError,
                WhatsAppError,
                EmailError,
            ) as exc:
                last_error = exc
                rec.intentos = intento
                break
            else:
                rec.estado = ESTADO_ENVIADO
                rec.intentos = intento
                rec.ultimo_error = None
                await self.recordatorios.update(rec)
                return rec

        # WhatsApp failed: try email fallback before giving up.
        if rec.canal == CANAL_WHATSAPP and rec.destinatario:
            email_plantilla = await self.plantillas.get_activa(
                tenant_id=rec.tenant_id, clave=rec.plantilla, canal=CANAL_EMAIL
            )
            if email_plantilla is not None and email_plantilla.activo:
                try:
                    await self.email.send(
                        to=rec.destinatario,
                        subject=f"Turno: {rec.plantilla}",
                        body=email_plantilla.cuerpo,
                    )
                except EmailError as exc:
                    last_error = exc
                else:
                    rec.estado = ESTADO_ENVIADO
                    rec.ultimo_error = f"fallback email tras: {last_error}"
                    await self.recordatorios.update(rec)
                    return rec

        rec.estado = ESTADO_FALLIDO
        rec.ultimo_error = str(last_error) if last_error else "envío fallido"
        await self.recordatorios.update(rec)
        await self._alerta_recepcion(rec, rec.ultimo_error)
        return rec

    async def _send(
        self, rec: RecordatorioRecord, plantilla: PlantillaRecord, *, canal: str
    ) -> None:
        if not rec.destinatario:
            raise PermanentWhatsAppError("destinatario vacío")
        if canal == CANAL_WHATSAPP:
            await self.whatsapp.send_template(
                to=rec.destinatario,
                template_name=plantilla.meta_template_name or plantilla.clave,
                language=plantilla.idioma,
            )
            return
        await self.email.send(
            to=rec.destinatario,
            subject=f"Turno: {plantilla.clave}",
            body=plantilla.cuerpo,
        )


class RequiereSenaService:
    """Derives RN-NO-03 double-absence flag from the last two turnos."""

    def __init__(self, turnos: TurnoNotificacionStore) -> None:
        self.turnos = turnos

    async def requiere_sena(self, paciente_id: uuid.UUID) -> bool:
        historial = await self.turnos.list_por_paciente(paciente_id)
        if len(historial) < 2:
            return False
        ultimos = historial[:2]
        return all(t.estado == "ausente" for t in ultimos)


# --- Job building blocks (worker calls these) ------------------------------


def _destinatario(turno: TurnoNotificable) -> tuple[str, str] | None:
    if turno.contacto_whatsapp:
        return CANAL_WHATSAPP, turno.contacto_whatsapp
    if turno.contacto_email:
        return CANAL_EMAIL, turno.contacto_email
    return None


async def programar_recordatorios(
    service: NotificacionService,
    turnos: TurnoNotificacionStore,
    *,
    ahora: datetime.datetime,
    t48h: int = 48,
    t24h: int = 24,
) -> int:
    """Schedule/send the closest applicable reminder (T-24h wins over T-48h)."""
    ahora = _aware(ahora)
    enviados = 0
    for turno in await turnos.list_activos():
        delta = _aware(turno.inicio) - ahora
        if delta <= datetime.timedelta(0):
            continue
        if delta <= datetime.timedelta(hours=t24h):
            tipo = TIPO_T24H
        elif delta <= datetime.timedelta(hours=t48h):
            tipo = TIPO_T48H
        else:
            continue
        destino = _destinatario(turno)
        if destino is None:
            continue
        canal, destinatario = destino
        if await service.existe(turno_id=turno.id, canal=canal, tipo=tipo):
            continue
        rec = await service.programar(
            turno_id=turno.id,
            tenant_id=turno.tenant_id,
            tipo=tipo,
            canal=canal,
            destinatario=destinatario,
            enviar_at=ahora,
            paciente_id=turno.paciente_id,
        )
        await service.enviar(rec)
        enviados += 1
    return enviados


async def avisar_sin_confirmacion(
    service: NotificacionService,
    turnos: TurnoNotificacionStore,
    *,
    ahora: datetime.datetime,
    umbral_hs: int = 24,
    on_hueco_riesgo: Callable[[TurnoNotificable], Awaitable[None]] | None = None,
) -> int:
    """Create reception alerts for unconfirmed turnos reaching the threshold."""
    ahora = _aware(ahora)
    avisos = 0
    for turno in await turnos.list_activos():
        delta = _aware(turno.inicio) - ahora
        if delta <= datetime.timedelta(0) or delta > datetime.timedelta(
            hours=umbral_hs
        ):
            continue
        if turno.confirmado_at is not None:
            continue
        if await service.existe(
            turno_id=turno.id, canal=CANAL_INTERNO, tipo=TIPO_AVISO_RECEPCION
        ):
            continue
        await service.programar(
            turno_id=turno.id,
            tenant_id=turno.tenant_id,
            tipo=TIPO_AVISO_RECEPCION,
            canal=CANAL_INTERNO,
            destinatario=None,
            enviar_at=ahora,
            paciente_id=turno.paciente_id,
        )
        if on_hueco_riesgo is not None:
            await on_hueco_riesgo(turno)
        avisos += 1
    return avisos


async def programar_recalls_ausentes(
    service: NotificacionService,
    turnos: TurnoNotificacionStore,
    *,
    ahora: datetime.datetime,
    dias: int = 7,
) -> int:
    ahora = _aware(ahora)
    enviados = 0
    for turno in await turnos.list_por_estado("ausente"):
        if _aware(turno.fin) + datetime.timedelta(days=dias) > ahora:
            continue
        destino = _destinatario(turno)
        if destino is None:
            continue
        canal, destinatario = destino
        if await service.existe(
            turno_id=turno.id, canal=canal, tipo=TIPO_RECALL_AUSENTE
        ):
            continue
        rec = await service.programar(
            turno_id=turno.id,
            tenant_id=turno.tenant_id,
            tipo=TIPO_RECALL_AUSENTE,
            canal=canal,
            destinatario=destinatario,
            enviar_at=ahora,
            paciente_id=turno.paciente_id,
        )
        await service.enviar(rec)
        enviados += 1
    return enviados


async def programar_recalls_control(
    service: NotificacionService,
    turnos: TurnoNotificacionStore,
    *,
    ahora: datetime.datetime,
) -> int:
    ahora = _aware(ahora)
    enviados = 0
    for turno in await turnos.list_por_estado("atendido"):
        if not turno.intervalo_control_dias:
            continue
        vence = _aware(turno.fin) + datetime.timedelta(
            days=turno.intervalo_control_dias
        )
        if vence > ahora:
            continue
        destino = _destinatario(turno)
        if destino is None:
            continue
        canal, destinatario = destino
        if await service.existe(turno_id=turno.id, canal=canal, tipo=TIPO_CONTROL):
            continue
        rec = await service.programar(
            turno_id=turno.id,
            tenant_id=turno.tenant_id,
            tipo=TIPO_CONTROL,
            canal=canal,
            destinatario=destinatario,
            enviar_at=ahora,
            paciente_id=turno.paciente_id,
        )
        await service.enviar(rec)
        enviados += 1
    return enviados
