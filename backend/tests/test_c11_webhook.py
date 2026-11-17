"""C-11 tasks 4.1-4.3: WhatsApp webhook signature, idempotency and confirmation."""

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
from app.application.notificaciones import TurnoNotificable

TENANT = uuid.uuid4()


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(wh.router)
    return TestClient(app, raise_server_exceptions=False)


def _turno(*, estado: str = "reservado", token: str | None = None) -> TurnoNotificable:
    inicio = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=30)
    return TurnoNotificable(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        inicio=inicio,
        fin=inicio + datetime.timedelta(minutes=30),
        estado=estado,
        paciente_id=uuid.uuid4(),
        contacto_whatsapp="+5491100000000",
        contacto_email="demo@ficticio.invalid",
        token_portal=token,
    )


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    runtime.reset_runtime()
    wh.reset_rate_limit()
    monkeypatch.delenv("WHATSAPP_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")
    yield
    runtime.reset_runtime()
    wh.reset_rate_limit()


def _signed_headers(body: bytes, secret: str) -> dict[str, str]:
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"x-hub-signature-256": f"sha256={signature}"}


def test_invalid_signature_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN the signature is invalid THEN 401 and no state change."""
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "fictitious-webhook-secret")
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))
    body = json.dumps({"turno_id": str(turno.id), "text": "CONFIRMAR"}).encode()
    response = _app().post(
        "/webhooks/whatsapp",
        content=body,
        headers={"x-hub-signature-256": "sha256=deadbeef"},
    )
    assert response.status_code == 401
    assert asyncio.run(runtime.TURNOS.get(turno.id)).estado == "reservado"


def test_missing_signature_is_rejected_when_secret_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN the secret is configured and header absent THEN 401."""
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "fictitious-webhook-secret")
    response = _app().post("/webhooks/whatsapp", json={"turno_id": str(uuid.uuid4())})
    assert response.status_code == 401


def test_valid_signature_confirms_turno(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN signature is valid and text confirms THEN turno -> confirmado."""
    secret = "fictitious-webhook-secret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))
    body = json.dumps({"turno_id": str(turno.id), "text": "CONFIRMAR"}).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed_headers(body, secret)
    )
    assert response.status_code == 200
    updated = asyncio.run(runtime.TURNOS.get(turno.id))
    assert updated is not None
    assert updated.estado == "confirmado"
    assert updated.confirmado_at is not None


def test_button_payload_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN the confirmation arrives as an interactive button THEN it confirms."""
    secret = "fictitious-webhook-secret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))
    body = json.dumps(
        {
            "turno_id": str(turno.id),
            "message": {"button": {"payload": "CONFIRMAR"}},
        }
    ).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed_headers(body, secret)
    )
    assert response.status_code == 200
    assert asyncio.run(runtime.TURNOS.get(turno.id)).estado == "confirmado"


def test_nested_meta_payload_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN Meta's nested webhook shape arrives THEN the turno confirms."""
    secret = "fictitious-webhook-secret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "5491100000000",
                                    "text": {"body": "SÍ"},
                                    "metadata": {"turno_id": str(turno.id)},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed_headers(body, secret)
    )
    assert response.status_code == 200
    assert asyncio.run(runtime.TURNOS.get(turno.id)).estado == "confirmado"


def test_confirmation_by_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN only the portal token is present THEN the turno resolves."""
    secret = "fictitious-webhook-secret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    turno = _turno(token="token-ficticio")
    asyncio.run(runtime.TURNOS.add(turno))
    body = json.dumps({"token": "token-ficticio", "text": "CONFIRMAR"}).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed_headers(body, secret)
    )
    assert response.status_code == 200
    assert asyncio.run(runtime.TURNOS.get(turno.id)).estado == "confirmado"


def test_confirmation_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN the provider retries THEN no duplicate audit row is created."""
    secret = "fictitious-webhook-secret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))
    body = json.dumps({"turno_id": str(turno.id), "text": "CONFIRMAR"}).encode()
    headers = _signed_headers(body, secret)
    for _ in range(2):
        assert (
            _app().post("/webhooks/whatsapp", content=body, headers=headers).status_code
            == 200
        )
    rows = asyncio.run(runtime.RECORDATORIOS.list_by_tenant(TENANT))
    assert len([r for r in rows if r.tipo == "confirmacion"]) == 1


def test_cancelled_turno_is_not_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN a confirmation arrives for a cancelled turno THEN state is kept."""
    secret = "fictitious-webhook-secret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    turno = _turno(estado="cancelado")
    asyncio.run(runtime.TURNOS.add(turno))
    body = json.dumps({"turno_id": str(turno.id), "text": "CONFIRMAR"}).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed_headers(body, secret)
    )
    assert response.status_code == 200
    assert asyncio.run(runtime.TURNOS.get(turno.id)).estado == "cancelado"


def test_unknown_turno_is_acknowledged_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WHEN the turno does not exist THEN 200 with no side effects."""
    secret = "fictitious-webhook-secret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    body = json.dumps({"turno_id": str(uuid.uuid4()), "text": "CONFIRMAR"}).encode()
    response = _app().post(
        "/webhooks/whatsapp", content=body, headers=_signed_headers(body, secret)
    )
    assert response.status_code == 200


def test_dev_without_secret_accepts(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN APP_ENV=dev and no secret THEN the webhook stays usable."""
    turno = _turno()
    asyncio.run(runtime.TURNOS.add(turno))
    response = _app().post(
        "/webhooks/whatsapp", json={"turno_id": str(turno.id), "text": "CONFIRMAR"}
    )
    assert response.status_code == 200


def test_prod_without_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN APP_ENV=prod and no secret THEN the webhook rejects (401)."""
    monkeypatch.setenv("APP_ENV", "prod")
    response = _app().post("/webhooks/whatsapp", json={"text": "CONFIRMAR"})
    assert response.status_code == 401


def test_rate_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHEN the webhook exceeds the rate window THEN 429."""
    monkeypatch.setattr(wh, "_RATE_LIMIT", 1)
    client = _app()
    first = client.post("/webhooks/whatsapp", json={"text": "hola"})
    second = client.post("/webhooks/whatsapp", json={"text": "hola"})
    assert first.status_code == 200
    assert second.status_code == 429


def test_router_is_public() -> None:
    """WHEN the app is built THEN /webhooks/whatsapp bypasses JWT."""
    from app.api.deps import is_public_path

    assert is_public_path("POST", "/webhooks/whatsapp") is True
