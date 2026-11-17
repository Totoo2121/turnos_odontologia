"""C-11 WhatsApp Business API adapter (official BSP only, RN-NO-05).

The application depends on the ``WhatsAppClient`` protocol; the default
``MetaCloudWhatsAppClient`` talks to Meta's Cloud API over HTTPS. Keeping the
adapter behind a port lets a tenant migrate to a different official BSP
without touching notification rules, and lets tests run without network.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import httpx

GRAPH_BASE_URL = "https://graph.facebook.com/v20.0"


class WhatsAppError(Exception):
    """Base WhatsApp delivery error."""


class TransientWhatsAppError(WhatsAppError):
    """Retryable failure (timeout, 429, 5xx)."""


class PermanentWhatsAppError(WhatsAppError):
    """Non-retryable failure (bad request, auth, missing configuration)."""


class WhatsAppClient(Protocol):
    """Port: send an approved template message to one recipient."""

    async def send_template(
        self,
        *,
        to: str,
        template_name: str,
        language: str = "es",
        body_params: Sequence[str] = (),
    ) -> None: ...


class MetaCloudWhatsAppClient:
    """Official WhatsApp Business Cloud API client (tenant phone id + token)."""

    def __init__(
        self,
        *,
        token: str,
        phone_id: str,
        base_url: str = GRAPH_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._token = token
        self._phone_id = phone_id
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    async def send_template(
        self,
        *,
        to: str,
        template_name: str,
        language: str = "es",
        body_params: Sequence[str] = (),
    ) -> None:
        if not self._token or not self._phone_id:
            raise PermanentWhatsAppError(
                "WhatsApp Business API is not configured for this tenant"
            )
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if body_params:
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": param} for param in body_params
                    ],
                }
            ]
        url = f"{self._base_url}/{self._phone_id}/messages"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientWhatsAppError(str(exc)) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientWhatsAppError(
                f"transient BSP error {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentWhatsAppError(
                f"permanent BSP error {response.status_code}"
            )


class FakeWhatsAppClient:
    """Test double: records sends and replays queued failures."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.failures: list[Exception] = []

    async def send_template(
        self,
        *,
        to: str,
        template_name: str,
        language: str = "es",
        body_params: Sequence[str] = (),
    ) -> None:
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append(
            {
                "to": to,
                "template_name": template_name,
                "language": language,
                "body_params": list(body_params),
            }
        )
