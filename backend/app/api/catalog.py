"""C-05 catalog HTTP seam: 4 CRUD resources + internal huecos query (D4).

- ``tenant_id`` comes ONLY from the verified JWT principal (D4) — never
  from query/body/path. Cross-tenant ids read as missing → uniform 404.
- RBAC (D4): writes (POST/PATCH/DELETE) require ``propietario``; reads
  allow any staff role (``propietario|odontologo|recepcion|asistente``).
- Persistence goes through the ``CatalogStore`` port: production wires
  ``DbCatalogStore`` over the tenant-pinned session; tests inject the
  in-memory fake. Uniform errors flow through ``AppError``.
- ``GET /agenda/huecos`` is an INTERNAL staff-only query (no public
  surface, no rate-limit/captcha needed — D4 tradeoff): C-06/C-08 reuse
  the same pure generator. Sillón-level bloqueos are not applied here
  (no sillón context without turnos yet — C-06 adds it).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter

from app.api.catalog_schemas import (
    BloqueoCreate,
    BloqueoRead,
    BloqueoUpdate,
    PrestacionCreate,
    PrestacionRead,
    PrestacionUpdate,
    ProfesionalCreate,
    ProfesionalRead,
    ProfesionalUpdate,
    SillonCreate,
    SillonRead,
    SillonUpdate,
)
from app.api.deps import (
    get_current_principal,
    require_any,
    require_role,
    tenant_session,
)
from app.application.agenda_slots import Ocupacion, generate_slots
from app.application.auth_service import Principal
from app.application.catalog_store import CatalogStore, DbCatalogStore
from app.shared.exceptions import AppError

__all__ = ["router", "get_catalog_store", "get_current_principal"]

STAFF_ROLES = ("propietario", "odontologo", "recepcion", "asistente")

READ_GUARD = require_any(*STAFF_ROLES)
WRITE_GUARD = require_role("propietario")

_NOT_FOUND = {"description": "Inexistente en este tenant (incluye cross-tenant)"}
_FORBIDDEN = {"description": "Rol sin permiso de escritura de catalogo"}
_UNAUTHORIZED = {"description": "JWT ausente o invalido"}
_UNPROCESSABLE = {"description": "Regla de negocio violada (detalle en body)"}

router = APIRouter()


async def get_catalog_store(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> CatalogStore:
    """Production store: DB-backed, pinned to the JWT tenant (D4)."""
    return DbCatalogStore(session, principal.tenant_id)  # type: ignore[return-value]


def _principal_tenant(principal: Principal) -> uuid.UUID:
    return principal.tenant_id


async def _require_prestaciones_exist(
    store: CatalogStore, prestacion_ids: list[uuid.UUID]
) -> None:
    for prestacion_id in prestacion_ids:
        if await store.get_prestacion(prestacion_id) is None:
            raise AppError(f"prestacion inexistente en el tenant: {prestacion_id}", 422)


# --- Prestaciones ---


@router.get(
    "/prestaciones",
    response_model=list[PrestacionRead],
    summary="Listar prestaciones",
    description="Catalogo de prestaciones del tenant (solo lectura staff). "
    "Ejemplo ficticio: Limpieza 45' + buffer 10'.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN},
)
async def list_prestaciones(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    rows = await store.list_prestaciones(limit=limit, offset=offset)
    return [PrestacionRead.model_validate(row) for row in rows]


@router.post(
    "/prestaciones",
    response_model=PrestacionRead,
    status_code=201,
    summary="Crear prestacion",
    description="Alta de prestacion con reglas (duracion>0, sena exige monto). "
    "Solo propietario. Ejemplo ficticio: Consulta 30'.",
    responses={
        201: {"description": "Prestacion creada"},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        422: _UNPROCESSABLE,
    },
)
async def create_prestacion(
    body: PrestacionCreate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.create_prestacion(body.model_dump())
    return PrestacionRead.model_validate(row)


@router.get(
    "/prestaciones/{prestacion_id}",
    response_model=PrestacionRead,
    summary="Ver prestacion",
    description="Detalle de una prestacion del tenant. Cross-tenant responde 404.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def get_prestacion(
    prestacion_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.get_prestacion(prestacion_id)
    if row is None:
        raise AppError("not found", 404)
    return PrestacionRead.model_validate(row)


@router.patch(
    "/prestaciones/{prestacion_id}",
    response_model=PrestacionRead,
    summary="Editar prestacion",
    description="Edicion parcial. Cambiar duracion NO altera turnos ya creados "
    "(cada turno congela su duracion en C-06; contrato RN-AG-03). Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND, 422: _UNPROCESSABLE},
)
async def update_prestacion(
    prestacion_id: uuid.UUID,
    body: PrestacionUpdate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.update_prestacion(
        prestacion_id, body.model_dump(exclude_unset=True)
    )
    if row is None:
        raise AppError("not found", 404)
    return PrestacionRead.model_validate(row)


@router.delete(
    "/prestaciones/{prestacion_id}",
    status_code=204,
    summary="Dar de baja prestacion",
    description="Baja LOGICA (is_active=false + deleted_at): deja de ofrecerse "
    "sin romper turnos historicos. Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def delete_prestacion(
    prestacion_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Response:
    _ = _principal_tenant(principal)
    if not await store.delete_prestacion(prestacion_id):
        raise AppError("not found", 404)
    return Response(status_code=204)


# --- Profesionales ---


@router.get(
    "/profesionales",
    response_model=list[ProfesionalRead],
    summary="Listar profesionales",
    description="Profesionales del tenant con prestaciones habilitadas. "
    "Ejemplo ficticio: Dra. Demo con Limpieza + Consulta.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN},
)
async def list_profesionales(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    rows = await store.list_profesionales(limit=limit, offset=offset)
    return [ProfesionalRead.model_validate(row) for row in rows]


@router.post(
    "/profesionales",
    response_model=ProfesionalRead,
    status_code=201,
    summary="Crear profesional",
    description="Alta con al menos una prestacion habilitada del tenant "
    "(sin habilitacion no es agendable → 422). Solo propietario.",
    responses={
        201: {"description": "Profesional creado"},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        422: _UNPROCESSABLE,
    },
)
async def create_profesional(
    body: ProfesionalCreate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    await _require_prestaciones_exist(store, body.prestacion_ids)
    row = await store.create_profesional(body.model_dump())
    await store.set_habilitaciones(row["id"], body.prestacion_ids)
    full = await store.get_profesional(row["id"])
    assert full is not None
    return ProfesionalRead.model_validate(full)


@router.get(
    "/profesionales/{profesional_id}",
    response_model=ProfesionalRead,
    summary="Ver profesional",
    description="Detalle con habilitaciones. Cross-tenant responde 404.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def get_profesional(
    profesional_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.get_profesional(profesional_id)
    if row is None:
        raise AppError("not found", 404)
    return ProfesionalRead.model_validate(row)


@router.patch(
    "/profesionales/{profesional_id}",
    response_model=ProfesionalRead,
    summary="Editar profesional",
    description="Edicion parcial; vaciar habilitaciones deja no agendable → 422. "
    "Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND, 422: _UNPROCESSABLE},
)
async def update_profesional(
    profesional_id: uuid.UUID,
    body: ProfesionalUpdate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    patch = body.model_dump(exclude_unset=True)
    prestacion_ids = patch.pop("prestacion_ids", None)
    if prestacion_ids is not None:
        await _require_prestaciones_exist(store, prestacion_ids)
    row = await store.update_profesional(profesional_id, patch)
    if row is None:
        raise AppError("not found", 404)
    if prestacion_ids is not None:
        await store.set_habilitaciones(profesional_id, prestacion_ids)
        row = await store.get_profesional(profesional_id)
        assert row is not None
    return ProfesionalRead.model_validate(row)


@router.delete(
    "/profesionales/{profesional_id}",
    status_code=204,
    summary="Dar de baja profesional",
    description="Baja logica reversible. Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def delete_profesional(
    profesional_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Response:
    _ = _principal_tenant(principal)
    if not await store.delete_profesional(profesional_id):
        raise AppError("not found", 404)
    return Response(status_code=204)


# --- Sillones ---


@router.get(
    "/sillones",
    response_model=list[SillonRead],
    summary="Listar sillones",
    description="Recursos box del tenant. Ejemplo ficticio: Box 1 (demo).",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN},
)
async def list_sillones(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    rows = await store.list_sillones(limit=limit, offset=offset)
    return [SillonRead.model_validate(row) for row in rows]


@router.post(
    "/sillones",
    response_model=SillonRead,
    status_code=201,
    summary="Crear sillon",
    description="Alta de box. Solo propietario.",
    responses={
        201: {"description": "Sillon creado"},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        422: _UNPROCESSABLE,
    },
)
async def create_sillon(
    body: SillonCreate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.create_sillon(body.model_dump())
    return SillonRead.model_validate(row)


@router.get(
    "/sillones/{sillon_id}",
    response_model=SillonRead,
    summary="Ver sillon",
    description="Detalle. Cross-tenant responde 404.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def get_sillon(
    sillon_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.get_sillon(sillon_id)
    if row is None:
        raise AppError("not found", 404)
    return SillonRead.model_validate(row)


@router.patch(
    "/sillones/{sillon_id}",
    response_model=SillonRead,
    summary="Editar sillon",
    description="Incluye activo=false (deja de ofrecerse hasta reactivar). "
    "Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND, 422: _UNPROCESSABLE},
)
async def update_sillon(
    sillon_id: uuid.UUID,
    body: SillonUpdate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.update_sillon(sillon_id, body.model_dump(exclude_unset=True))
    if row is None:
        raise AppError("not found", 404)
    return SillonRead.model_validate(row)


@router.delete(
    "/sillones/{sillon_id}",
    status_code=204,
    summary="Dar de baja sillon",
    description="Baja logica reversible. Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def delete_sillon(
    sillon_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Response:
    _ = _principal_tenant(principal)
    if not await store.delete_sillon(sillon_id):
        raise AppError("not found", 404)
    return Response(status_code=204)


# --- Bloqueos ---


@router.get(
    "/bloqueos",
    response_model=list[BloqueoRead],
    summary="Listar bloqueos",
    description="Ventanas no disponibles (RN-AG-05). Ejemplo ficticio: "
    "feriado 25/12 del profesional demo.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN},
)
async def list_bloqueos(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    rows = await store.list_bloqueos(limit=limit, offset=offset)
    return [BloqueoRead.model_validate(row) for row in rows]


@router.post(
    "/bloqueos",
    response_model=BloqueoRead,
    status_code=201,
    summary="Crear bloqueo",
    description="Bloqueo con motivo y al menos un objetivo (profesional/sillon). "
    "Solo propietario.",
    responses={
        201: {"description": "Bloqueo creado"},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        422: _UNPROCESSABLE,
    },
)
async def create_bloqueo(
    body: BloqueoCreate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    if body.profesional_id is not None and (
        await store.get_profesional(body.profesional_id) is None
    ):
        raise AppError("profesional inexistente en el tenant", 422)
    if body.sillon_id is not None and await store.get_sillon(body.sillon_id) is None:
        raise AppError("sillon inexistente en el tenant", 422)
    row = await store.create_bloqueo(body.model_dump())
    return BloqueoRead.model_validate(row)


@router.get(
    "/bloqueos/{bloqueo_id}",
    response_model=BloqueoRead,
    summary="Ver bloqueo",
    description="Detalle. Cross-tenant responde 404.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def get_bloqueo(
    bloqueo_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    row = await store.get_bloqueo(bloqueo_id)
    if row is None:
        raise AppError("not found", 404)
    return BloqueoRead.model_validate(row)


@router.patch(
    "/bloqueos/{bloqueo_id}",
    response_model=BloqueoRead,
    summary="Editar bloqueo",
    description="Edicion parcial con mismas reglas (objetivo, fin>inicio). "
    "Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND, 422: _UNPROCESSABLE},
)
async def update_bloqueo(
    bloqueo_id: uuid.UUID,
    body: BloqueoUpdate,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Any:
    _ = _principal_tenant(principal)
    patch = body.model_dump(exclude_unset=True)
    if patch.get("profesional_id") is not None and (
        await store.get_profesional(patch["profesional_id"]) is None
    ):
        raise AppError("profesional inexistente en el tenant", 422)
    if patch.get("sillon_id") is not None and (
        await store.get_sillon(patch["sillon_id"]) is None
    ):
        raise AppError("sillon inexistente en el tenant", 422)
    current = await store.get_bloqueo(bloqueo_id)
    if current is None:
        raise AppError("not found", 404)
    inicio = patch.get("inicio", current["inicio"])
    fin = patch.get("fin", current["fin"])
    if fin <= inicio:
        raise AppError("fin debe ser posterior a inicio", 422)
    row = await store.update_bloqueo(bloqueo_id, patch)
    assert row is not None
    return BloqueoRead.model_validate(row)


@router.delete(
    "/bloqueos/{bloqueo_id}",
    status_code=204,
    summary="Eliminar bloqueo",
    description="Baja logica (reabre los huecos del rango). Solo propietario.",
    responses={401: _UNAUTHORIZED, 403: _FORBIDDEN, 404: _NOT_FOUND},
)
async def delete_bloqueo(
    bloqueo_id: uuid.UUID,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(WRITE_GUARD),
) -> Response:
    _ = _principal_tenant(principal)
    if not await store.delete_bloqueo(bloqueo_id):
        raise AppError("not found", 404)
    return Response(status_code=204)


# --- Huecos (consulta interna, solo staff) ---


@router.get(
    "/agenda/huecos",
    summary="Consultar huecos disponibles",
    description="Genera huecos en multiplos de duracion+buffer descontando "
    "bloqueos del profesional (RN-AG-04). Interno staff: valida ventana y "
    "existencia en tenant. Sin turnos aun (C-06 los alimenta).",
    responses={
        200: {"description": "Lista de huecos [inicio, fin)"},
        400: {"description": "Ventana invalida"},
        401: _UNAUTHORIZED,
        403: _FORBIDDEN,
        404: _NOT_FOUND,
        422: _UNPROCESSABLE,
    },
)
async def get_huecos(
    profesional_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    desde: datetime,
    hasta: datetime,
    store: CatalogStore = Depends(get_catalog_store),
    principal: Principal = Depends(READ_GUARD),
) -> dict[str, list[dict[str, str]]]:
    """Huecos validos del profesional para la prestacion en la ventana."""
    _ = _principal_tenant(principal)
    if hasta <= desde:
        raise AppError("hasta debe ser posterior a desde", 400)
    profesional = await store.get_profesional(profesional_id)
    if profesional is None:
        raise AppError("not found", 404)
    prestacion = await store.get_prestacion(prestacion_id)
    if prestacion is None:
        raise AppError("not found", 404)
    if prestacion_id not in profesional.get("prestacion_ids", []):
        raise AppError("profesional no habilitado en la prestacion", 422)
    if not profesional.get("activo", True) or not prestacion.get("is_active", True):
        return {"huecos": []}
    bloqueos = await store.list_bloqueos_for_profesional(
        profesional_id, desde=desde, hasta=hasta
    )
    slots = generate_slots(
        ventana_inicio=desde,
        ventana_fin=hasta,
        duracion_min=prestacion["duracion_min"],
        buffer_min=prestacion.get("buffer_min", 0),
        turnos=[],
        bloqueos=[
            Ocupacion(inicio=row["inicio"], fin=row["fin"]) for row in bloqueos
        ],
    )
    return {
        "huecos": [
            {"inicio": slot.inicio.isoformat(), "fin": slot.fin.isoformat()}
            for slot in slots
        ]
    }
