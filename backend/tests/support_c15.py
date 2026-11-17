"""Shared C-15 test rig: C-14 memory stores + agenda read model + caja router."""

from __future__ import annotations

import asyncio
import datetime
import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import agenda_cobros as agenda_cobros_api
from app.api import caja as caja_api
from app.api import clinica as clinica_api
from app.api import pacientes as pacientes_api
from app.api import presupuestos as presupuestos_api
from app.api import turnos as turnos_api
from app.application.agenda_cobros import (
    AgendaCobroService,
    MemoryAgendaCobroStore,
)
from app.application.caja import CajaService, MemoryTurnoDiaStore
from app.application.pacientes import (
    HistoriaClinicaService,
    PacienteRecord,
    PacienteService,
)
from app.application.turnos import (
    MemoryBloqueoStore,
    MemoryTurnoCatalogStore,
    MemoryTurnoStore,
    PrestacionAgenda,
    ProfesionalAgenda,
    SillonAgenda,
    TurnoService,
)
from app.infrastructure.pdf import SimplePdfWriter
from app.shared.exceptions import register_exception_handlers
from tests.support_c14 import (
    TENANT_A,
    C14Stores,
    acceso_service,
    build_services,
    build_stores,
    cuenta_service,
    presupuesto_services,
    seed_paciente_historia,
)


@dataclass
class C15Stores:
    c14: C14Stores
    turnos_dia: MemoryTurnoDiaStore


def build_c15_stores() -> C15Stores:
    return C15Stores(c14=build_stores(), turnos_dia=MemoryTurnoDiaStore())


def caja_services(stores: C15Stores) -> caja_api.CajaServices:
    return caja_api.CajaServices(
        cuentas=cuenta_service(stores.c14),
        caja=CajaService(stores.c14.movimientos, stores.turnos_dia),
        pdf=SimplePdfWriter(),
    )


def build_c15_client(
    stores: C15Stores,
    who,  # type: ignore[no-untyped-def]
    *,
    agenda: MemoryAgendaCobroStore | None = None,
    turnos: turnos_api.TurnoServices | None = None,
) -> TestClient:
    """Pacientes + clinica + presupuestos + agenda + turnos + caja routers."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(pacientes_api.router, prefix="/api")
    app.include_router(clinica_api.router, prefix="/api")
    app.include_router(clinica_api.storage_router, prefix="/api")
    app.include_router(presupuestos_api.router, prefix="/api")
    app.include_router(turnos_api.router, prefix="/api")
    app.include_router(agenda_cobros_api.router, prefix="/api")
    app.include_router(caja_api.router, prefix="/api")
    acceso = acceso_service(stores.c14)
    pacientes = PacienteService(stores.c14.pacientes)
    historias = HistoriaClinicaService(
        stores.c14.historias,
        stores.c14.pacientes,
        stores.c14.evoluciones,
        stores.c14.derivaciones,
        acceso,
    )
    app.dependency_overrides[pacientes_api.get_current_principal] = lambda: who
    app.dependency_overrides[pacientes_api.get_paciente_service] = (
        lambda: pacientes
    )
    app.dependency_overrides[pacientes_api.get_historia_service] = (
        lambda: historias
    )
    app.dependency_overrides[clinica_api.get_clinica_services] = (
        lambda: build_services(stores.c14)
    )
    app.dependency_overrides[clinica_api.get_storage] = (
        lambda: stores.c14.storage
    )
    app.dependency_overrides[presupuestos_api.get_presupuesto_services] = (
        lambda: presupuesto_services(stores.c14)
    )
    agenda_store = agenda if agenda is not None else MemoryAgendaCobroStore()
    app.dependency_overrides[agenda_cobros_api.get_agenda_cobro_service] = (
        lambda: AgendaCobroService(agenda_store)
    )
    if turnos is not None:
        app.dependency_overrides[turnos_api.get_turno_services] = lambda: turnos
    app.dependency_overrides[caja_api.get_caja_services] = (
        lambda: caja_services(stores)
    )
    return TestClient(app, raise_server_exceptions=False)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def pago(
    stores: C15Stores,
    who,  # type: ignore[no-untyped-def]
    paciente_id: uuid.UUID,
    *,
    monto="15000.00",
    medio: str = "efectivo",
    idempotency_key: str | None = None,
):
    return _run(
        cuenta_service(stores.c14).registrar_pago(
            who,
            paciente_id,
            monto=monto,
            medio=medio,
            idempotency_key=idempotency_key,
        )
    )


# --- Turnos rig ------------------------------------------------------------


@dataclass
class TurnoRig:
    service: TurnoService
    turnos: MemoryTurnoStore
    catalogo: MemoryTurnoCatalogStore
    bloqueos: MemoryBloqueoStore
    prestacion: PrestacionAgenda
    profesional: ProfesionalAgenda
    sillon: SillonAgenda
    paciente: PacienteRecord


def build_turno_rig(
    stores: C15Stores,
    *,
    duracion_min: int = 30,
    buffer_min: int = 10,
    sena_obligatoria: bool = False,
    anticipacion_min_cancel_hs: int = 24,
    intervalo_control_dias: int | None = 90,
) -> TurnoRig:
    paciente, _historia = seed_paciente_historia(stores.c14)
    prestacion = PrestacionAgenda(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        nombre="Consulta Ficticia C-15",
        duracion_min=duracion_min,
        buffer_min=buffer_min,
        sena_obligatoria=sena_obligatoria,
        anticipacion_min_cancel_hs=anticipacion_min_cancel_hs,
        intervalo_control_dias=intervalo_control_dias,
    )
    profesional = ProfesionalAgenda(
        id=uuid.uuid4(), tenant_id=TENANT_A, nombre="Odontologo Ficticio C-15"
    )
    sillon = SillonAgenda(
        id=uuid.uuid4(), tenant_id=TENANT_A, nombre="Sillon Ficticio C-15"
    )
    catalogo = MemoryTurnoCatalogStore(
        prestaciones=[prestacion],
        profesionales=[profesional],
        sillones=[sillon],
    )
    turnos = MemoryTurnoStore()
    bloqueos = MemoryBloqueoStore()
    service = TurnoService(
        turnos, catalogo, bloqueos, stores.c14.pacientes
    )
    return TurnoRig(
        service=service,
        turnos=turnos,
        catalogo=catalogo,
        bloqueos=bloqueos,
        prestacion=prestacion,
        profesional=profesional,
        sillon=sillon,
        paciente=paciente,
    )


def build_turno_client(rig: TurnoRig, who) -> TestClient:  # type: ignore[no-untyped-def]
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(turnos_api.router, prefix="/api")
    app.dependency_overrides[turnos_api.get_turno_services] = (
        lambda: turnos_api.TurnoServices(turnos=rig.service)
    )
    app.dependency_overrides[turnos_api.get_current_principal] = lambda: who
    return TestClient(app, raise_server_exceptions=False)


def crear_turno(
    rig: TurnoRig,
    who,  # type: ignore[no-untyped-def]
    *,
    inicio: datetime.datetime,
    paciente_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
    sillon_id: uuid.UUID | None = None,
    prestacion_id: uuid.UUID | None = None,
    origen: str = "recepcion",
):
    return _run(
        rig.service.crear(
            who,
            paciente_id=paciente_id or rig.paciente.id,
            profesional_id=profesional_id or rig.profesional.id,
            sillon_id=sillon_id or rig.sillon.id,
            prestacion_id=prestacion_id or rig.prestacion.id,
            inicio=inicio,
            origen=origen,
        )
    )
