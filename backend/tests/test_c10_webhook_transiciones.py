"""C-10 task 3.2: IPN acreditación / anulación + vencimiento — Strict TDD."""

from __future__ import annotations

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import cobros_webhook as wh
from app.application.cobros import (
    ESTADO_TURNO_CANCELADO,
    ESTADO_TURNO_CONFIRMADO,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(wh.router)
    return TestClient(app, raise_server_exceptions=False)


def _reset() -> None:
    wh.SERVICE.turnos.clear()
    wh.SERVICE._liberados.clear()


def test_ipn_aprobado_acredita_y_confirma_turno() -> None:
    """WHEN llega IPN con pago aprobado THEN turno pasa a `confirmado`."""
    _reset()
    turno_id = uuid.uuid4()
    payload = {
        "action": "payment.updated",
        "data": {
            "id": f"pay-approved-{uuid.uuid4()}",
            "status": "approved",
            "transaction_amount": 5000.0,
            "metadata": {"turno_id": str(turno_id)},
        },
    }
    r = _client().post("/webhooks/mercadopago", json=payload)
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert wh.SERVICE.estado_turno(turno_id) == ESTADO_TURNO_CONFIRMADO


def test_ipn_vencido_anula_turno_y_libera_hueco() -> None:
    """WHEN llega IPN con pago vencido THEN turno `cancelado` + hueco liberado."""
    _reset()
    turno_id = uuid.uuid4()
    payload = {
        "data": {
            "id": f"pay-expired-{uuid.uuid4()}",
            "status": "expired",
            "metadata": {"turno_id": str(turno_id)},
        },
    }
    r = _client().post("/webhooks/mercadopago", json=payload)
    assert r.status_code == 200
    assert wh.SERVICE.estado_turno(turno_id) == ESTADO_TURNO_CANCELADO
    assert wh.SERVICE.hueco_liberado(turno_id) is True


def test_ipn_rechazado_anula_turno_y_libera_hueco() -> None:
    """WHEN llega IPN con pago rechazado THEN turno `cancelado` + hueco liberado."""
    _reset()
    turno_id = uuid.uuid4()
    payload = {
        "data": {
            "id": f"pay-rejected-{uuid.uuid4()}",
            "status": "rejected",
            "metadata": {"turno_id": str(turno_id)},
        },
    }
    r = _client().post("/webhooks/mercadopago", json=payload)
    assert r.status_code == 200
    assert wh.SERVICE.estado_turno(turno_id) == ESTADO_TURNO_CANCELADO
    assert wh.SERVICE.hueco_liberado(turno_id) is True


def test_ipn_duplicado_es_idempotente() -> None:
    """WHEN llega un IPN duplicado THEN responde OK sin re-transicionar."""
    _reset()
    turno_id = uuid.uuid4()
    mp_payment_id = f"pay-dup-{uuid.uuid4()}"
    payload = {
        "data": {"id": mp_payment_id, "status": "approved", "metadata": {"turno_id": str(turno_id)}},
    }
    r1 = _client().post("/webhooks/mercadopago", json=payload)
    r2 = _client().post("/webhooks/mercadopago", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("idempotent") is True
    assert wh.SERVICE.estado_turno(turno_id) == ESTADO_TURNO_CONFIRMADO
