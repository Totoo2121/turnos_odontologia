"""C-11 task 2.2: Meta Cloud WhatsApp adapter classification (no network)."""

from __future__ import annotations

import asyncio
import json
import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import httpx
import pytest

from app.infrastructure.whatsapp_bsp import (
    FakeWhatsAppClient,
    MetaCloudWhatsAppClient,
    PermanentWhatsAppError,
    TransientWhatsAppError,
)


def _client(handler) -> MetaCloudWhatsAppClient:  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler)
    return MetaCloudWhatsAppClient(
        token="fictitious-token", phone_id="fictitious-phone", transport=transport
    )


def test_send_template_success_posts_expected_payload() -> None:
    """WHEN BSP answers 200 THEN the template payload is sent."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.ficticio"}]})

    client = _client(handler)
    asyncio.run(
        client.send_template(
            to="+5491100000000",
            template_name="recordatorio_turno_24h",
            language="es",
            body_params=["14/11", "09:00"],
        )
    )
    assert captured["url"] == (
        "https://graph.facebook.com/v20.0/fictitious-phone/messages"
    )
    assert captured["auth"] == "Bearer fictitious-token"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["template"]["name"] == "recordatorio_turno_24h"
    assert body["template"]["components"][0]["parameters"][0]["text"] == "14/11"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_statuses_raise_retryable_error(status: int) -> None:
    """WHEN BSP answers 429/5xx THEN a retryable error is raised."""
    client = _client(lambda _request: httpx.Response(status, json={}))
    with pytest.raises(TransientWhatsAppError):
        asyncio.run(client.send_template(to="+5491100000000", template_name="t"))


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_statuses_raise_non_retryable_error(status: int) -> None:
    """WHEN BSP answers 4xx THEN a permanent error is raised."""
    client = _client(lambda _request: httpx.Response(status, json={}))
    with pytest.raises(PermanentWhatsAppError):
        asyncio.run(client.send_template(to="+5491100000000", template_name="t"))


def test_transport_error_is_retryable() -> None:
    """WHEN the network fails THEN a retryable error is raised."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fictitious network failure", request=request)

    client = _client(handler)
    with pytest.raises(TransientWhatsAppError):
        asyncio.run(client.send_template(to="+5491100000000", template_name="t"))


def test_unconfigured_client_is_permanent_error() -> None:
    """WHEN no Business API credentials exist THEN official channel refuses."""
    client = MetaCloudWhatsAppClient(token="", phone_id="")
    with pytest.raises(PermanentWhatsAppError):
        asyncio.run(client.send_template(to="+5491100000000", template_name="t"))


def test_fake_client_replays_failures_then_records_send() -> None:
    """WHEN a fake failure is queued THEN it raises once and then records."""
    fake = FakeWhatsAppClient()
    fake.failures.append(TransientWhatsAppError("fictitious transient"))
    with pytest.raises(TransientWhatsAppError):
        asyncio.run(fake.send_template(to="+5491100000000", template_name="t"))
    asyncio.run(fake.send_template(to="+5491100000000", template_name="t"))
    assert fake.sent == [
        {
            "to": "+5491100000000",
            "template_name": "t",
            "language": "es",
            "body_params": [],
        }
    ]
