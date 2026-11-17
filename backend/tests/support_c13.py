"""Shared C-13 test rig: in-memory stores + real router (no Postgres)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import clinica as clinica_api
from app.api import pacientes as pacientes_api
from app.api.clinica import ClinicaServices
from app.application.auth_service import Principal
from app.application.clinica import (
    AdjuntoService,
    ConsentimientoService,
    MemoryAdjuntoStore,
    MemoryConsentimientoStore,
    MemoryEventoPiezaStore,
    MemoryOdontogramaStore,
    OdontogramaService,
)
from app.application.pacientes import (
    AccesoClinicoService,
    HistoriaClinicaService,
    MemoryAccesoClinicoStore,
    MemoryDerivacionStore,
    MemoryEvolucionStore,
    MemoryHistoriaStore,
    MemoryPacienteStore,
    PacienteService,
)
from app.infrastructure.pdf import SimplePdfWriter
from app.infrastructure.storage import InMemoryStorage, SignedURLSigner
from app.shared.exceptions import register_exception_handlers

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
TENANT_A_STR = str(TENANT_A)
STORAGE_SECRET = "fictitious-storage-secret-not-real"


@dataclass
class C13Stores:
    pacientes: MemoryPacienteStore
    historias: MemoryHistoriaStore
    evoluciones: MemoryEvolucionStore
    derivaciones: MemoryDerivacionStore
    acceso: MemoryAccesoClinicoStore
    odontogramas: MemoryOdontogramaStore
    eventos: MemoryEventoPiezaStore
    adjuntos: MemoryAdjuntoStore
    consentimientos: MemoryConsentimientoStore
    storage: InMemoryStorage


def build_stores(
    *, max_bytes: int = 1024 * 1024, ttl_seg: int = 300
) -> C13Stores:
    signer = SignedURLSigner(
        STORAGE_SECRET, ttl_seg=ttl_seg, base_url="http://testserver"
    )
    return C13Stores(
        pacientes=MemoryPacienteStore(),
        historias=MemoryHistoriaStore(),
        evoluciones=MemoryEvolucionStore(),
        derivaciones=MemoryDerivacionStore(),
        acceso=MemoryAccesoClinicoStore(),
        odontogramas=MemoryOdontogramaStore(),
        eventos=MemoryEventoPiezaStore(),
        adjuntos=MemoryAdjuntoStore(),
        consentimientos=MemoryConsentimientoStore(),
        storage=InMemoryStorage(signer),
    )


def acceso_service(stores: C13Stores) -> AccesoClinicoService:
    return AccesoClinicoService(stores.acceso, stores.derivaciones)


def build_services(
    stores: C13Stores,
    *,
    max_bytes: int = 1024 * 1024,
) -> ClinicaServices:
    acceso = acceso_service(stores)
    historias = stores.historias
    return ClinicaServices(
        odontogramas=OdontogramaService(
            stores.odontogramas, stores.eventos, historias, acceso
        ),
        adjuntos=AdjuntoService(
            stores.adjuntos,
            historias,
            acceso,
            stores.storage,
            max_bytes=max_bytes,
            mime_permitidos=(
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
            ),
        ),
        consentimientos=ConsentimientoService(
            stores.consentimientos,
            historias,
            stores.pacientes,
            acceso,
            stores.storage,
            SimplePdfWriter(),
        ),
    )


def principal(
    *,
    sub: uuid.UUID | None = None,
    tenant_id: uuid.UUID = TENANT_A,
    roles: tuple[str, ...] = ("propietario",),
    email: str = "ficticio@demo-ficticia.invalid",
) -> Principal:
    return Principal(
        sub=str(sub or uuid.uuid4()),
        tenant_id=tenant_id,
        roles=roles,
        email=email,
    )


def seed_paciente_historia(
    stores: C13Stores,
    *,
    tenant_id: uuid.UUID = TENANT_A,
    who: Principal | None = None,
    dni: str = "91000001",
    nombre: str = "Paciente Ficticio C-13",
):
    """Create a patient + history with the C-12 services (memory)."""
    owner = who or principal(tenant_id=tenant_id)
    pacientes = PacienteService(stores.pacientes)
    acceso = acceso_service(stores)
    historias = HistoriaClinicaService(
        stores.historias,
        stores.pacientes,
        stores.evoluciones,
        stores.derivaciones,
        acceso,
    )
    paciente = _run(
        pacientes.crear(
            tenant_id=tenant_id,
            nombre=nombre,
            telefono="+5491100000000",
            dni=dni,
        )
    )
    historia = _run(historias.obtener_o_crear(owner, paciente.id))
    return paciente, historia


def seed_tratante(
    stores: C13Stores,
    paciente_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID = TENANT_A,
    usuario_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
) -> tuple[Principal, uuid.UUID, uuid.UUID]:
    """Register a treating professional for a patient (turno-based access)."""
    usuario = usuario_id or uuid.uuid4()
    profesional = profesional_id or uuid.uuid4()
    stores.acceso.registrar_profesional(usuario, profesional)
    stores.acceso.registrar_turno(tenant_id, paciente_id, profesional)
    return (
        principal(sub=usuario, tenant_id=tenant_id, roles=("odontologo",)),
        usuario,
        profesional,
    )


def build_client(
    stores: C13Stores,
    who: Principal,
    *,
    max_bytes: int = 1024 * 1024,
) -> TestClient:
    """Real clinica router over memory stores, principal overridden."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(clinica_api.router, prefix="/api")
    app.include_router(clinica_api.storage_router, prefix="/api")
    services = build_services(stores, max_bytes=max_bytes)
    app.dependency_overrides[clinica_api.get_current_principal] = lambda: who
    app.dependency_overrides[clinica_api.get_clinica_services] = lambda: services
    app.dependency_overrides[clinica_api.get_storage] = lambda: stores.storage
    return TestClient(app, raise_server_exceptions=False)


def build_full_client(
    stores: C13Stores,
    who: Principal,
    *,
    max_bytes: int = 1024 * 1024,
) -> TestClient:
    """Pacientes + clinica routers over the same memory stores (E2E Flujo 3)."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(pacientes_api.router, prefix="/api")
    app.include_router(clinica_api.router, prefix="/api")
    app.include_router(clinica_api.storage_router, prefix="/api")
    acceso = acceso_service(stores)
    pacientes = PacienteService(stores.pacientes)
    historias = HistoriaClinicaService(
        stores.historias,
        stores.pacientes,
        stores.evoluciones,
        stores.derivaciones,
        acceso,
    )
    services = build_services(stores, max_bytes=max_bytes)
    app.dependency_overrides[pacientes_api.get_current_principal] = lambda: who
    app.dependency_overrides[pacientes_api.get_paciente_service] = (
        lambda: pacientes
    )
    app.dependency_overrides[pacientes_api.get_historia_service] = (
        lambda: historias
    )
    app.dependency_overrides[clinica_api.get_clinica_services] = lambda: services
    app.dependency_overrides[clinica_api.get_storage] = lambda: stores.storage
    return TestClient(app, raise_server_exceptions=False)



def _now() -> datetime:
    return datetime.now(UTC)


def _run(coro):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(coro)
