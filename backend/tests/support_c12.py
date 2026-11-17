"""Shared C-12 test rig: in-memory stores + real router (no Postgres)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import pacientes as pacientes_api
from app.application.auth_service import Principal
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
from app.shared.exceptions import register_exception_handlers

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


@dataclass
class C12Stores:
    pacientes: MemoryPacienteStore
    historias: MemoryHistoriaStore
    evoluciones: MemoryEvolucionStore
    derivaciones: MemoryDerivacionStore
    acceso: MemoryAccesoClinicoStore


def build_stores() -> C12Stores:
    return C12Stores(
        pacientes=MemoryPacienteStore(),
        historias=MemoryHistoriaStore(),
        evoluciones=MemoryEvolucionStore(),
        derivaciones=MemoryDerivacionStore(),
        acceso=MemoryAccesoClinicoStore(),
    )


def build_services(
    stores: C12Stores,
) -> tuple[PacienteService, HistoriaClinicaService, AccesoClinicoService]:
    acceso = AccesoClinicoService(stores.acceso, stores.derivaciones)
    pacientes = PacienteService(stores.pacientes)
    historias = HistoriaClinicaService(
        stores.historias,
        stores.pacientes,
        stores.evoluciones,
        stores.derivaciones,
        acceso,
    )
    return pacientes, historias, acceso


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


def build_client(
    stores: C12Stores,
    who: Principal,
) -> TestClient:
    """Real pacientes router over memory stores, principal overridden."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(pacientes_api.router, prefix="/api")
    pacientes_service, historia_service, _acceso = build_services(stores)
    app.dependency_overrides[pacientes_api.get_current_principal] = (
        lambda: who
    )
    app.dependency_overrides[pacientes_api.get_paciente_service] = (
        lambda: pacientes_service
    )
    app.dependency_overrides[pacientes_api.get_historia_service] = (
        lambda: historia_service
    )
    return TestClient(app, raise_server_exceptions=False)
