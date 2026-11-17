"""C-10 Mercado Pago IPN webhook endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.application.cobros import (
    ESTADO_TURNO_CANCELADO,
    ESTADO_TURNO_CONFIRMADO,
    CobroService,
    MemoryCobroStore,
)
from app.shared.settings import get_settings

router = APIRouter(tags=["cobros-webhook"])

# Shared in-memory store (tests may replace via module attribute).
STORE: MemoryCobroStore = MemoryCobroStore()

# Shared in-memory cobros service (scaffold; owns pago + turno transitions).
SERVICE: CobroService = CobroService()

# Track processed mp_payment_ids for idempotency.
_PROCESSED: set[str] = set()

# IPN statuses that close the cobro flow: approved (acredita) or terminal
# rejected/expired (anulan la reserva y liberan el hueco).
_ESTADOS_ANULABLES = frozenset({"rejected", "expired", "denied"})


def _extract_sig(header: str | None) -> str | None:
    if not header:
        return None
    header = header.strip()
    # x-signature: ts=...,v1=<hex>
    if "=" in header and "," in header:
        for part in header.split(","):
            part = part.strip()
            if part.startswith("v1="):
                return part[3:]
    # x-hub-signature-256: sha256=<hex>
    if header.startswith("sha256="):
        return header[7:]
    # bare hex
    return header


def _validate_signature(body: bytes, request: Request) -> bool:
    secret = get_settings().mp_webhook_secret
    if not secret:
        return True
    sig = _extract_sig(
        request.headers.get("x-signature")
        or request.headers.get("x-hub-signature-256")
        or request.headers.get("x-hub-signature")
    )
    if not sig:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _extract_status(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload, dict) else None
    status = None
    if isinstance(data, dict):
        status = data.get("status")
    if status is None and isinstance(payload, dict):
        status = payload.get("status") or payload.get("payment_status") or payload.get("state")
    return str(status).lower() if status is not None else None


def _extract_turno_id(payload: dict) -> uuid.UUID:
    data = payload.get("data") if isinstance(payload, dict) else None
    raw: object = None
    if isinstance(data, dict):
        meta = data.get("metadata")
        raw = data.get("turno_id") or (
            meta.get("turno_id") if isinstance(meta, dict) else None
        )
    if raw is None and isinstance(payload, dict):
        meta = payload.get("metadata")
        raw = payload.get("turno_id") or (
            meta.get("turno_id") if isinstance(meta, dict) else None
        )
    try:
        return uuid.UUID(str(raw)) if raw is not None else uuid.uuid4()
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid4()


def _extract_tenant_id(payload: dict) -> uuid.UUID:
    """Tenant echoed from the order metadata (fallback: random scaffold id)."""
    data = payload.get("data") if isinstance(payload, dict) else None
    raw: object = None
    if isinstance(data, dict):
        meta = data.get("metadata")
        raw = data.get("tenant_id") or (
            meta.get("tenant_id") if isinstance(meta, dict) else None
        )
    if raw is None and isinstance(payload, dict):
        meta = payload.get("metadata")
        raw = payload.get("tenant_id") or (
            meta.get("tenant_id") if isinstance(meta, dict) else None
        )
    try:
        return uuid.UUID(str(raw)) if raw is not None else uuid.uuid4()
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid4()


def _extract_monto(payload: dict) -> float:
    data = payload.get("data") if isinstance(payload, dict) else None
    raw: object = None
    if isinstance(data, dict):
        raw = data.get("transaction_amount") or data.get("amount") or data.get("total")
    if raw is None and isinstance(payload, dict):
        raw = payload.get("transaction_amount") or payload.get("amount")
    try:
        return float(raw or 0)
    except (ValueError, TypeError):
        return 0.0


def _extract_mp_order_id(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload, dict) else None
    order: dict = data.get("order") if isinstance(data, dict) else None
    raw = order.get("id") if isinstance(order, dict) else None
    if raw is None and isinstance(data, dict):
        meta = data.get("metadata")
        raw = meta.get("mp_order_id") if isinstance(meta, dict) else None
    return str(raw) if raw is not None else None


@router.post("/webhooks/mercadopago")
async def ipn_webhook(request: Request):
    body = await request.body()
    if not _validate_signature(body, request):
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}

    # Extract mp_payment_id from various IPN shapes.
    data = payload.get("data") if isinstance(payload, dict) else None
    mp_payment_id = None
    status = None
    if isinstance(data, dict):
        mp_payment_id = data.get("id")
        status = data.get("status")
    if mp_payment_id is None and isinstance(payload, dict):
        mp_payment_id = payload.get("id") or payload.get("mp_payment_id")
    mp_payment_id = str(mp_payment_id) if mp_payment_id is not None else None
    status = _extract_status(payload)

    if mp_payment_id is None:
        return JSONResponse(status_code=400, content={"detail": "missing payment id"})

    # Idempotency.
    if mp_payment_id in _PROCESSED:
        return {"ok": True, "idempotent": True}
    existing = await STORE.find_by_mp_payment_id(mp_payment_id)
    if existing is not None:
        _PROCESSED.add(mp_payment_id)
        return {"ok": True, "idempotent": True}

    turno_id = _extract_turno_id(payload)
    tenant_id = _extract_tenant_id(payload)
    monto = _extract_monto(payload)

    if status == "approved":
        # IPN acreditado: turno -> `confirmado` (RN-TU-04 / design C-10).
        auditor = getattr(request.app.state, "audit_webhook_recorder", None)
        if auditor is not None:
            await auditor(
                tenant_id=tenant_id, actor_usuario_id=None,
                evento="cobro_mp_acreditacion_solicitada", recurso="cobro",
                recurso_id=str(turno_id), metodo="WEBHOOK",
                ruta="/webhooks/mercadopago",
            )
        pago = await SERVICE.acreditar(
            turno_id=turno_id,
            tenant_id=tenant_id,
            mp_payment_id=mp_payment_id,
            mp_order_id=_extract_mp_order_id(payload),
            monto=monto,
        )
        _PROCESSED.add(mp_payment_id)
        return {
            "ok": True,
            "idempotent": False,
            "estado": pago.estado,
            "turno": {"id": str(turno_id), "estado": ESTADO_TURNO_CONFIRMADO},
        }

    if status is not None and status in _ESTADOS_ANULABLES:
        # IPN vencido/rechazado: turno -> `cancelado` + liberar hueco (RN-AD-04, RN-G-02).
        auditor = getattr(request.app.state, "audit_webhook_recorder", None)
        if auditor is not None:
            await auditor(
                tenant_id=tenant_id, actor_usuario_id=None,
                evento="cobro_mp_anulacion_solicitada", recurso="cobro",
                recurso_id=str(turno_id), metodo="WEBHOOK",
                ruta="/webhooks/mercadopago",
            )
        motivo = "vencido" if status == "expired" else "rechazado"
        pago = await SERVICE.anular(
            turno_id=turno_id,
            tenant_id=tenant_id,
            mp_payment_id=mp_payment_id,
            monto=monto,
            motivo=motivo,
        )
        _PROCESSED.add(mp_payment_id)
        return {
            "ok": True,
            "idempotent": False,
            "estado": pago.estado,
            "turno": {"id": str(turno_id), "estado": ESTADO_TURNO_CANCELADO},
        }

    # Estados intermedios (ej. pending): registrados sin transicionar el turno.
    _PROCESSED.add(mp_payment_id)
    return {"ok": True, "idempotent": False, "estado": status or "pendiente"}
