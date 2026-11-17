"""Auditing dependency for authenticated, sensitive API surfaces."""

from __future__ import annotations

import uuid

from fastapi import Depends, Request
from sqlalchemy import text

from app.api.deps import get_current_principal
from app.application.auth_service import Principal
from app.domain.admin.models import AuditEvento
from app.shared.db import get_session_factory


async def audit_sensitive_request(
    request: Request,
    principal: Principal = Depends(get_current_principal),
) -> None:
    recorder = getattr(request.app.state, "audit_recorder", None)
    if recorder is None:
        return
    await recorder(request, principal)


async def record_api_event(request: Request, principal: Principal) -> None:
    path = request.url.path
    if (
        "/historias-clinicas" in path
        or "/odontogramas" in path
        or "/adjuntos" in path
        or "/consentimientos" in path
        or "/pacientes" in path
    ):
        resource = "hce"
        event = "hce_consultada" if request.method == "GET" else "hce_cambio"
    elif (
        "/caja" in path
        or "/cuenta-corriente" in path
        or "/movimientos-cc" in path
        or "/recaudacion" in path
    ):
        resource = "cobros"
        event = "cobro_consultado" if request.method == "GET" else "cobro_cambio"
    elif "/turnos" in path or "/agenda" in path:
        resource = "agenda"
        event = "agenda_consultada" if request.method == "GET" else "agenda_cambio"
    elif "/presupuestos" in path:
        resource = "presupuestos"
        event = (
            "presupuesto_consultado"
            if request.method == "GET"
            else "presupuesto_cambio"
        )
    elif "/reportes" in path:
        resource, event = "reportes", "reporte_consultado"
    else:
        resource, event = "administracion", (
            "recurso_consultado" if request.method == "GET" else "recurso_cambio"
        )

    try:
        actor_id = uuid.UUID(principal.sub)
    except ValueError:
        actor_id = None
    segments = path.strip("/").split("/")
    resource_id = next((part for part in reversed(segments) if _is_uuid(part)), None)
    await record_tenant_event(
        tenant_id=principal.tenant_id,
        actor_usuario_id=actor_id,
        evento=event,
        recurso=resource,
        recurso_id=resource_id,
        metodo=request.method,
        ruta=path,
    )


async def record_tenant_event(
    *,
    tenant_id: uuid.UUID,
    actor_usuario_id: uuid.UUID | None,
    evento: str,
    recurso: str,
    recurso_id: str | None,
    metodo: str,
    ruta: str,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            session.add(
                AuditEvento(
                    tenant_id=tenant_id,
                    actor_usuario_id=actor_usuario_id,
                    evento=evento,
                    recurso=recurso,
                    recurso_id=recurso_id,
                    metodo=metodo,
                    ruta=ruta[:255],
                )
            )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
