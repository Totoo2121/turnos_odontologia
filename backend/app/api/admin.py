"""C-17 owner-only audit and tenant export endpoints."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.audit import audit_sensitive_request
from app.api.deps import require_role, tenant_session
from app.application.auth_service import Principal
from app.domain.admin.models import AuditEvento, Exportacion
from app.domain.models import Rol, Tenant, UserRol, Usuario
from app.infrastructure.security import hash_password
from app.infrastructure.storage import build_storage
from app.shared.db import get_session_factory
from app.shared.exceptions import AppError

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(audit_sensitive_request)]
)
OWNER = require_role("propietario")


class ExportacionRead(BaseModel):
    id: uuid.UUID
    estado: str
    solicitada_at: dt.datetime
    generada_at: dt.datetime | None
    vence_at: dt.datetime | None


class AuditEventoRead(BaseModel):
    id: uuid.UUID
    actor_usuario_id: uuid.UUID | None
    evento: str
    recurso: str
    recurso_id: str | None
    metodo: str
    ruta: str
    detalles: dict[str, Any] | None
    created_at: dt.datetime


class PerfilAdminRead(BaseModel):
    id: uuid.UUID
    nombre: str
    slug_reserva: str
    moneda: str


class PerfilAdminUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    moneda: str = Field(pattern="^ARS$")

    @field_validator("nombre")
    @classmethod
    def nombre_sin_espacios_externos(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("el nombre debe tener al menos 2 caracteres")
        return value


class UsuarioAdminCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    nombre: str = Field(min_length=2, max_length=160)
    password_inicial: str = Field(min_length=10, max_length=256)
    rol: str = Field(pattern="^(odontologo|recepcion|asistente)$")

    @field_validator("nombre")
    @classmethod
    def nombre_sin_espacios_externos(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("el nombre debe tener al menos 2 caracteres")
        return value

    @field_validator("email")
    @classmethod
    def email_valido(cls, value: str) -> str:
        value = value.strip().lower()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
            raise ValueError("email inválido")
        return value


class UsuarioAdminRead(BaseModel):
    id: uuid.UUID
    email: str
    nombre: str | None
    rol: str
    activo: bool
    created_at: dt.datetime


@router.get("/perfil", response_model=PerfilAdminRead)
async def obtener_perfil(
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> PerfilAdminRead:
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == principal.tenant_id)
    )
    if tenant is None:
        raise AppError("not found", 404)
    return PerfilAdminRead.model_validate(tenant, from_attributes=True)


@router.patch("/perfil", response_model=PerfilAdminRead)
async def actualizar_perfil(
    body: PerfilAdminUpdate,
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> PerfilAdminRead:
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == principal.tenant_id)
    )
    if tenant is None:
        raise AppError("not found", 404)
    tenant.nombre = body.nombre
    tenant.moneda = body.moneda
    await session.commit()
    await session.refresh(tenant)
    return PerfilAdminRead.model_validate(tenant, from_attributes=True)


@router.get("/usuarios", response_model=list[UsuarioAdminRead])
async def listar_usuarios(
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> list[UsuarioAdminRead]:
    rows = (
        await session.execute(
            select(Usuario, Rol.nombre)
            .join(UserRol, UserRol.usuario_id == Usuario.id)
            .join(Rol, Rol.id == UserRol.rol_id)
            .where(
                Usuario.tenant_id == principal.tenant_id,
                UserRol.tenant_id == principal.tenant_id,
            )
            .order_by(Usuario.email, Rol.nombre)
        )
    ).all()
    return [
        UsuarioAdminRead(
            id=user.id,
            email=user.email,
            nombre=user.nombre,
            rol=role,
            activo=user.is_active,
            created_at=user.created_at,
        )
        for user, role in rows
    ]


@router.post("/usuarios", response_model=UsuarioAdminRead, status_code=201)
async def crear_usuario(
    body: UsuarioAdminCreate,
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> UsuarioAdminRead:
    role = await session.scalar(select(Rol).where(Rol.nombre == body.rol))
    if role is None:
        raise AppError("rol no disponible", 409)
    user = Usuario(
        tenant_id=principal.tenant_id,
        email=str(body.email).strip().lower(),
        nombre=body.nombre,
        password_hash=hash_password(body.password_inicial),
    )
    session.add(user)
    try:
        await session.flush()
        session.add(
            UserRol(tenant_id=principal.tenant_id, usuario_id=user.id, rol_id=role.id)
        )
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise AppError(
            "ya existe un usuario con ese email en esta clínica", 409
        ) from None
    return UsuarioAdminRead(
        id=user.id,
        email=user.email,
        nombre=user.nombre,
        rol=body.rol,
        activo=user.is_active,
        created_at=user.created_at,
    )


def _job_read(job: Exportacion) -> ExportacionRead:
    return ExportacionRead(
        id=job.id,
        estado=job.estado,
        solicitada_at=job.solicitada_at,
        generada_at=job.generada_at,
        vence_at=job.vence_at,
    )


@router.get("/exportaciones", response_model=list[ExportacionRead])
async def listar_exportaciones(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> list[ExportacionRead]:
    jobs = (
        await session.scalars(
            select(Exportacion)
            .where(Exportacion.tenant_id == principal.tenant_id)
            .order_by(Exportacion.solicitada_at.desc())
            .limit(limit)
        )
    ).all()
    return [_job_read(job) for job in jobs]


@router.post("/exportacion", response_model=ExportacionRead, status_code=202)
async def solicitar_exportacion(
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> ExportacionRead:
    try:
        requester_id = uuid.UUID(principal.sub)
    except ValueError:
        raise AppError("identidad inválida", 401) from None
    job = Exportacion(
        tenant_id=principal.tenant_id,
        solicitada_por_usuario_id=requester_id,
        estado="pendiente",
    )
    session.add(job)
    await session.flush()
    job_id = job.id
    await session.commit()
    try:
        from app.worker.tasks import generar_exportacion_job

        generar_exportacion_job.delay(str(job_id), str(principal.tenant_id))
    except Exception:
        factory = get_session_factory()
        async with factory() as fallback:
            async with fallback.begin():
                await fallback.execute(
                    text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                    {"tenant_id": str(principal.tenant_id)},
                )
                failed = await fallback.scalar(
                    select(Exportacion).where(
                        Exportacion.id == job_id,
                        Exportacion.tenant_id == principal.tenant_id,
                    )
                )
                if failed is not None:
                    failed.estado, failed.error_code = "fallida", "worker_no_disponible"
        raise AppError("servicio de exportación no disponible", 503) from None
    return _job_read(job)


@router.get("/exportacion/{exportacion_id}", response_model=ExportacionRead)
async def estado_exportacion(
    exportacion_id: uuid.UUID,
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> ExportacionRead:
    job = await session.scalar(
        select(Exportacion).where(
            Exportacion.id == exportacion_id,
            Exportacion.tenant_id == principal.tenant_id,
        )
    )
    if job is None:
        raise AppError("not found", 404)
    return _job_read(job)


@router.get("/exportacion/{exportacion_id}/descargar")
async def descargar_exportacion(
    exportacion_id: uuid.UUID,
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> Response:
    job = await session.scalar(
        select(Exportacion).where(
            Exportacion.id == exportacion_id,
            Exportacion.tenant_id == principal.tenant_id,
        )
    )
    if job is None:
        raise AppError("not found", 404)
    now = dt.datetime.now(dt.UTC)
    if job.estado != "lista" or not job.storage_key or not job.vence_at:
        raise AppError("exportación todavía no disponible", 409)
    if job.vence_at <= now:
        await _expire_job(session, job)
        raise AppError("exportación vencida", 410)
    key = job.storage_key
    archive = await build_storage().get(key)
    await build_storage().delete(key)
    job.estado, job.storage_key = "vencida", None
    session.add(
        AuditEvento(
            tenant_id=principal.tenant_id,
            actor_usuario_id=uuid.UUID(principal.sub),
            evento="exportacion_descargada",
            recurso="exportacion",
            recurso_id=str(exportacion_id),
            metodo="GET",
            ruta="/api/admin/exportacion/{id}/descargar",
        )
    )
    await session.commit()
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="exportacion-{exportacion_id}.zip"'
            )
        },
    )


async def _expire_job(session: AsyncSession, job: Exportacion) -> None:
    if job.storage_key:
        await build_storage().delete(job.storage_key)
    job.estado, job.storage_key = "vencida", None
    await session.commit()


@router.get("/auditoria", response_model=list[AuditEventoRead])
async def listar_auditoria(
    desde: dt.datetime | None = Query(None),
    hasta: dt.datetime | None = Query(None),
    evento: str | None = Query(None, max_length=64),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
    session: AsyncSession = Depends(tenant_session),
    principal: Principal = Depends(OWNER),
) -> list[AuditEventoRead]:
    stmt = select(AuditEvento).where(AuditEvento.tenant_id == principal.tenant_id)
    if desde is not None:
        stmt = stmt.where(AuditEvento.created_at >= desde)
    if hasta is not None:
        stmt = stmt.where(AuditEvento.created_at < hasta)
    if evento:
        stmt = stmt.where(AuditEvento.evento == evento)
    rows = (
        await session.scalars(
            stmt.order_by(AuditEvento.created_at.desc(), AuditEvento.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [AuditEventoRead.model_validate(row, from_attributes=True) for row in rows]
