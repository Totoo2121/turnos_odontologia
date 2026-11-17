"""C-14 presupuestos, planes de tratamiento y cuenta corriente API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.clinica import get_storage
from app.api.audit import audit_sensitive_request
from app.api.deps import get_current_principal, require_any, tenant_session
from app.application.auth_service import Principal
from app.application.clinica import (
    ConsentimientoService,
    DbConsentimientoStore,
)
from app.application.cuenta_corriente import (
    CuentaCorrienteService,
    DbCuentaCorrienteStore,
    DbMovimientoCCStore,
)
from app.application.pacientes import (
    AccesoClinicoService,
    DbAccesoClinicoStore,
    DbDerivacionStore,
    DbHistoriaStore,
    DbPacienteStore,
)
from app.application.presupuestos import (
    AceptacionView,
    DbPlanTratamientoStore,
    DbPrestacionReader,
    DbPresupuestoItemStore,
    DbPresupuestoStore,
    ItemInput,
    PlanEtapaView,
    PlanTratamientoView,
    PresupuestoItemRecord,
    PresupuestoService,
    PresupuestoView,
)
from app.infrastructure.pdf import SimplePdfWriter
from app.shared.settings import get_settings

__all__ = ["router", "get_presupuesto_services"]

CLINICAL_GUARD = require_any("propietario", "odontologo")

router = APIRouter(tags=["presupuestos"], dependencies=[Depends(audit_sensitive_request)])


@dataclass(frozen=True)
class PresupuestoServices:
    presupuestos: PresupuestoService
    cuentas: CuentaCorrienteService


async def get_presupuesto_services(
    session: Any = Depends(tenant_session),  # type: ignore[no-untyped-def]
    principal: Principal = Depends(get_current_principal),
) -> PresupuestoServices:
    """Production services pinned to the JWT tenant (D11/D14)."""
    tenant = principal.tenant_id
    settings = get_settings()
    historias = DbHistoriaStore(session, tenant)
    pacientes = DbPacienteStore(session, tenant)
    derivaciones = DbDerivacionStore(session, tenant)
    acceso = AccesoClinicoService(
        DbAccesoClinicoStore(session, tenant), derivaciones
    )
    cuentas = CuentaCorrienteService(
        DbCuentaCorrienteStore(session, tenant),
        DbMovimientoCCStore(session, tenant),
        pacientes,
    )
    consentimientos = ConsentimientoService(
        DbConsentimientoStore(session, tenant),
        historias,
        pacientes,
        acceso,
        get_storage(),
        SimplePdfWriter(),
    )
    presupuestos = PresupuestoService(
        DbPresupuestoStore(session, tenant),
        DbPresupuestoItemStore(session, tenant),
        DbPlanTratamientoStore(session, tenant),
        DbPrestacionReader(session, tenant),
        historias,
        pacientes,
        acceso,
        cuentas,
        consentimientos,
        validez_dias=settings.presupuesto_validez_dias,
    )
    return PresupuestoServices(
        presupuestos=presupuestos, cuentas=cuentas
    )


# --- Schemas ---------------------------------------------------------------


class PresupuestoItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prestacion_id: uuid.UUID
    cantidad: int = Field(default=1, ge=1, le=999)
    precio_unitario: Decimal | None = Field(default=None, ge=0)
    descripcion: str | None = Field(default=None, max_length=200)
    pieza_fdi: int | None = Field(default=None, ge=11, le=48)
    superficie: str | None = Field(default=None, max_length=16)
    etapa: int = Field(default=1, ge=1, le=20)


class PresupuestoItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cantidad: int | None = Field(default=None, ge=1, le=999)
    precio_unitario: Decimal | None = Field(default=None, ge=0)
    descripcion: str | None = Field(default=None, max_length=200)
    pieza_fdi: int | None = Field(default=None, ge=11, le=48)
    superficie: str | None = Field(default=None, max_length=16)
    etapa: int | None = Field(default=None, ge=1, le=20)


class PresupuestoItemRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    presupuesto_id: uuid.UUID
    prestacion_id: uuid.UUID
    descripcion: str
    cantidad: int
    precio_unitario: Decimal
    importe: Decimal
    etapa: int
    requiere_consentimiento: bool
    pieza_fdi: int | None = None
    superficie: str | None = None
    created_at: datetime | None = None


class PresupuestoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    historia_clinica_id: uuid.UUID | None = None
    validez_hasta: date | None = None
    observaciones: str | None = Field(default=None, max_length=2000)
    items: list[PresupuestoItemCreate] = Field(default_factory=list)


class PresupuestoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validez_hasta: date | None = None
    observaciones: str | None = Field(default=None, max_length=2000)


class PresupuestoRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    paciente_id: uuid.UUID
    historia_clinica_id: uuid.UUID
    creado_por_usuario_id: uuid.UUID
    estado: str
    moneda: str
    total: Decimal
    validez_hasta: date | None = None
    enviado_at: datetime | None = None
    aceptado_at: datetime | None = None
    rechazado_at: datetime | None = None
    observaciones: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    items: list[PresupuestoItemRead] = Field(default_factory=list)


class AceptacionRead(PresupuestoRead):
    plan_id: uuid.UUID | None = None
    movimiento_id: uuid.UUID | None = None


class PlanEtapaRead(BaseModel):
    etapa: int
    subtotal: Decimal
    items: list[PresupuestoItemRead]


class PlanTratamientoRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    presupuesto_id: uuid.UUID
    paciente_id: uuid.UUID
    consentimiento_id: uuid.UUID | None = None
    estado: str
    total: Decimal
    etapas: int
    etapa_actual: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    detalle: list[PlanEtapaRead] = Field(default_factory=list)


class MovimientoCCRead(BaseModel):
    id: uuid.UUID
    tipo: str
    monto: Decimal
    descripcion: str
    referencia: str | None = None
    plan_tratamiento_id: uuid.UUID | None = None
    ocurrido_at: datetime | None = None
    created_at: datetime | None = None


class CuentaCorrienteRead(BaseModel):
    paciente_id: uuid.UUID
    moneda: str
    saldo: Decimal
    movimientos: list[MovimientoCCRead] = Field(default_factory=list)


# --- Mapping helpers -------------------------------------------------------


def _item_read(item: PresupuestoItemRecord) -> PresupuestoItemRead:
    return PresupuestoItemRead(
        id=item.id,
        tenant_id=item.tenant_id,
        presupuesto_id=item.presupuesto_id,
        prestacion_id=item.prestacion_id,
        descripcion=item.descripcion,
        cantidad=item.cantidad,
        precio_unitario=item.precio_unitario,
        importe=item.importe,
        etapa=item.etapa,
        requiere_consentimiento=item.requiere_consentimiento,
        pieza_fdi=item.pieza_fdi,
        superficie=item.superficie,
        created_at=item.created_at,
    )


def _presupuesto_read(view: PresupuestoView) -> PresupuestoRead:
    record = view.presupuesto
    return PresupuestoRead(
        id=record.id,
        tenant_id=record.tenant_id,
        paciente_id=record.paciente_id,
        historia_clinica_id=record.historia_clinica_id,
        creado_por_usuario_id=record.creado_por_usuario_id,
        estado=record.estado,
        moneda=record.moneda,
        total=record.total,
        validez_hasta=record.validez_hasta,
        enviado_at=record.enviado_at,
        aceptado_at=record.aceptado_at,
        rechazado_at=record.rechazado_at,
        observaciones=record.observaciones,
        created_at=record.created_at,
        updated_at=record.updated_at,
        items=[_item_read(item) for item in view.items],
    )


def _aceptacion_read(view: AceptacionView) -> AceptacionRead:
    base = _presupuesto_read(
        PresupuestoView(presupuesto=view.presupuesto, items=view.items)
    )
    return AceptacionRead(
        **base.model_dump(),
        plan_id=view.plan.id,
        movimiento_id=view.movimiento.id if view.movimiento else None,
    )


def _etapa_read(etapa: PlanEtapaView) -> PlanEtapaRead:
    return PlanEtapaRead(
        etapa=etapa.etapa,
        subtotal=etapa.subtotal,
        items=[_item_read(item) for item in etapa.items],
    )


def _plan_read(view: PlanTratamientoView) -> PlanTratamientoRead:
    plan = view.plan
    return PlanTratamientoRead(
        id=plan.id,
        tenant_id=plan.tenant_id,
        presupuesto_id=plan.presupuesto_id,
        paciente_id=plan.paciente_id,
        consentimiento_id=plan.consentimiento_id,
        estado=plan.estado,
        total=plan.total,
        etapas=plan.etapas,
        etapa_actual=plan.etapa_actual,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        detalle=[_etapa_read(etapa) for etapa in view.etapas],
    )


def _item_input(body: PresupuestoItemCreate) -> ItemInput:
    return ItemInput(
        prestacion_id=body.prestacion_id,
        cantidad=body.cantidad,
        precio_unitario=body.precio_unitario,
        descripcion=body.descripcion,
        pieza_fdi=body.pieza_fdi,
        superficie=body.superficie,
        etapa=body.etapa,
    )


# --- Presupuestos ----------------------------------------------------------


@router.post(
    "/presupuestos", response_model=PresupuestoRead, status_code=201
)
async def create_presupuesto(
    body: PresupuestoCreate,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.crear(
        principal,
        paciente_id=body.paciente_id,
        historia_clinica_id=body.historia_clinica_id,
        validez_hasta=body.validez_hasta,
        observaciones=body.observaciones,
        items=[_item_input(item) for item in body.items],
    )
    return _presupuesto_read(view)


@router.get("/presupuestos", response_model=list[PresupuestoRead])
async def list_presupuestos(
    paciente_id: uuid.UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    views = await services.presupuestos.listar(
        principal,
        paciente_id=paciente_id,
        estado=estado,
        limit=limit,
        offset=offset,
    )
    return [_presupuesto_read(view) for view in views]


@router.get(
    "/presupuestos/{presupuesto_id}", response_model=PresupuestoRead
)
async def get_presupuesto(
    presupuesto_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.obtener(principal, presupuesto_id)
    return _presupuesto_read(view)


@router.patch(
    "/presupuestos/{presupuesto_id}", response_model=PresupuestoRead
)
async def update_presupuesto(
    presupuesto_id: uuid.UUID,
    body: PresupuestoUpdate,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    data = body.model_dump(exclude_unset=True)
    kwargs: dict[str, Any] = {}
    if "validez_hasta" in data:
        kwargs["validez_hasta"] = data["validez_hasta"]
    if "observaciones" in data:
        kwargs["observaciones"] = data["observaciones"]
    view = await services.presupuestos.editar(
        principal, presupuesto_id, **kwargs
    )
    return _presupuesto_read(view)


@router.delete("/presupuestos/{presupuesto_id}", status_code=204)
async def delete_presupuesto(
    presupuesto_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Response:
    await services.presupuestos.eliminar(principal, presupuesto_id)
    return Response(status_code=204)


# --- Items -----------------------------------------------------------------


@router.post(
    "/presupuestos/{presupuesto_id}/items",
    response_model=PresupuestoRead,
    status_code=201,
)
async def create_item(
    presupuesto_id: uuid.UUID,
    body: PresupuestoItemCreate,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.agregar_item(
        principal, presupuesto_id, _item_input(body)
    )
    return _presupuesto_read(view)


@router.patch(
    "/presupuestos/{presupuesto_id}/items/{item_id}",
    response_model=PresupuestoRead,
)
async def update_item(
    presupuesto_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PresupuestoItemUpdate,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    data = body.model_dump(exclude_unset=True)
    kwargs: dict[str, Any] = {}
    for field in ("cantidad", "precio_unitario", "descripcion", "etapa"):
        if field in data:
            kwargs[field] = data[field]
    if "pieza_fdi" in data:
        kwargs["pieza_fdi"] = data["pieza_fdi"]
    if "superficie" in data:
        kwargs["superficie"] = data["superficie"]
    view = await services.presupuestos.editar_item(
        principal, presupuesto_id, item_id, **kwargs
    )
    return _presupuesto_read(view)


@router.delete(
    "/presupuestos/{presupuesto_id}/items/{item_id}",
    response_model=PresupuestoRead,
)
async def delete_item(
    presupuesto_id: uuid.UUID,
    item_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.quitar_item(
        principal, presupuesto_id, item_id
    )
    return _presupuesto_read(view)


# --- Transitions -----------------------------------------------------------


@router.post(
    "/presupuestos/{presupuesto_id}/enviar",
    response_model=PresupuestoRead,
)
async def enviar_presupuesto(
    presupuesto_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.enviar(principal, presupuesto_id)
    return _presupuesto_read(view)


@router.post(
    "/presupuestos/{presupuesto_id}/aceptar",
    response_model=AceptacionRead,
)
async def aceptar_presupuesto(
    presupuesto_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.aceptar(principal, presupuesto_id)
    return _aceptacion_read(view)


@router.post(
    "/presupuestos/{presupuesto_id}/rechazar",
    response_model=PresupuestoRead,
)
async def rechazar_presupuesto(
    presupuesto_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.rechazar(principal, presupuesto_id)
    return _presupuesto_read(view)


# --- Planes ----------------------------------------------------------------


@router.get(
    "/planes-tratamiento", response_model=list[PlanTratamientoRead]
)
async def list_planes(
    paciente_id: uuid.UUID = Query(...),
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    views = await services.presupuestos.listar_planes(
        principal, paciente_id=paciente_id
    )
    return [_plan_read(view) for view in views]


@router.get(
    "/planes-tratamiento/{plan_id}", response_model=PlanTratamientoRead
)
async def get_plan(
    plan_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(CLINICAL_GUARD),
) -> Any:
    view = await services.presupuestos.obtener_plan(principal, plan_id)
    return _plan_read(view)


# --- Cuenta corriente ------------------------------------------------------


@router.get(
    "/pacientes/{paciente_id}/cuenta-corriente",
    response_model=CuentaCorrienteRead,
)
async def get_cuenta_corriente(
    paciente_id: uuid.UUID,
    services: PresupuestoServices = Depends(get_presupuesto_services),
    principal: Principal = Depends(get_current_principal),
) -> Any:
    view = await services.cuentas.obtener(principal, paciente_id)
    return CuentaCorrienteRead(
        paciente_id=view.paciente_id,
        moneda=view.moneda,
        saldo=view.saldo,
        movimientos=[
            MovimientoCCRead(
                id=mov.id,
                tipo=mov.tipo,
                monto=mov.monto,
                descripcion=mov.descripcion,
                referencia=mov.referencia,
                plan_tratamiento_id=mov.plan_tratamiento_id,
                ocurrido_at=mov.ocurrido_at,
                created_at=mov.created_at,
            )
            for mov in view.movimientos
        ],
    )
