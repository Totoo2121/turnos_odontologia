"""C-11 tasks 4.1/4.2: worker jobs for reminders, alerts and recalls (RED first)."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.notificaciones import (
    CANAL_EMAIL,
    CANAL_INTERNO,
    CANAL_WHATSAPP,
    ESTADO_PENDIENTE,
    TIPO_AVISO_RECEPCION,
    MemoryPlantillaStore,
    MemoryRecordatorioStore,
    MemoryTurnoNotificacionStore,
    NotificacionService,
    PlantillaRecord,
    TurnoNotificable,
)
from app.infrastructure.smtp import FakeEmailClient
from app.infrastructure.whatsapp_bsp import FakeWhatsAppClient
from app.worker.tasks import (
    avisar_turnos_sin_confirmacion,
    enviar_recalls_ausentes,
    enviar_recalls_control,
    enviar_recordatorios_programados,
)

TENANT = uuid.uuid4()
PACIENTE = uuid.uuid4()
NOW = datetime.datetime(2026, 11, 14, 12, 0, tzinfo=datetime.UTC)


def _plantilla(clave: str, canal: str) -> PlantillaRecord:
    return PlantillaRecord(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        clave=clave,
        canal=canal,
        idioma="es",
        version=1,
        cuerpo=f"Cuerpo {clave} {canal} (ficticio)",
        meta_template_name=clave if canal == CANAL_WHATSAPP else None,
        activo=True,
    )


def _seed(store: MemoryPlantillaStore) -> None:
    for clave in (
        "recordatorio_t48h",
        "recordatorio_t24h",
        "recall_ausente",
        "control",
        "aviso_recepcion",
    ):
        for canal in (CANAL_WHATSAPP, CANAL_EMAIL):
            asyncio.run(store.add(_plantilla(clave, canal)))


def _service() -> tuple[NotificacionService, FakeWhatsAppClient, FakeEmailClient]:
    plantillas = MemoryPlantillaStore()
    _seed(plantillas)
    whatsapp = FakeWhatsAppClient()
    email = FakeEmailClient()
    service = NotificacionService(
        recordatorios=MemoryRecordatorioStore(),
        plantillas=plantillas,
        whatsapp=whatsapp,
        email=email,
        max_intentos=1,
        backoff_base_s=0.0,
        sleep=lambda _seconds: asyncio.sleep(0),
    )
    return service, whatsapp, email


def _turno(
    *,
    inicio: datetime.datetime | None = None,
    estado: str = "confirmado",
    confirmado_at: datetime.datetime | None = None,
    intervalo_control_dias: int | None = None,
) -> TurnoNotificable:
    inicio = inicio or NOW + datetime.timedelta(hours=10)
    return TurnoNotificable(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        inicio=inicio,
        fin=inicio + datetime.timedelta(minutes=30),
        estado=estado,
        paciente_id=PACIENTE,
        contacto_whatsapp="+5491100000000",
        contacto_email="demo@ficticio.invalid",
        confirmado_at=confirmado_at,
        intervalo_control_dias=intervalo_control_dias,
    )


def test_worker_sends_t48_and_t24_without_duplicates() -> None:
    """WHEN the turno enters each window THEN one reminder per window is sent."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    turno = _turno(inicio=NOW + datetime.timedelta(hours=30))
    asyncio.run(turnos.add(turno))

    first = asyncio.run(
        enviar_recordatorios_programados(
            ahora=NOW, service=service, turnos=turnos, t48h=48, t24h=24
        )
    )
    assert first == 1
    assert whatsapp.sent[0]["template_name"] == "recordatorio_t48h"

    # Same instant: nothing is re-sent (idempotent by turno/canal/tipo).
    assert (
        asyncio.run(
            enviar_recordatorios_programados(
                ahora=NOW, service=service, turnos=turnos, t48h=48, t24h=24
            )
        )
        == 0
    )

    later = NOW + datetime.timedelta(hours=10)
    second = asyncio.run(
        enviar_recordatorios_programados(
            ahora=later, service=service, turnos=turnos, t48h=48, t24h=24
        )
    )
    assert second == 1
    assert [s["template_name"] for s in whatsapp.sent] == [
        "recordatorio_t48h",
        "recordatorio_t24h",
    ]


def test_worker_excludes_cancelled_and_unreachable_turnos() -> None:
    """WHEN a turno is cancelled or has no contact THEN no reminder is sent."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    asyncio.run(
        turnos.add(
            _turno(inicio=NOW + datetime.timedelta(hours=10), estado="cancelado")
        )
    )
    sin_contacto = _turno(inicio=NOW + datetime.timedelta(hours=10))
    asyncio.run(
        turnos.add(
            TurnoNotificable(
                id=sin_contacto.id,
                tenant_id=sin_contacto.tenant_id,
                inicio=sin_contacto.inicio,
                fin=sin_contacto.fin,
                estado=sin_contacto.estado,
                paciente_id=sin_contacto.paciente_id,
            )
        )
    )
    assert (
        asyncio.run(
            enviar_recordatorios_programados(
                ahora=NOW, service=service, turnos=turnos, t48h=48, t24h=24
            )
        )
        == 0
    )
    assert whatsapp.sent == []


def test_worker_alerts_reception_and_offers_waitlist_at_threshold() -> None:
    """WHEN the confirmation threshold hits THEN alert + waitlist callback run."""
    service, _, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    turno = _turno(
        inicio=NOW + datetime.timedelta(hours=5), confirmado_at=None
    )
    asyncio.run(turnos.add(turno))
    offered: list[uuid.UUID] = []

    async def on_offer(t: TurnoNotificable) -> None:
        offered.append(t.id)

    avisos = asyncio.run(
        avisar_turnos_sin_confirmacion(
            ahora=NOW,
            service=service,
            turnos=turnos,
            umbral_hs=24,
            on_hueco_riesgo=on_offer,
        )
    )
    assert avisos == 1
    assert offered == [turno.id]
    alert = asyncio.run(
        service.recordatorios.find(
            turno_id=turno.id, canal=CANAL_INTERNO, tipo=TIPO_AVISO_RECEPCION
        )
    )
    assert alert is not None
    assert alert.estado == ESTADO_PENDIENTE

    # Idempotent on re-run.
    assert (
        asyncio.run(
            avisar_turnos_sin_confirmacion(
                ahora=NOW,
                service=service,
                turnos=turnos,
                umbral_hs=24,
                on_hueco_riesgo=on_offer,
            )
        )
        == 0
    )


def test_worker_does_not_alert_confirmed_turnos() -> None:
    """WHEN the turno is already confirmed THEN no reception alert exists."""
    service, _, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    asyncio.run(
        turnos.add(
            _turno(
                inicio=NOW + datetime.timedelta(hours=5),
                confirmado_at=NOW - datetime.timedelta(hours=2),
            )
        )
    )
    assert (
        asyncio.run(
            avisar_turnos_sin_confirmacion(
                ahora=NOW, service=service, turnos=turnos, umbral_hs=24
            )
        )
        == 0
    )


def test_worker_sends_recall_after_seven_absent_days_once() -> None:
    """WHEN an absence is 7+ days old THEN exactly one recall is sent."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    asyncio.run(
        turnos.add(
            _turno(
                inicio=NOW - datetime.timedelta(days=9), estado="ausente"
            )
        )
    )
    assert (
        asyncio.run(
            enviar_recalls_ausentes(
                ahora=NOW, service=service, turnos=turnos, dias=7
            )
        )
        == 1
    )
    assert whatsapp.sent[0]["template_name"] == "recall_ausente"
    assert (
        asyncio.run(
            enviar_recalls_ausentes(
                ahora=NOW, service=service, turnos=turnos, dias=7
            )
        )
        == 0
    )


def test_worker_sends_control_recall_by_prestacion_interval() -> None:
    """WHEN the control interval elapsed THEN one control recall is sent."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    asyncio.run(
        turnos.add(
            _turno(
                inicio=NOW - datetime.timedelta(days=200),
                estado="atendido",
                intervalo_control_dias=180,
            )
        )
    )
    assert (
        asyncio.run(
            enviar_recalls_control(ahora=NOW, service=service, turnos=turnos)
        )
        == 1
    )
    assert whatsapp.sent[0]["template_name"] == "control"
    assert (
        asyncio.run(
            enviar_recalls_control(ahora=NOW, service=service, turnos=turnos)
        )
        == 0
    )


@pytest.mark.parametrize(
    ("entry", "task"),
    [
        ("c11-recordatorios", "app.worker.tasks.enviar_recordatorios_programados"),
        (
            "c11-avisos-sin-confirmacion",
            "app.worker.tasks.avisar_turnos_sin_confirmacion",
        ),
        ("c11-recall-ausentes", "app.worker.tasks.enviar_recalls_ausentes"),
        ("c11-recall-control", "app.worker.tasks.enviar_recalls_control"),
    ],
)
def test_worker_c11_jobs_are_scheduled_in_beat(entry: str, task: str) -> None:
    """WHEN Celery beat is inspected THEN every C-11 job is scheduled."""
    from app.worker.celery_app import celery_app

    configured = celery_app.conf.beat_schedule.get(entry)
    assert configured is not None
    assert configured["task"] == task
    assert configured["schedule"] > 0


def test_worker_c11_tasks_are_registered_and_sync() -> None:
    """WHEN the Celery app loads THEN the C-11 tasks are sync and executable."""
    import app.worker.tasks  # noqa: F401  (registers tasks on import)
    from app.worker.celery_app import celery_app

    for name in (
        "app.worker.tasks.enviar_recordatorios_programados",
        "app.worker.tasks.avisar_turnos_sin_confirmacion",
        "app.worker.tasks.enviar_recalls_ausentes",
        "app.worker.tasks.enviar_recalls_control",
    ):
        task = celery_app.tasks[name]
        resultado = task.run()
        assert isinstance(resultado, int)
