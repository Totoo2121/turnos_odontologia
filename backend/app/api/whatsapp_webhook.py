"""C-11 public WhatsApp webhook: signature, rate-limit and confirmation.

Provider callbacks are public paths, so they must validate the provider
signature and a rate-limit before touching state (hard project rule).
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import hmac
import uuid
from collections import deque
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.application import notificaciones_runtime as runtime
from app.application.notificaciones import (
    CANAL_WHATSAPP,
    TIPO_CONFIRMACION,
)
from app.shared.settings import get_settings

router = APIRouter(tags=["notificaciones-webhook"])

_RATE_LIMIT = 60
_RATE_WINDOW_SECONDS = 60
_rate_hits: dict[str, deque[datetime.datetime]] = {}

CONFIRM_KEYWORDS = frozenset({"confirmar", "confirmo", "si", "sí", "1"})
ESTADOS_NO_CONFIRMABLES = frozenset(
    {"cancelado", "ausente", "atendido", "reservado-pendiente-pago"}
)


def reset_rate_limit() -> None:
    _rate_hits.clear()


def _check_rate(request: Request) -> bool:
    ip = request.client.host if request.client else "unknown"
    now = datetime.datetime.now(datetime.UTC)
    window = _rate_hits.setdefault(ip, deque())
    while window and (now - window[0]).total_seconds() >= _RATE_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        return False
    window.append(now)
    return True


def _extract_signature(request: Request) -> str | None:
    header = request.headers.get("x-hub-signature-256") or request.headers.get(
        "x-hub-signature"
    )
    if not header:
        return None
    header = header.strip()
    if header.startswith("sha256="):
        return header[7:]
    return header


def _validate_signature(body: bytes, request: Request) -> bool:
    settings = get_settings()
    secret = settings.whatsapp_webhook_secret
    if not secret:
        # Dev/stub mode: accept but never in prod (fail-closed).
        return settings.app_env.strip().lower() != "prod"
    signature = _extract_signature(request)
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the first inbound message from Meta's nested webhook shape."""
    entry = payload.get("entry")
    if isinstance(entry, list) and entry:
        changes = _as_dict(entry[0]).get("changes")
        if isinstance(changes, list) and changes:
            value = _as_dict(_as_dict(changes[0]).get("value"))
            messages = value.get("messages")
            if isinstance(messages, list) and messages:
                return _as_dict(messages[0])
    direct = payload.get("message")
    if isinstance(direct, dict):
        return direct
    return {}


def _extract_text(msg: dict[str, Any], payload: dict[str, Any]) -> str:
    candidates = [
        msg.get("text"),
        msg.get("body"),
        payload.get("text"),
        payload.get("message") if isinstance(payload.get("message"), str) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("body")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _extract_button(msg: dict[str, Any]) -> str:
    button = _as_dict(msg.get("button"))
    value = button.get("payload") or button.get("text")
    if isinstance(value, str):
        return value
    interactive = _as_dict(msg.get("interactive"))
    reply = _as_dict(interactive.get("button_reply")) or _as_dict(
        interactive.get("list_reply")
    )
    value = reply.get("id") or reply.get("title")
    return value if isinstance(value, str) else ""


def _is_confirmation(msg: dict[str, Any], payload: dict[str, Any]) -> bool:
    text = _extract_text(msg, payload).strip().lower()
    if text.startswith("confirm"):
        return True
    if text in CONFIRM_KEYWORDS:
        return True
    button = _extract_button(msg).strip().lower()
    return button.startswith("confirm") or button in CONFIRM_KEYWORDS


def _extract_uuid(payload: dict[str, Any], key: str) -> uuid.UUID | None:
    message = _first_message(payload)
    scopes = [
        payload,
        _as_dict(payload.get("data")),
        _as_dict(_as_dict(payload.get("data")).get("metadata")),
        _as_dict(payload.get("metadata")),
        message,
        # Meta nests per-message references under ``messages[0].metadata``.
        _as_dict(message.get("metadata")),
    ]
    for scope in scopes:
        raw = scope.get(key) if isinstance(scope, dict) else None
        if raw is None:
            continue
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError, AttributeError):
            continue
    return None


@router.post("/webhooks/whatsapp", response_model=None)
async def whatsapp_webhook(request: Request) -> JSONResponse:
    if not _check_rate(request):
        return JSONResponse(status_code=429, content={"detail": "too many requests"})

    body = await request.body()
    if not _validate_signature(body, request):
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "invalid payload"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"detail": "invalid payload"})

    msg = _first_message(payload)
    if not _is_confirmation(msg, payload):
        # Non-confirmation traffic is acknowledged without side effects.
        return JSONResponse(status_code=200, content={"ok": True})

    turno_id = _extract_uuid(payload, "turno_id")
    token = payload.get("token")
    if turno_id is None and isinstance(token, str):
        by_token = await runtime.TURNOS.find_by_token(token)
        if by_token is not None:
            turno_id = by_token.id
    if turno_id is None:
        return JSONResponse(status_code=200, content={"ok": True})

    turno = await runtime.TURNOS.get(turno_id)
    if turno is None or turno.estado in ESTADOS_NO_CONFIRMABLES:
        return JSONResponse(status_code=200, content={"ok": True})

    if turno.estado != "confirmado":
        auditor = getattr(request.app.state, "audit_webhook_recorder", None)
        if auditor is not None:
            await auditor(
                tenant_id=turno.tenant_id, actor_usuario_id=None,
                evento="turno_confirmacion_whatsapp_solicitada", recurso="agenda",
                recurso_id=str(turno.id), metodo="WEBHOOK",
                ruta="/webhooks/whatsapp",
            )
        ahora = datetime.datetime.now(datetime.UTC)
        await runtime.TURNOS.add(
            dataclasses.replace(turno, estado="confirmado", confirmado_at=ahora)
        )
        # Audit the confirmation as a recordatorio row (idempotent by unique key).
        rec = await runtime.SERVICE.programar(
            turno_id=turno.id,
            tenant_id=turno.tenant_id,
            tipo=TIPO_CONFIRMACION,
            canal=CANAL_WHATSAPP,
            destinatario=turno.contacto_whatsapp,
            enviar_at=ahora,
            paciente_id=turno.paciente_id,
        )
        rec.estado = "confirmado"
        rec.confirmado_at = ahora
        await runtime.RECORDATORIOS.update(rec)

    return JSONResponse(status_code=200, content={"ok": True})


__all__ = [
    "router",
    "CONFIRM_KEYWORDS",
    "ESTADOS_NO_CONFIRMABLES",
    "reset_rate_limit",
]
