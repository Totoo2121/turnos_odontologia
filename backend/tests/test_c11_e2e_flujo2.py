"""C-11 task 6.2: E2E del Flujo 2 con recordatorios WhatsApp (RED first).

Flujo 2 (KB 07): turno reservado -> recordatorio T-48h -> recordatorio T-24h ->
el paciente responde CONFIRMAR por WhatsApp -> webhook firmado -> turno
``confirmado`` (auditado en ``recordatorio``). Sin Postgres ni BSP reales: el
router real corre contra el runtime in-memory y un ``FakeWhatsAppClient``.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import json
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import whatsapp_webhook as wh
from app.application import notificaciones_runtime as runtime
from app.application.notificaciones import (
    CANAL_INTERNO,
    ESTADO_PENDIENTE,
    TIPO_AVISO_RECEPCION,
    TIPO_CONFIRMACION,
    TurnoNotificable,
)
from app.infrastructure.whatsapp_bsp import FakeWhatsAppClient
from app.worker.tasks import (
    avisar_turnos_sin_confirmacion,
    enviar_recordatorios_programados,
)

TENANT = uuid.uuid4()
PACIENTE = uuid.uuid4()
NOW = datetime.datetime(2026, 11, 14, 12, 0, tzinfo=datetime.UTC)
INICIO = NOW + datetime.timedelta(hours=30)
SECRET = "fictitious-e2e-webhook-secret"


@pytest.fixture(autouse=True)
def _runtime(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    runtime.reset_runtime()
    wh.reset_rate_limit()
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", SECRET)
    yield
    runtime.reset_runtime()
    wh.reset_rate_limit()


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(wh.router)
    return TestClient(app, raise_server_exceptions=False)


def _turno() -> TurnoNotificable:
    return TurnoNotificable(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        inicio=INICIO,
        fin=INICIO + datetime.timedelta(minutes=30),
        estado="reservado",
        paciente_id=PACIENTE,
        contacto_whatsapp="+5491100000000",
        contacto_email="demo@ficticio.invalid",
    )


def _signed(body: bytes) -> dict[str, str]:
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"x-hub-signature-256": f"sha256={signature}"}


def test_flujo2_recordatorios_y_confirmacion_por_whatsapp() -> None:
    """WHEN T-48h/T-24h reminders run and the patient confirms THEN audit ok."""
    fake = FakeWhatsAppClient()
    service = runtime.build_service(whatsapp=fake)
    runtime.SERVICE = service
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))

    # T-30h: the T-48h reminder goes out.
    assert (
        asyncio.run(
            enviar_recordatorios_programados(
                ahora=NOW, service=service, turnos=runtime.TURNOS, t48h=48, t24h=24
            )
        )
        == 1
    )
    assert fake.sent[0]["template_name"] == "recordatorio_turno_48h"

    # T-20h: the T-24h reminder goes out, the T-48h one is not repeated.
    t24 = NOW + datetime.timedelta(hours=10)
    assert (
        asyncio.run(
            enviar_recordatorios_programados(
                ahora=t24, service=service, turnos=runtime.TURNOS, t48h=48, t24h=24
            )
        )
        == 1
    )
    assert [s["template_name"] for s in fake.sent] == [
        "recordatorio_turno_48h",
        "recordatorio_turno_24h",
    ]

    # The patient replies CONFIRMAR; the webhook signature validates.
    body = json.dumps({"turno_id": str(turno.id), "text": "CONFIRMAR"}).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed(body)
    )
    assert response.status_code == 200, response.text

    updated = asyncio.run(runtime.TURNOS.get(turno.id))
    assert updated is not None
    assert updated.estado == "confirmado"
    assert updated.confirmado_at is not None

    audit = asyncio.run(
        runtime.RECORDATORIOS.find(
            turno_id=turno.id, canal="whatsapp", tipo=TIPO_CONFIRMACION
        )
    )
    assert audit is not None
    assert audit.estado == "confirmado"
    assert audit.confirmado_at is not None

    # A duplicate provider callback stays idempotent.
    assert (
        _app()
        .post("/webhooks/whatsapp", content=body, headers=_signed(body))
        .status_code
        == 200
    )
    rows = asyncio.run(runtime.RECORDATORIOS.list_by_tenant(TENANT))
    assert len([r for r in rows if r.tipo == TIPO_CONFIRMACION]) == 1

    # Reminders never re-send after the turno is confirmed.
    assert (
        asyncio.run(
            enviar_recordatorios_programados(
                ahora=t24, service=service, turnos=runtime.TURNOS, t48h=48, t24h=24
            )
        )
        == 0
    )
    assert len(fake.sent) == 2


def test_flujo2_confirmed_turno_is_not_alerted_to_reception() -> None:
    """WHEN the turno is confirmed THEN the reception alert job does nothing."""
    fake = FakeWhatsAppClient()
    service = runtime.build_service(whatsapp=fake)
    runtime.SERVICE = service
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))

    body = json.dumps({"turno_id": str(turno.id), "text": "CONFIRMAR"}).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed(body)
    )
    assert response.status_code == 200

    assert (
        asyncio.run(
            avisar_turnos_sin_confirmacion(
                ahora=NOW + datetime.timedelta(hours=10),
                service=service,
                turnos=runtime.TURNOS,
                umbral_hs=24,
            )
        )
        == 0
    )
    alert = asyncio.run(
        runtime.RECORDATORIOS.find(
            turno_id=turno.id, canal=CANAL_INTERNO, tipo=TIPO_AVISO_RECEPCION
        )
    )
    assert alert is None


def test_flujo2_unconfirmed_turno_alerts_reception() -> None:
    """WHEN the threshold hits without confirmation THEN an internal alert lands."""
    fake = FakeWhatsAppClient()
    service = runtime.build_service(whatsapp=fake)
    runtime.SERVICE = service
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))

    assert (
        asyncio.run(
            avisar_turnos_sin_confirmacion(
                ahora=NOW + datetime.timedelta(hours=10),
                service=service,
                turnos=runtime.TURNOS,
                umbral_hs=24,
                on_hueco_riesgo=_noop,
            )
        )
        == 1
    )
    alert = asyncio.run(
        runtime.RECORDATORIOS.find(
            turno_id=turno.id, canal=CANAL_INTERNO, tipo=TIPO_AVISO_RECEPCION
        )
    )
    assert alert is not None
    assert alert.estado == ESTADO_PENDIENTE


async def _noop(_turno: TurnoNotificable) -> None:
    return None
