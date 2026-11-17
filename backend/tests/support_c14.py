"""Shared C-14 test rig: in-memory stores + real routers (no Postgres)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import clinica as clinica_api
from app.api import pacientes as pacientes_api
from app.api import presupuestos as presupuestos_api
from app.api.clinica import ClinicaServices
from app.api.presupuestos import PresupuestoServices
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
from app.application.cuenta_corriente import (
    CuentaCorrienteService,
    MemoryCuentaCorrienteStore,
    MemoryMovimientoCCStore,
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
from app.application.presupuestos import (
    ItemInput,
    MemoryPlanTratamientoStore,
    MemoryPrestacionReader,
    MemoryPresupuestoItemStore,
    MemoryPresupuestoStore,
    PrestacionSnapshot,
    PresupuestoService,
)
from app.infrastructure.pdf import SimplePdfWriter
from app.infrastructure.storage import InMemoryStorage, SignedURLSigner
from app.shared.exceptions import register_exception_handlers

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
TENANT_A_STR = str(TENANT_A)
TENANT_B_STR = str(TENANT_B)
STORAGE_SECRET = "fictitious-storage-secret-not-real"


@dataclass
class C14Stores:
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
    presupuestos: MemoryPresupuestoStore
    items: MemoryPresupuestoItemStore
    planes: MemoryPlanTratamientoStore
    prestaciones: MemoryPrestacionReader
    cuentas: MemoryCuentaCorrienteStore
    movimientos: MemoryMovimientoCCStore


def build_stores(*, ttl_seg: int = 300) -> C14Stores:
    signer = SignedURLSigner(
        STORAGE_SECRET, ttl_seg=ttl_seg, base_url="http://testserver"
    )
    return C14Stores(
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
        presupuestos=MemoryPresupuestoStore(),
        items=MemoryPresupuestoItemStore(),
        planes=MemoryPlanTratamientoStore(),
        prestaciones=MemoryPrestacionReader(),
        cuentas=MemoryCuentaCorrienteStore(),
        movimientos=MemoryMovimientoCCStore(),
    )


def acceso_service(stores: C14Stores) -> AccesoClinicoService:
    return AccesoClinicoService(stores.acceso, stores.derivaciones)


def consentimientos_service(stores: C14Stores) -> ConsentimientoService:
    return ConsentimientoService(
        stores.consentimientos,
        stores.historias,
        stores.pacientes,
        acceso_service(stores),
        stores.storage,
        SimplePdfWriter(),
    )


def cuenta_service(stores: C14Stores) -> CuentaCorrienteService:
    return CuentaCorrienteService(
        stores.cuentas, stores.movimientos, stores.pacientes
    )


def presupuestos_service(stores: C14Stores) -> PresupuestoService:
    return PresupuestoService(
        stores.presupuestos,
        stores.items,
        stores.planes,
        stores.prestaciones,
        stores.historias,
        stores.pacientes,
        acceso_service(stores),
        cuenta_service(stores),
        consentimientos_service(stores),
        validez_dias=30,
    )


def presupuesto_services(stores: C14Stores) -> PresupuestoServices:
    return PresupuestoServices(
        presupuestos=presupuestos_service(stores),
        cuentas=cuenta_service(stores),
    )


def build_services(stores: C14Stores) -> ClinicaServices:
    acceso = acceso_service(stores)
    return ClinicaServices(
        odontogramas=OdontogramaService(
            stores.odontogramas, stores.eventos, stores.historias, acceso
        ),
        adjuntos=AdjuntoService(
            stores.adjuntos,
            stores.historias,
            acceso,
            stores.storage,
            max_bytes=1024 * 1024,
            mime_permitidos=(
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
            ),
        ),
        consentimientos=consentimientos_service(stores),
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
    stores: C14Stores,
    *,
    tenant_id: uuid.UUID = TENANT_A,
    who: Principal | None = None,
    dni: str = "91000014",
    nombre: str = "Paciente Ficticio C-14",
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
            telefono="+5491100000014",
            dni=dni,
        )
    )
    historia = _run(historias.obtener_o_crear(owner, paciente.id))
    return paciente, historia


def seed_tratante(
    stores: C14Stores,
    paciente_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID = TENANT_A,
    usuario_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
) -> tuple[Principal, uuid.UUID, uuid.UUID]:
    usuario = usuario_id or uuid.uuid4()
    profesional = profesional_id or uuid.uuid4()
    stores.acceso.registrar_profesional(usuario, profesional)
    stores.acceso.registrar_turno(tenant_id, paciente_id, profesional)
    return (
        principal(sub=usuario, tenant_id=tenant_id, roles=("odontologo",)),
        usuario,
        profesional,
    )


def seed_prestacion(
    stores: C14Stores,
    *,
    nombre: str = "Consulta ficticia",
    precio: Decimal | str | None = Decimal("15000.50"),
    requiere_consentimiento: bool = False,
    prestacion_id: uuid.UUID | None = None,
) -> PrestacionSnapshot:
    snapshot = PrestacionSnapshot(
        id=prestacion_id or uuid.uuid4(),
        nombre=nombre,
        precio=(
            None if precio is None else Decimal(str(precio))
        ),
        requiere_consentimiento=requiere_consentimiento,
    )
    stores.prestaciones.add(snapshot)
    return snapshot


def item_input(
    prestacion_id: uuid.UUID,
    *,
    cantidad: int = 1,
    precio_unitario: Decimal | str | None = None,
    pieza_fdi: int | None = None,
    superficie: str | None = None,
    etapa: int = 1,
    descripcion: str | None = None,
) -> ItemInput:
    return ItemInput(
        prestacion_id=prestacion_id,
        cantidad=cantidad,
        precio_unitario=(
            None
            if precio_unitario is None
            else Decimal(str(precio_unitario))
        ),
        descripcion=descripcion,
        pieza_fdi=pieza_fdi,
        superficie=superficie,
        etapa=etapa,
    )


def crear_presupuesto(
    stores: C14Stores,
    who: Principal,
    *,
    paciente_id: uuid.UUID,
    historia_id: uuid.UUID | None = None,
    items: list[ItemInput] | None = None,
    validez_hasta: date | None = None,
):
    """Async helper wrapped for tests: returns the created PresupuestoView."""
    service = presupuestos_service(stores)
    return _run(
        service.crear(
            who,
            paciente_id=paciente_id,
            historia_clinica_id=historia_id,
            items=items or [],
            validez_hasta=validez_hasta,
        )
    )


def firmar_consentimiento(
    stores: C14Stores,
    who: Principal,
    *,
    historia_id: uuid.UUID,
    plan_invasivo: bool = True,
):
    """Sign an invasive consent through the C-13 service (memory)."""
    service = consentimientos_service(stores)
    return _run(
        service.crear(
            who,
            historia_id=historia_id,
            tipo="invasivo",
            texto="Texto ficticio de consentimiento para pruebas C-14.",
            texto_version="c14-test-1",
            firmante_nombre="Firmante Ficticio",
            firmante_dni="90000014",
            plan_invasivo=plan_invasivo,
            ip="127.0.0.1",
            dispositivo="pytest-ficticio",
        )
    )


def default_validez(days: int = 30) -> date:
    return date.today() + timedelta(days=days)


def build_full_client(stores: C14Stores, who: Principal) -> TestClient:
    """Pacientes + clinica + presupuestos routers over shared memory stores."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(pacientes_api.router, prefix="/api")
    app.include_router(clinica_api.router, prefix="/api")
    app.include_router(clinica_api.storage_router, prefix="/api")
    app.include_router(presupuestos_api.router, prefix="/api")
    acceso = acceso_service(stores)
    pacientes = PacienteService(stores.pacientes)
    historias = HistoriaClinicaService(
        stores.historias,
        stores.pacientes,
        stores.evoluciones,
        stores.derivaciones,
        acceso,
    )
    app.dependency_overrides[pacientes_api.get_current_principal] = (
        lambda: who
    )
    app.dependency_overrides[pacientes_api.get_paciente_service] = (
        lambda: pacientes
    )
    app.dependency_overrides[pacientes_api.get_historia_service] = (
        lambda: historias
    )
    app.dependency_overrides[clinica_api.get_clinica_services] = (
        lambda: build_services(stores)
    )
    app.dependency_overrides[clinica_api.get_storage] = (
        lambda: stores.storage
    )
    app.dependency_overrides[presupuestos_api.get_presupuesto_services] = (
        lambda: presupuesto_services(stores)
    )
    return TestClient(app, raise_server_exceptions=False)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _now() -> datetime:
    return datetime.now(UTC)
