"""C-13 clinical API: odontogram, attachments and signed consents."""

from __future__ import annotations

import uuid
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from fastapi import Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    get_current_principal,
    require_any,
    tenant_session,
)
from app.api.audit import audit_sensitive_request, record_tenant_event
from app.application.auth_service import Principal
from app.application.clinica import (
    AdjuntoService,
    ConsentimientoRecord,
    ConsentimientoService,
    DbAdjuntoStore,
    DbConsentimientoStore,
    DbEventoPiezaStore,
    DbOdontogramaStore,
    OdontogramaService,
    OdontogramaView,
)
from app.application.pacientes import (
    AccesoClinicoService,
    DbAccesoClinicoStore,
    DbDerivacionStore,
    DbHistoriaStore,
    DbPacienteStore,
)
from app.infrastructure.pdf import SimplePdfWriter
from app.infrastructure.storage import StoragePort, build_storage
from app.shared.exceptions import AppError
from app.shared.settings import get_settings

__all__ = ["router", "get_clinica_services", "get_storage"]

CLINICAL_GUARD = require_any("propietario", "odontologo")

router = APIRouter(tags=["clinica"], dependencies=[Depends(audit_sensitive_request)])
storage_router = APIRouter(tags=["clinica-storage"])


@dataclass(frozen=True)
class ClinicaServices:
    odontogramas: OdontogramaService
    adjuntos: AdjuntoService
    consentimientos: ConsentimientoService


@lru_cache(maxsize=1)
def get_storage() -> StoragePort:
    """Configured storage backend (cached: memory must persist across calls)."""
    return build_storage()


async def get_clinica_services(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> ClinicaServices:
    """Production services pinned to the JWT tenant (D11/D14)."""
    tenant = principal.tenant_id
    settings = get_settings()
    historias = DbHistoriaStore(session, tenant)
    pacientes = DbPacienteStore(session, tenant)
    derivaciones = DbDerivacionStore(session, tenant)
    acceso = AccesoClinicoService(
        DbAccesoClinicoStore(session, tenant), derivaciones
    )
    storage = get_storage()
    return ClinicaServices(
        odontogramas=OdontogramaService(
            DbOdontogramaStore(session, tenant),
            DbEventoPiezaStore(session, tenant),
            historias,
            acceso,
        ),
        adjuntos=AdjuntoService(
            DbAdjuntoStore(session, tenant),
            historias,
            acceso,
            storage,
            max_bytes=settings.adjunto_max_bytes,
            mime_permitidos=settings.mime_permitidos,
        ),
        consentimientos=ConsentimientoService(
            DbConsentimientoStore(session, tenant),
            historias,
            pacientes,
            acceso,
            storage,
            SimplePdfWriter(),
        ),
    )


# --- Schemas ---------------------------------------------------------------


class EstadoPiezaRead(BaseModel):
    pieza_fdi: int
    superficie: str | None = None
    estado: str
    fecha: datetime
    evento_id: uuid.UUID
    autor_usuario_id: uuid.UUID
    autor_profesional_id: uuid.UUID | None = None


class OdontogramaRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    estado_actual: list[EstadoPiezaRead] = Field(default_factory=list)


class EventoPiezaCreate(BaseModel):
    pieza_fdi: int = Field(ge=11, le=48)
    superficie: str | None = Field(default=None, max_length=16)
    estado: str = Field(min_length=1, max_length=16)
    fecha: datetime | None = None
    observaciones: str | None = None


class EventoPiezaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    odontograma_id: uuid.UUID
    pieza_fdi: int
    superficie: str | None = None
    estado: str
    fecha: datetime
    autor_usuario_id: uuid.UUID
    autor_profesional_id: uuid.UUID | None = None
    observaciones: str | None = None
    created_at: datetime | None = None


class AdjuntoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    tipo: str
    storage_key: str
    nombre_original: str
    content_type: str
    size_bytes: int
    sha256: str
    origen: str | None = None
    subido_por_usuario_id: uuid.UUID | None = None
    created_at: datetime | None = None


class SignedURLRead(BaseModel):
    url: str
    expires_at: datetime


class ConsentimientoCreate(BaseModel):
    historia_clinica_id: uuid.UUID
    tipo: str = Field(min_length=1, max_length=20)
    texto: str = Field(min_length=1)
    texto_version: str = Field(min_length=1, max_length=40)
    firmante_nombre: str = Field(min_length=1, max_length=160)
    firmante_dni: str | None = Field(default=None, max_length=20)
    plan_invasivo: bool | None = None


class ConsentimientoRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    tipo: str
    texto_version: str
    texto: str
    plan_invasivo: bool
    firmante_nombre: str
    firmante_dni: str | None = None
    firmado_at: datetime
    ip: str
    dispositivo: str
    firma_hash: str
    pdf_storage_key: str
    pdf_sha256: str
    created_by_usuario_id: uuid.UUID | None = None
    created_at: datetime | None = None
    hash_valido: bool = True


def _consentimiento_read(
    record: ConsentimientoRecord, hash_valido: bool
) -> ConsentimientoRead:
    return ConsentimientoRead(
        **asdict(record), hash_valido=hash_valido
    )


def _odontograma_read(view: OdontogramaView) -> OdontogramaRead:
    return OdontogramaRead(
        **asdict(view.odontograma),
        estado_actual=[
            EstadoPiezaRead(**asdict(estado)) for estado in view.estado_actual
        ],
    )


# --- Odontograma -----------------------------------------------------------


@router.get("/odontogramas/{historia_id}", response_model=OdontogramaRead)
async def get_odontograma(
    historia_id: uuid.UUID,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.odontogramas.obtener(principal, historia_id)
    return _odontograma_read(view)


@router.get(
    "/odontogramas/{historia_id}/eventos",
    response_model=list[EventoPiezaRead],
)
async def list_eventos(
    historia_id: uuid.UUID,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    rows = await services.odontogramas.listar_eventos(principal, historia_id)
    return [EventoPiezaRead.model_validate(row) for row in rows]


@router.post(
    "/odontogramas/{historia_id}/eventos",
    response_model=EventoPiezaRead,
    status_code=201,
)
async def create_evento(
    historia_id: uuid.UUID,
    body: EventoPiezaCreate,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    evento = await services.odontogramas.registrar_evento(
        principal,
        historia_id,
        pieza_fdi=body.pieza_fdi,
        estado=body.estado,
        superficie=body.superficie,
        fecha=body.fecha,
        observaciones=body.observaciones,
    )
    return EventoPiezaRead.model_validate(evento)


# --- Adjuntos --------------------------------------------------------------


@router.get(
    "/historias-clinicas/{historia_id}/adjuntos",
    response_model=list[AdjuntoRead],
)
async def list_adjuntos(
    historia_id: uuid.UUID,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    rows = await services.adjuntos.listar(principal, historia_id)
    return [AdjuntoRead.model_validate(row) for row in rows]


@router.post(
    "/historias-clinicas/{historia_id}/adjuntos",
    response_model=AdjuntoRead,
    status_code=201,
)
async def upload_adjunto(
    historia_id: uuid.UUID,
    tipo: str = Form(...),
    archivo: UploadFile = File(...),
    origen: str | None = Form(None),
    turno_id: str | None = Form(None),
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    if turno_id is not None:
        raise AppError(
            "los adjuntos se ligan a la historia clinica, nunca a un turno "
            "(RN-HC-05)",
            422,
        )
    data = await archivo.read(services.adjuntos.max_bytes + 1)
    record = await services.adjuntos.subir(
        principal,
        historia_id,
        tipo=tipo,
        nombre_original=archivo.filename or "archivo",
        content_type=archivo.content_type or "application/octet-stream",
        data=data,
        origen=origen,
    )
    return AdjuntoRead.model_validate(record)


@router.get("/adjuntos/{adjunto_id}/url", response_model=SignedURLRead)
async def get_adjunto_url(
    adjunto_id: uuid.UUID,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    signed = await services.adjuntos.url_firmada(principal, adjunto_id)
    return SignedURLRead(url=signed.url, expires_at=signed.expires_at)


@storage_router.get("/storage/{key:path}")
async def download_storage(
    request: Request,
    key: str,
    token: str = Query(...),
    storage: StoragePort = Depends(get_storage),
) -> Response:
    """Capability URL: the signed token replaces the JWT for this read."""
    tenant_id = storage.verify_token(key, token)
    data = await storage.get(key)
    if getattr(request.app.state, "audit_recorder", None) is not None:
        await record_tenant_event(
            tenant_id=tenant_id,
            actor_usuario_id=None,
            evento="hce_adjunto_descargado",
            recurso="adjunto",
            recurso_id=hashlib.sha256(key.encode("utf-8")).hexdigest(),
            metodo="GET",
            ruta="/api/storage/{key}",
        )
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


# --- Consentimientos -------------------------------------------------------


@router.post(
    "/consentimientos", response_model=ConsentimientoRead, status_code=201
)
async def create_consentimiento(
    body: ConsentimientoCreate,
    request: Request,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    ip = request.client.host if request.client else "desconocida"
    dispositivo = request.headers.get("user-agent", "desconocido")
    record = await services.consentimientos.crear(
        principal,
        historia_id=body.historia_clinica_id,
        tipo=body.tipo,
        texto=body.texto,
        texto_version=body.texto_version,
        firmante_nombre=body.firmante_nombre,
        firmante_dni=body.firmante_dni,
        plan_invasivo=body.plan_invasivo,
        ip=ip,
        dispositivo=dispositivo,
    )
    return _consentimiento_read(record, hash_valido=True)


@router.get(
    "/consentimientos/{consentimiento_id}",
    response_model=ConsentimientoRead,
)
async def get_consentimiento(
    consentimiento_id: uuid.UUID,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    record, valido = await services.consentimientos.obtener(
        principal, consentimiento_id
    )
    return _consentimiento_read(record, hash_valido=valido)


@router.get("/consentimientos/{consentimiento_id}/pdf")
async def get_consentimiento_pdf(
    consentimiento_id: uuid.UUID,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> RedirectResponse:
    signed = await services.consentimientos.pdf_url(
        principal, consentimiento_id
    )
    return RedirectResponse(url=signed.url, status_code=302)


@router.get(
    "/pacientes/{paciente_id}/consentimientos",
    response_model=list[ConsentimientoRead],
)
async def list_consentimientos_paciente(
    paciente_id: uuid.UUID,
    services: ClinicaServices = Depends(get_clinica_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    rows = await services.consentimientos.listar_por_paciente(
        principal, paciente_id
    )
    return [
        _consentimiento_read(
            row, hash_valido=services.consentimientos.verificar(row)
        )
        for row in rows
    ]
