"""C-10 task 6.1: E2E del Flujo 1 con seña — Strict TDD (RED first).

Flujo 1 (KB 07): reserva online con seña → orden Mercado Pago → checkout →
IPN aprobado → turno `confirmado`. La prueba corre sobre los routers reales
con ``TestClient`` y reemplaza los puertos externos por stores y clientes
in-memory: sin Postgres ni Mercado Pago reales.

Cadena cubierta:
1. ``POST /reservar/{slug}/turnos`` con seña crea la orden MP y deja el turno
   en ``reservado-pendiente-pago`` (spec C-10: reserva con seña genera orden).
2. ``GET /checkout/{turno_id}`` devuelve la URL de Checkout Pro de la orden.
3. ``POST /api/webhooks/mercadopago`` aprobado acredita el pago y confirma el
   turno; un IPN duplicado es idempotente.
4. ``GET /api/turnos/agenda`` muestra el cobro ``acreditado`` y el reporte de
   señas pendientes queda vacío.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import agenda_cobros as agenda_api
from app.api import cobros_webhook as wh
from app.api import turnero_publico as tp
from app.application.agenda_cobros import (
    AGENDA_TZ,
    AgendaCobroService,
    AgendaTurno,
    MemoryAgendaCobroStore,
)
from app.application.auth_service import Principal
from app.application.cobros import (
    ESTADO_COBRO_ACREDITADO,
    ESTADO_COBRO_PENDIENTE,
    ESTADO_TURNO_CONFIRMADO,
    ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO,
    CobroService,
    MemoryCobroStore,
)
from app.shared.exceptions import register_exception_handlers

SLUG = "demo-e2e-ficticia"
PROF = uuid.uuid4()
SILLON = uuid.uuid4()
TENANT = uuid.uuid4()
INICIO = datetime(2026, 11, 20, 10, 0, tzinfo=AGENDA_TZ)
MONTO_SENA = 5000.0
MP_ORDER_ID = "mp-order-e2e-1"
CHECKOUT_URL = "https://mp.example/checkout/e2e-1"


class FakeMPClient:
    """Mercado Pago SDK fake: devuelve una orden Checkout Pro determinista."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        return {"id": MP_ORDER_ID, "checkout_url": CHECKOUT_URL}


def _reserva(*, con_sena: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "nombre": "Paciente Ficticio E2E",
        "whatsapp": "+5491100000000",
        "profesional_id": str(PROF),
        "inicio": INICIO.isoformat(),
    }
    if con_sena:
        payload["monto_sena"] = MONTO_SENA
    return payload


def _ipn(
    *,
    turno_id: uuid.UUID,
    tenant_id: uuid.UUID,
    mp_payment_id: str,
    status: str = "approved",
) -> dict[str, Any]:
    return {
        "action": "payment.updated",
        "data": {
            "id": mp_payment_id,
            "status": status,
            "transaction_amount": MONTO_SENA,
            "metadata": {
                "turno_id": str(turno_id),
                "tenant_id": str(tenant_id),
                "mp_order_id": MP_ORDER_ID,
            },
        },
    }


@pytest.fixture()
def e2e(monkeypatch: pytest.MonkeyPatch):
    """App real + puertos in-memory inyectados por overrides/monkeypatch."""
    monkeypatch.setattr(tp, "_RESERVED", set())
    monkeypatch.setattr(tp, "_PORTAL", {})
    monkeypatch.setattr(tp, "_rate_hits", {})
    monkeypatch.setattr(wh, "_PROCESSED", set())

    mp = FakeMPClient()
    svc = CobroService(store=MemoryCobroStore(), client=mp)
    agenda_store = MemoryAgendaCobroStore()
    monkeypatch.setattr(tp, "COBROS", svc)
    monkeypatch.setattr(wh, "SERVICE", svc)
    monkeypatch.setattr(wh, "STORE", svc.store)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(tp.router)
    app.include_router(wh.router, prefix="/api")
    app.include_router(agenda_api.router, prefix="/api")
    principal = Principal(
        sub="staff-e2e-ficticio",
        tenant_id=TENANT,
        roles=("recepcion",),
        email="recepcion@demo-ficticia.invalid",
    )
    app.dependency_overrides[agenda_api.get_current_principal] = lambda: principal
    app.dependency_overrides[agenda_api.get_agenda_cobro_service] = lambda: (
        AgendaCobroService(agenda_store)
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, svc=svc, mp=mp, agenda=agenda_store)


def test_e2e_flujo1_sena_reserva_pago_webhook_confirmado(e2e) -> None:
    """WHEN el paciente reserva con seña y el IPN aprueba THEN turno confirmado."""
    client, svc, agenda = e2e.client, e2e.svc, e2e.agenda

    # 1. Reserva online con seña → orden MP + turno reservado-pendiente-pago.
    reserva = client.post(f"/reservar/{SLUG}/turnos", json=_reserva())
    assert reserva.status_code in (200, 201)
    body = reserva.json()
    assert body["estado"] == ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO
    assert body["checkout_url"] == CHECKOUT_URL
    turno_id = uuid.UUID(body["turno_id"])
    token = body["token"]

    assert svc.estado_turno(turno_id) == ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO
    pago = asyncio.run(svc.store.find_by_turno(turno_id))
    assert pago is not None
    assert pago.estado == ESTADO_COBRO_PENDIENTE
    assert pago.monto == MONTO_SENA
    assert pago.mp_order_id == MP_ORDER_ID
    assert len(e2e.mp.calls) == 1
    assert e2e.mp.calls[0]["monto"] == MONTO_SENA

    # 2. Checkout redirect público apunta a la orden creada.
    checkout = client.get(f"/checkout/{turno_id}")
    assert checkout.status_code == 200
    assert checkout.json()["url"] == CHECKOUT_URL
    assert checkout.json()["estado"] == ESTADO_COBRO_PENDIENTE
    portal_checkout = client.get(f"/p/{token}/checkout")
    assert portal_checkout.status_code == 200
    assert portal_checkout.json()["url"] == CHECKOUT_URL

    # 3. IPN aprobado → pago acreditado + turno confirmado (RN-TU-04).
    aprobado = client.post(
        "/api/webhooks/mercadopago",
        json=_ipn(
            turno_id=turno_id,
            tenant_id=pago.tenant_id,
            mp_payment_id="pay-e2e-approved-1",
        ),
    )
    assert aprobado.status_code == 200
    assert aprobado.json()["estado"] == ESTADO_COBRO_ACREDITADO
    assert aprobado.json()["turno"]["estado"] == ESTADO_TURNO_CONFIRMADO
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_CONFIRMADO
    assert svc.hueco_liberado(turno_id) is False

    confirmado = asyncio.run(svc.store.find_by_turno(turno_id))
    assert confirmado is not None
    assert confirmado.estado == ESTADO_COBRO_ACREDITADO
    assert confirmado.tenant_id == pago.tenant_id
    assert confirmado.mp_payment_id == "pay-e2e-approved-1"
    assert confirmado.acreditado_at is not None
    assert asyncio.run(svc.pendientes()) == []

    # 4. La agenda del mostrador ya muestra el cobro acreditado.
    agenda.add_turno(
        AgendaTurno(
            id=turno_id,
            inicio=INICIO,
            fin=INICIO + timedelta(minutes=30),
            estado=svc.estado_turno(turno_id),
            profesional_id=PROF,
            sillon_id=SILLON,
        )
    )
    agenda.add_pago(confirmado)
    dia = client.get(f"/api/turnos/agenda?fecha={INICIO.date().isoformat()}")
    assert dia.status_code == 200
    items = dia.json()
    assert len(items) == 1
    assert items[0]["id"] == str(turno_id)
    assert items[0]["estado"] == ESTADO_TURNO_CONFIRMADO
    assert items[0]["cobro"] == ESTADO_COBRO_ACREDITADO
    assert items[0]["cobro_monto"] == MONTO_SENA
    assert items[0]["cobro_mp_order_id"] == MP_ORDER_ID

    reporte = client.get("/api/reportes/senias-pendientes")
    assert reporte.status_code == 200
    assert reporte.json() == []

    # 5. IPN duplicado: OK idempotente, sin re-transicionar ni duplicar el pago.
    duplicado = client.post(
        "/api/webhooks/mercadopago",
        json=_ipn(
            turno_id=turno_id,
            tenant_id=pago.tenant_id,
            mp_payment_id="pay-e2e-approved-1",
        ),
    )
    assert duplicado.status_code == 200
    assert duplicado.json()["idempotent"] is True
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_CONFIRMADO
    assert len(svc.store._rows) == 1


def test_e2e_reserva_sin_sena_no_crea_orden_mp(e2e) -> None:
    """WHEN la prestación no exige seña THEN no hay orden MP ni checkout."""
    client, svc = e2e.client, e2e.svc

    reserva = client.post(f"/reservar/{SLUG}/turnos", json=_reserva(con_sena=False))
    assert reserva.status_code in (200, 201)
    body = reserva.json()
    assert body["estado"] == "reservado"
    assert body.get("checkout_url") is None

    turno_id = uuid.UUID(body["turno_id"])
    assert svc.estado_turno(turno_id) is None
    assert asyncio.run(svc.store.find_by_turno(turno_id)) is None
    assert e2e.mp.calls == []
