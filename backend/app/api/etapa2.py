"""Explicit, authenticated 501 stubs for integrations outside v1.0."""

from __future__ import annotations

from typing import NoReturn

from fastapi import Depends
from fastapi.routing import APIRouter

from app.api.audit import audit_sensitive_request
from app.api.deps import require_role
from app.shared.exceptions import AppError

router = APIRouter(
    prefix="/etapa2",
    tags=["etapa2-stubs"],
    dependencies=[Depends(audit_sensitive_request), Depends(require_role("propietario"))],
)
MESSAGE = "Integración reservada para etapa 2; no está disponible en v1.0."


def _stub() -> NoReturn:
    raise AppError(MESSAGE, 501)


_STUBS: tuple[tuple[str, str, str], ...] = (
    ("POST", "/arca/comprobantes", "emision_fiscal_arca"),
    ("POST", "/obras-sociales/liquidaciones", "liquidaciones_obras_sociales"),
    ("POST", "/recetario/renapdis", "recetario_renapdis"),
    ("POST", "/ia/notas-voz", "ia_notas_voz"),
    ("POST", "/ia/no-show-score", "ia_no_show_score"),
    ("GET", "/perfil-publico", "perfil_publico"),
    ("GET", "/api-publica", "api_publica"),
    ("POST", "/integraciones/radiologia", "integracion_radiologia"),
    ("POST", "/integraciones/laboratorio", "integracion_laboratorio"),
)

for _method, _path, _name in _STUBS:
    router.add_api_route(
        _path,
        _stub,
        methods=[_method],
        response_model=None,
        name=_name,
        operation_id=f"stub_{_name}",
        responses={501: {"description": MESSAGE}},
    )
