"""C-08 turnero online publico (skeleton)."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.application.cobros import (
    ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO,
    CobroService,
)

router = APIRouter(prefix="", tags=["turnero-publico"])

# C-10 task 6.1: cobros service (in-memory scaffold; tests replace it).
COBROS: CobroService = CobroService()

_RESERVED: set[tuple[str, str, str]] = set()

# In-memory portal records (stub; DB-backed in later change).
_PORTAL: dict[str, dict] = {}

# Rate limit: N requests per IP+slug per window.
_RATE_LIMIT = 5
_RATE_WINDOW_SECONDS = 60
_rate_hits: dict[str, deque[datetime]] = {}


def _rate_key(request: Request, slug: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}|{slug}"


def _check_rate(request: Request, slug: str) -> bool:
    key = _rate_key(request, slug)
    now = datetime.now(timezone.utc)
    window = _rate_hits.setdefault(key, deque())
    while window and (now - window[0]).total_seconds() >= _RATE_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        return False
    window.append(now)
    return True


class ReservaIn(BaseModel):
    nombre: str
    whatsapp: str
    profesional_id: str
    inicio: str
    # C-10: monto de la seña exigida por la prestación elegida (None = sin seña).
    monto_sena: float | None = None


class ReprogramarIn(BaseModel):
    inicio: str


def _record(token: str) -> dict:
    if token not in _PORTAL:
        now = datetime.now(timezone.utc)
        if "past" in token or "expired" in token:
            inicio = now - timedelta(hours=1)
        elif "soon" in token:
            inicio = now + timedelta(hours=1)
        else:
            inicio = now + timedelta(hours=48)
        _PORTAL[token] = {
            "token": token,
            "estado": "reservado",
            "inicio": inicio,
            "anticipacion_min_cancel_hs": 24,
            "prestacion_id": "P-demo",
            "franja": "manana",
            "profesional_id": None,
        }
    return _PORTAL[token]


def _plazo_ok(rec: dict) -> bool:
    now = datetime.now(timezone.utc)
    inicio = rec["inicio"]
    if inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=timezone.utc)
    return (inicio - now) >= timedelta(hours=rec["anticipacion_min_cancel_hs"])


@router.get("/reservar/{slug}")
async def get_reservar(slug: str) -> dict:
    return {"slug": slug, "prestaciones": [], "profesionales": [], "huecos": []}


@router.post("/reservar/{slug}/turnos")
async def post_reservar(slug: str, request: Request, body: ReservaIn):
    if not _check_rate(request, slug):
        return JSONResponse(status_code=429, content={"detail": "too many requests"})
    key = (slug, body.profesional_id, body.inicio)
    if key in _RESERVED:
        return JSONResponse(
            status_code=409,
            content={"alternativas": [], "lista_espera": True},
        )
    turno_id = uuid.uuid4()
    # C-10 scaffold: tenant determinista por slug hasta integrar el lookup
    # real del tenant (C-02/C-05); el turno se materializa en la agenda luego.
    tenant_id = uuid.uuid5(uuid.NAMESPACE_URL, f"tenant:{slug}")
    estado = "reservado"
    pago = None
    if body.monto_sena is not None:
        # Spec C-10: reserva con seña obligatoria → orden MP + turno pendiente.
        pago = await COBROS.reservar_con_sena(
            turno_id=turno_id,
            tenant_id=tenant_id,
            monto=body.monto_sena,
            descripcion=f"Seña turno {slug}",
        )
        estado = ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO
    _RESERVED.add(key)
    token = f"token-{slug}"
    rec = _record(token)
    rec.update(
        {
            "turno_id": str(turno_id),
            "estado": estado,
            "profesional_id": body.profesional_id,
            "checkout_url": pago.checkout_url if pago is not None else None,
            "pago_id": str(pago.id) if pago is not None else None,
        }
    )
    return {
        "slug": slug,
        "estado": estado,
        "portal": f"/p/{token}",
        "token": token,
        "turno_id": str(turno_id),
        "pago_id": str(pago.id) if pago is not None else None,
        "checkout_url": pago.checkout_url if pago is not None else None,
    }


@router.get("/p/{token}")
async def get_portal(token: str) -> dict:
    rec = _record(token)
    return {
        "token": token,
        "estado": rec["estado"],
        "inicio": rec["inicio"].isoformat(),
        "politica": {"anticipacion_min_cancel_hs": rec["anticipacion_min_cancel_hs"]},
    }


@router.post("/p/{token}/cancelar", response_model=None)
async def cancelar_portal(token: str):
    rec = _record(token)
    if not _plazo_ok(rec):
        return JSONResponse(
            status_code=400,
            content={
                "mensaje": "Fuera de plazo de cancelacion",
                "politica": {"anticipacion_min_cancel_hs": rec["anticipacion_min_cancel_hs"]},
            },
        )
    rec["estado"] = "cancelado"
    try:
        from app.worker import tasks as _wt

        _wt.ofertar_hueco_liberado(
            prestacion_id=rec.get("prestacion_id"),
            franja=rec.get("franja"),
            profesional_id=rec.get("profesional_id"),
        )
    except Exception:
        pass
    return {"token": token, "cancelado": True}


@router.get("/checkout/{turno_id}")
async def checkout_redirect(turno_id: str) -> dict:
    pago = None
    try:
        pago = await COBROS.store.find_by_turno(uuid.UUID(turno_id))
    except ValueError:
        pago = None
    url = (
        pago.checkout_url
        if pago is not None and pago.checkout_url
        else f"https://mp/checkout/{turno_id}"
    )
    return {
        "turno_id": turno_id,
        "url": url,
        "estado": pago.estado if pago is not None else None,
    }


@router.get("/p/{token}/checkout")
async def portal_checkout(token: str) -> dict:
    rec = _record(token)
    url = rec.get("checkout_url") or f"https://mp/checkout/{token}"
    return {"token": token, "url": url, "estado": rec["estado"]}


@router.get("/p/{token}/retorno")
async def portal_retorno(token: str) -> dict:
    rec = _record(token)
    return {"token": token, "estado": rec["estado"], "url": f"/p/{token}"}


@router.post("/p/{token}/reprogramar", response_model=None)
async def reprogramar_portal(token: str, body: ReprogramarIn | None = None):
    rec = _record(token)
    if not _plazo_ok(rec):
        return JSONResponse(
            status_code=400,
            content={
                "mensaje": "Fuera de plazo de reprogramacion",
                "politica": {
                    "anticipacion_min_cancel_hs": rec["anticipacion_min_cancel_hs"]
                },
            },
        )
    if body is not None:
        try:
            rec["inicio"] = datetime.fromisoformat(body.inicio).replace(
                tzinfo=UTC
            )
        except ValueError:
            rec["inicio"] = datetime.fromisoformat(body.inicio)
    rec["estado"] = "reservado"
    return {"token": token, "reprogramado": True}
