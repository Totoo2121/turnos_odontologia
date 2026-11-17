"""C-11 tasks 3.1-3.5: notification service rules (RED first)."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from app.application.notificaciones import (
    CANAL_EMAIL,
    CANAL_INTERNO,
    CANAL_WHATSAPP,
    ESTADO_ENVIADO,
    ESTADO_FALLIDO,
    ESTADO_PENDIENTE,
    TIPO_AVISO_RECEPCION,
    TIPO_T24H,
    MemoryPlantillaStore,
    MemoryRecordatorioStore,
    MemoryTurnoNotificacionStore,
    NotificacionService,
    PlantillaRecord,
    RequiereSenaService,
    TurnoNotificable,
    avisar_sin_confirmacion,
    programar_recalls_ausentes,
    programar_recalls_control,
    programar_recordatorios,
)
from app.infrastructure.smtp import FakeEmailClient, TransientEmailError
from app.infrastructure.whatsapp_bsp import (
    FakeWhatsAppClient,
    TransientWhatsAppError,
)

TENANT = uuid.uuid4()
PACIENTE = uuid.uuid4()
NOW = datetime.datetime(2026, 11, 14, 12, 0, tzinfo=datetime.UTC)


def _plantilla(
    clave: str, canal: str, *, activo: bool = True, version: int = 1
) -> PlantillaRecord:
    return PlantillaRecord(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        clave=clave,
        canal=canal,
        idioma="es",
        version=version,
        cuerpo=f"Cuerpo {clave} {canal} (ficticio)",
        meta_template_name=clave if canal == CANAL_WHATSAPP else None,
        activo=activo,
    )


def _seed(store: MemoryPlantillaStore, *, activo: bool = True) -> None:
    for clave in (
        "recordatorio_t48h",
        "recordatorio_t24h",
        "recall_ausente",
        "control",
        "aviso_recepcion",
    ):
        for canal in (CANAL_WHATSAPP, CANAL_EMAIL):
            asyncio.run(store.add(_plantilla(clave, canal, activo=activo)))


def _service(
    *,
    max_intentos: int = 3,
    activo: bool = True,
) -> tuple[NotificacionService, FakeWhatsAppClient, FakeEmailClient]:
    plantillas = MemoryPlantillaStore()
    _seed(plantillas, activo=activo)
    whatsapp = FakeWhatsAppClient()
    email = FakeEmailClient()
    service = NotificacionService(
        recordatorios=MemoryRecordatorioStore(),
        plantillas=plantillas,
        whatsapp=whatsapp,
        email=email,
        max_intentos=max_intentos,
        backoff_base_s=0.0,
        sleep=lambda _seconds: asyncio.sleep(0),
    )
    return service, whatsapp, email


def _turno(
    *,
    inicio: datetime.datetime | None = None,
    estado: str = "confirmado",
    whatsapp: str | None = "+5491100000000",
    email: str | None = "demo@ficticio.invalid",
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
        contacto_whatsapp=whatsapp,
        contacto_email=email,
        confirmado_at=confirmado_at,
        intervalo_control_dias=intervalo_control_dias,
    )


def test_programar_is_idempotent_per_turno_channel_type() -> None:
    """WHEN programmed twice THEN the same record is reused (unique key)."""
    service, _, _ = _service()
    turno = _turno()
    first = asyncio.run(
        service.programar(
            turno_id=turno.id,
            tenant_id=TENANT,
            tipo=TIPO_T24H,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=NOW,
        )
    )
    second = asyncio.run(
        service.programar(
            turno_id=turno.id,
            tenant_id=TENANT,
            tipo=TIPO_T24H,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=NOW,
        )
    )
    assert first.id == second.id
    rows = asyncio.run(service.recordatorios.list_by_tenant(TENANT))
    assert len(rows) == 1


def test_envio_con_plantilla_activa_marks_sent() -> None:
    """WHEN a valid template exists THEN WhatsApp sends and state is enviado."""
    service, whatsapp, _ = _service()
    turno = _turno()
    rec = asyncio.run(
        service.programar(
            turno_id=turno.id,
            tenant_id=TENANT,
            tipo=TIPO_T24H,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=NOW,
        )
    )
    updated = asyncio.run(service.enviar(rec))
    assert updated.estado == ESTADO_ENVIADO
    assert updated.intentos == 1
    assert len(whatsapp.sent) == 1
    assert whatsapp.sent[0]["template_name"] == "recordatorio_t24h"


def test_missing_template_fails_controlled_and_alerts_reception() -> None:
    """WHEN the template is missing/inactive THEN fail + internal alert."""
    service, whatsapp, _ = _service(activo=False)
    turno = _turno()
    rec = asyncio.run(
        service.programar(
            turno_id=turno.id,
            tenant_id=TENANT,
            tipo=TIPO_T24H,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=NOW,
        )
    )
    updated = asyncio.run(service.enviar(rec))
    assert updated.estado == ESTADO_FALLIDO
    assert whatsapp.sent == []
    alert = asyncio.run(
        service.recordatorios.find(
            turno_id=turno.id, canal=CANAL_INTERNO, tipo=TIPO_AVISO_RECEPCION
        )
    )
    assert alert is not None
    assert alert.estado == ESTADO_PENDIENTE


def test_transient_failure_retries_with_backoff_then_succeeds() -> None:
    """WHEN two transient failures happen THEN the third attempt succeeds."""
    service, whatsapp, _ = _service(max_intentos=3)
    whatsapp.failures.extend(
        [TransientWhatsAppError("t1"), TransientWhatsAppError("t2")]
    )
    turno = _turno()
    rec = asyncio.run(
        service.programar(
            turno_id=turno.id,
            tenant_id=TENANT,
            tipo=TIPO_T24H,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=NOW,
        )
    )
    updated = asyncio.run(service.enviar(rec))
    assert updated.estado == ESTADO_ENVIADO
    assert updated.intentos == 3
    assert len(whatsapp.sent) == 1


def test_exhausted_retries_fall_back_to_email() -> None:
    """WHEN WhatsApp exhausts retries THEN email fallback delivers."""
    service, whatsapp, email = _service(max_intentos=2)
    whatsapp.failures.extend(
        [TransientWhatsAppError("t1"), TransientWhatsAppError("t2")]
    )
    turno = _turno()
    rec = asyncio.run(
        service.programar(
            turno_id=turno.id,
            tenant_id=TENANT,
            tipo=TIPO_T24H,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=NOW,
        )
    )
    updated = asyncio.run(service.enviar(rec))
    assert updated.estado == ESTADO_ENVIADO
    assert updated.ultimo_error is not None
    assert "fallback" in updated.ultimo_error.lower()
    assert len(email.sent) == 1


def test_persistent_failure_marks_failed_and_alerts() -> None:
    """WHEN both channels fail THEN state fallido + reception alert."""
    service, whatsapp, email = _service(max_intentos=1)
    whatsapp.failures.append(TransientWhatsAppError("t1"))
    email.failures.append(TransientEmailError("e1"))
    turno = _turno()
    rec = asyncio.run(
        service.programar(
            turno_id=turno.id,
            tenant_id=TENANT,
            tipo=TIPO_T24H,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=NOW,
        )
    )
    updated = asyncio.run(service.enviar(rec))
    assert updated.estado == ESTADO_FALLIDO
    alert = asyncio.run(
        service.recordatorios.find(
            turno_id=turno.id, canal=CANAL_INTERNO, tipo=TIPO_AVISO_RECEPCION
        )
    )
    assert alert is not None


def test_reminder_windows_t48_then_t24_without_duplicates() -> None:
    """WHEN the turno crosses 48h then 24h THEN one reminder per window."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    turno = _turno(inicio=NOW + datetime.timedelta(hours=30))
    asyncio.run(turnos.add(turno))

    sent_48 = asyncio.run(
        programar_recordatorios(service, turnos, ahora=NOW, t48h=48, t24h=24)
    )
    assert sent_48 == 1
    assert whatsapp.sent[0]["template_name"] == "recordatorio_t48h"

    # Same instant re-run: no duplicate.
    assert (
        asyncio.run(
            programar_recordatorios(service, turnos, ahora=NOW, t48h=48, t24h=24)
        )
        == 0
    )

    later = NOW + datetime.timedelta(hours=10)
    sent_24 = asyncio.run(
        programar_recordatorios(service, turnos, ahora=later, t48h=48, t24h=24)
    )
    assert sent_24 == 1
    assert [s["template_name"] for s in whatsapp.sent] == [
        "recordatorio_t48h",
        "recordatorio_t24h",
    ]


def test_reminders_skip_inactive_states_and_without_contact() -> None:
    """WHEN turno cancels or lacks contact THEN no reminder is scheduled."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    asyncio.run(
        turnos.add(
            _turno(inicio=NOW + datetime.timedelta(hours=10), estado="cancelado")
        )
    )
    asyncio.run(
        turnos.add(
            _turno(
                inicio=NOW + datetime.timedelta(hours=10),
                whatsapp=None,
                email=None,
            )
        )
    )
    assert (
        asyncio.run(
            programar_recordatorios(service, turnos, ahora=NOW, t48h=48, t24h=24)
        )
        == 0
    )
    assert whatsapp.sent == []


def test_unconfirmed_at_threshold_alerts_and_offers_waitlist() -> None:
    """WHEN unconfirmed at threshold THEN internal alert + waitlist callback."""
    service, _, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    turno = _turno(inicio=NOW + datetime.timedelta(hours=5), confirmado_at=None)
    asyncio.run(turnos.add(turno))
    offered: list[uuid.UUID] = []

    async def on_offer(t: TurnoNotificable) -> None:
        offered.append(t.id)

    avisos = asyncio.run(
        avisar_sin_confirmacion(
            service, turnos, ahora=NOW, umbral_hs=24, on_hueco_riesgo=on_offer
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
    # Re-run is idempotent.
    assert (
        asyncio.run(
            avisar_sin_confirmacion(
                service, turnos, ahora=NOW, umbral_hs=24, on_hueco_riesgo=on_offer
            )
        )
        == 0
    )


def test_confirmed_turno_does_not_trigger_threshold_alert() -> None:
    """WHEN confirmado_at is set THEN no reception alert is created."""
    service, _, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    asyncio.run(
        turnos.add(
            _turno(
                inicio=NOW + datetime.timedelta(hours=5),
                confirmado_at=NOW - datetime.timedelta(hours=1),
            )
        )
    )
    assert (
        asyncio.run(
            avisar_sin_confirmacion(service, turnos, ahora=NOW, umbral_hs=24)
        )
        == 0
    )


def test_recall_ausente_after_seven_days_without_duplicates() -> None:
    """WHEN an absence is 7+ days old THEN one recall is sent."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    viejo = _turno(
        inicio=NOW - datetime.timedelta(days=9),
        estado="ausente",
    )
    asyncio.run(turnos.add(viejo))
    assert (
        asyncio.run(programar_recalls_ausentes(service, turnos, ahora=NOW, dias=7))
        == 1
    )
    assert whatsapp.sent[0]["template_name"] == "recall_ausente"
    assert (
        asyncio.run(programar_recalls_ausentes(service, turnos, ahora=NOW, dias=7))
        == 0
    )


def test_recall_control_uses_prestacion_interval() -> None:
    """WHEN the control interval elapsed THEN a control recall is sent."""
    service, whatsapp, _ = _service()
    turnos = MemoryTurnoNotificacionStore()
    viejo = _turno(
        inicio=NOW - datetime.timedelta(days=200),
        estado="atendido",
        intervalo_control_dias=180,
    )
    asyncio.run(turnos.add(viejo))
    assert asyncio.run(programar_recalls_control(service, turnos, ahora=NOW)) == 1
    assert whatsapp.sent[0]["template_name"] == "control"
    assert asyncio.run(programar_recalls_control(service, turnos, ahora=NOW)) == 0


def test_requiere_sena_derives_double_absence() -> None:
    """WHEN the last two turnos are ausente THEN requires deposit."""
    turnos = MemoryTurnoNotificacionStore()
    base = NOW - datetime.timedelta(days=20)
    asyncio.run(
        turnos.add(_turno(inicio=base, estado="ausente"))
    )
    asyncio.run(
        turnos.add(_turno(inicio=base + datetime.timedelta(days=7), estado="ausente"))
    )
    assert asyncio.run(RequiereSenaService(turnos).requiere_sena(PACIENTE)) is True


def test_requiere_sena_resets_when_attended() -> None:
    """WHEN one of the last two turnos was attended THEN no deposit flag."""
    turnos = MemoryTurnoNotificacionStore()
    base = NOW - datetime.timedelta(days=20)
    asyncio.run(turnos.add(_turno(inicio=base, estado="ausente")))
    asyncio.run(
        turnos.add(_turno(inicio=base + datetime.timedelta(days=7), estado="atendido"))
    )
    assert asyncio.run(RequiereSenaService(turnos).requiere_sena(PACIENTE)) is False
