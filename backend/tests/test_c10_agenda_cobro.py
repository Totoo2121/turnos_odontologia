"""C-10 task 5.1: estado de cobro en agenda + reporte de señas pendientes.

Strict TDD — RED first.

Cubre:
- Proyección aplicación: la agenda expone el estado de cobro MP del turno
  (pendiente/acreditado/vencido/rechazado, o ``sin-sena`` si no hay orden).
- Reporte de señas pendientes: solo órdenes sin acreditar, con datos del turno.
- Endpoints HTTP: ``GET /api/turnos/agenda`` incluye ``cobro``;
  ``GET /api/reportes/senias-pendientes`` lista las señas pendientes.
- Scoping tenant en el store DB (compiled SQL, sin live DB).
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import agenda_cobros as api_module
from app.application.agenda_cobros import (
    AGENDA_TZ,
    ESTADO_COBRO_SIN_SENA,
    AgendaCobroService,
    AgendaTurno,
    DbAgendaCobroStore,
    MemoryAgendaCobroStore,
    rango_agenda,
)
from app.application.auth_service import Principal
from app.application.cobros import (
    ESTADO_COBRO_ACREDITADO,
    ESTADO_COBRO_PENDIENTE,
    ESTADO_COBRO_RECHAZADO,
    ESTADO_COBRO_VENCIDO,
    PagoRecord,
)
from app.infrastructure.repository import TenantScopeError
from app.shared.exceptions import register_exception_handlers

TENANT = uuid.uuid4()
FECHA = date(2026, 11, 13)
PROF = uuid.uuid4()
SILLON = uuid.uuid4()


def _inicio(dia: date = FECHA, hora: int = 9) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, 0, tzinfo=AGENDA_TZ)


def _turno(
    *,
    turno_id: uuid.UUID | None = None,
    inicio: datetime | None = None,
    profesional_id: uuid.UUID = PROF,
    sillon_id: uuid.UUID = SILLON,
    estado: str = "reservado-pendiente-pago",
) -> AgendaTurno:
    inicio = inicio or _inicio()
    return AgendaTurno(
        id=turno_id or uuid.uuid4(),
        inicio=inicio,
        fin=inicio + timedelta(minutes=30),
        estado=estado,
        profesional_id=profesional_id,
        sillon_id=sillon_id,
    )


def _pago(
    turno_id: uuid.UUID,
    *,
    estado: str = ESTADO_COBRO_PENDIENTE,
    monto: float = 5000.0,
    creado: datetime | None = None,
    mp_order_id: str | None = "mp-order-1",
) -> PagoRecord:
    return PagoRecord(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        turno_id=turno_id,
        mp_order_id=mp_order_id,
        monto=monto,
        estado=estado,
        created_at=creado or datetime.now(UTC),
        acreditado_at=datetime.now(UTC)
        if estado == ESTADO_COBRO_ACREDITADO
        else None,
    )


# --- Rango de la agenda -----------------------------------------------------


def test_rango_agenda_dia_usa_medianoche_local() -> None:
    """WHEN vista=dia THEN rango [00:00 local, +1 día) en la TZ de la clínica."""
    desde, hasta = rango_agenda(FECHA, "dia")
    assert desde == datetime(2026, 11, 13, 0, 0, tzinfo=AGENDA_TZ)
    assert hasta - desde == timedelta(days=1)


def test_rango_agenda_semana_cubre_siete_dias() -> None:
    """WHEN vista=semana THEN el rango cubre 7 días desde la fecha."""
    desde, hasta = rango_agenda(FECHA, "semana")
    assert hasta - desde == timedelta(days=7)


def test_rango_agenda_rechaza_vista_invalida() -> None:
    """WHEN vista desconocida THEN ValueError (fail-closed)."""
    with pytest.raises(ValueError):
        rango_agenda(FECHA, "mes")


# --- Proyección: estado de cobro en la agenda -------------------------------


@pytest.mark.asyncio
async def test_agenda_expone_cobro_acreditado() -> None:
    """WHEN el turno tiene pago acreditado THEN la agenda muestra `acreditado`."""
    turno = _turno()
    store = MemoryAgendaCobroStore()
    store.add_turno(turno)
    store.add_pago(_pago(turno.id, estado=ESTADO_COBRO_ACREDITADO, monto=7500.0))
    svc = AgendaCobroService(store)

    items = await svc.agenda(fecha=FECHA)

    assert len(items) == 1
    item = items[0]
    assert item.id == turno.id
    assert item.cobro == ESTADO_COBRO_ACREDITADO
    assert item.cobro_monto == 7500.0
    assert item.cobro_moneda == "ARS"
    assert item.cobro_mp_order_id == "mp-order-1"


@pytest.mark.asyncio
async def test_agenda_expone_cobro_pendiente_y_vencido() -> None:
    """WHEN hay órdenes pendiente/vencida THEN la agenda refleja cada estado."""
    pendiente = _turno()
    vencido = _turno()
    store = MemoryAgendaCobroStore()
    store.add_turno(pendiente)
    store.add_turno(vencido)
    store.add_pago(_pago(pendiente.id, estado=ESTADO_COBRO_PENDIENTE))
    store.add_pago(_pago(vencido.id, estado=ESTADO_COBRO_VENCIDO))
    svc = AgendaCobroService(store)

    por_id = {item.id: item for item in await svc.agenda(fecha=FECHA)}

    assert por_id[pendiente.id].cobro == ESTADO_COBRO_PENDIENTE
    assert por_id[vencido.id].cobro == ESTADO_COBRO_VENCIDO


@pytest.mark.asyncio
async def test_agenda_sin_orden_de_pago_muestra_sin_sena() -> None:
    """WHEN el turno no tiene seña THEN la agenda expone `sin-sena`."""
    turno = _turno(estado="confirmado")
    store = MemoryAgendaCobroStore()
    store.add_turno(turno)
    svc = AgendaCobroService(store)

    items = await svc.agenda(fecha=FECHA)

    assert items[0].cobro == ESTADO_COBRO_SIN_SENA
    assert items[0].cobro_monto is None


@pytest.mark.asyncio
async def test_agenda_usa_el_ultimo_pago_del_turno() -> None:
    """WHEN hay varios pagos THEN la agenda muestra el mas reciente."""
    turno = _turno()
    store = MemoryAgendaCobroStore()
    store.add_turno(turno)
    store.add_pago(
        _pago(
            turno.id,
            estado=ESTADO_COBRO_PENDIENTE,
            creado=datetime(2026, 11, 13, 11, 0, tzinfo=UTC),
        )
    )
    store.add_pago(
        _pago(
            turno.id,
            estado=ESTADO_COBRO_ACREDITADO,
            creado=datetime(2026, 11, 13, 12, 0, tzinfo=UTC),
        )
    )
    svc = AgendaCobroService(store)

    items = await svc.agenda(fecha=FECHA)

    assert items[0].cobro == ESTADO_COBRO_ACREDITADO


@pytest.mark.asyncio
async def test_agenda_filtra_por_profesional_y_sillon() -> None:
    """WHEN se filtra THEN solo se devuelven los turnos del filtro."""
    otro_prof = uuid.uuid4()
    otro_sillon = uuid.uuid4()
    propio = _turno()
    ajeno = _turno(profesional_id=otro_prof, sillon_id=otro_sillon)
    store = MemoryAgendaCobroStore()
    store.add_turno(propio)
    store.add_turno(ajeno)
    svc = AgendaCobroService(store)

    por_prof = await svc.agenda(fecha=FECHA, profesional_id=PROF)
    por_sillon = await svc.agenda(fecha=FECHA, sillon_id=SILLON)

    assert [t.id for t in por_prof] == [propio.id]
    assert [t.id for t in por_sillon] == [propio.id]


@pytest.mark.asyncio
async def test_agenda_vista_semana_incluye_todos_los_dias() -> None:
    """WHEN vista=semana THEN entran los turnos de los 7 días y no los de fuera."""
    lunes = _turno(inicio=_inicio(FECHA))
    domingo = _turno(inicio=_inicio(FECHA + timedelta(days=6)))
    siguiente = _turno(inicio=_inicio(FECHA + timedelta(days=7)))
    store = MemoryAgendaCobroStore()
    for turno in (lunes, domingo, siguiente):
        store.add_turno(turno)
    svc = AgendaCobroService(store)

    ids = {t.id for t in await svc.agenda(fecha=FECHA, vista="semana")}

    assert ids == {lunes.id, domingo.id}


# --- Reporte de señas pendientes -------------------------------------------


@pytest.mark.asyncio
async def test_reporte_senias_pendientes_solo_incluye_pendientes() -> None:
    """WHEN se pide el reporte THEN lista solo ordenes `pendiente` con su turno."""
    pendiente = _turno()
    acreditado = _turno()
    rechazado = _turno()
    store = MemoryAgendaCobroStore()
    for turno in (pendiente, acreditado, rechazado):
        store.add_turno(turno)
    store.add_pago(_pago(pendiente.id, estado=ESTADO_COBRO_PENDIENTE, monto=6000.0))
    store.add_pago(_pago(acreditado.id, estado=ESTADO_COBRO_ACREDITADO))
    store.add_pago(_pago(rechazado.id, estado=ESTADO_COBRO_RECHAZADO))
    svc = AgendaCobroService(store)

    reporte = await svc.senias_pendientes()

    assert len(reporte) == 1
    senia = reporte[0]
    assert senia.turno_id == pendiente.id
    assert senia.estado == ESTADO_COBRO_PENDIENTE
    assert senia.monto == 6000.0
    assert senia.turno_inicio == pendiente.inicio
    assert senia.turno_estado == "reservado-pendiente-pago"


# --- Endpoints HTTP ---------------------------------------------------------


def _app_for(roles: tuple[str, ...], store: MemoryAgendaCobroStore) -> FastAPI:
    principal = Principal(
        sub=f"user-{roles[0]}-ficticio",
        tenant_id=TENANT,
        roles=roles,
        email=f"{roles[0]}@demo-ficticia.invalid",
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router, prefix="/api")
    app.dependency_overrides[api_module.get_current_principal] = lambda: principal
    app.dependency_overrides[api_module.get_agenda_cobro_service] = (
        lambda: AgendaCobroService(store)
    )
    return app


def test_endpoint_agenda_incluye_cobro() -> None:
    """WHEN recepción consulta la agenda THEN cada turno incluye `cobro`."""
    turno = _turno()
    store = MemoryAgendaCobroStore()
    store.add_turno(turno)
    store.add_pago(_pago(turno.id, estado=ESTADO_COBRO_ACREDITADO, monto=5000.0))
    app = _app_for(("recepcion",), store)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/turnos/agenda?fecha={FECHA.isoformat()}")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list) and len(body) == 1
    item = body[0]
    assert item["id"] == str(turno.id)
    assert item["cobro"] == ESTADO_COBRO_ACREDITADO
    assert item["cobro_monto"] == 5000.0
    assert item["estado"] == "reservado-pendiente-pago"


def test_endpoint_agenda_sin_sena_expone_sin_sena() -> None:
    """WHEN el turno no tiene seña THEN el endpoint responde `sin-sena`."""
    turno = _turno(estado="confirmado")
    store = MemoryAgendaCobroStore()
    store.add_turno(turno)
    app = _app_for(("odontologo",), store)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/turnos/agenda?fecha={FECHA.isoformat()}&vista=dia"
        )

    assert response.status_code == 200
    assert response.json()[0]["cobro"] == ESTADO_COBRO_SIN_SENA


def test_endpoint_agenda_vista_semana_y_filtro_profesional() -> None:
    """WHEN se pide la semana filtrada THEN acepta vista + profesional_id."""
    propio = _turno()
    ajeno = _turno(profesional_id=uuid.uuid4())
    store = MemoryAgendaCobroStore()
    store.add_turno(propio)
    store.add_turno(ajeno)
    app = _app_for(("asistente",), store)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/turnos/agenda?fecha={FECHA.isoformat()}"
            f"&vista=semana&profesional_id={PROF}"
        )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(propio.id)]


def test_endpoint_agenda_rechaza_vista_invalida() -> None:
    """WHEN vista no es dia|semana THEN 422 (contrato estricto)."""
    store = MemoryAgendaCobroStore()
    app = _app_for(("recepcion",), store)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/turnos/agenda?fecha={FECHA.isoformat()}&vista=mes"
        )

    assert response.status_code == 422


def test_endpoint_agenda_sin_jwt_responde_401() -> None:
    """WHEN no hay JWT THEN el endpoint de agenda responde 401."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router, prefix="/api")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/turnos/agenda?fecha={FECHA.isoformat()}")

    assert response.status_code == 401


def test_endpoint_agenda_deniega_paciente_portal() -> None:
    """WHEN un paciente-portal consulta la agenda THEN 403 (RBAC staff)."""
    store = MemoryAgendaCobroStore()
    app = _app_for(("paciente-portal",), store)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/turnos/agenda?fecha={FECHA.isoformat()}")

    assert response.status_code == 403


def test_endpoint_reporte_senias_pendientes() -> None:
    """WHEN recepción pide el reporte THEN lista las señas sin acreditar."""
    turno = _turno()
    store = MemoryAgendaCobroStore()
    store.add_turno(turno)
    store.add_pago(_pago(turno.id, estado=ESTADO_COBRO_PENDIENTE, monto=4500.0))
    app = _app_for(("recepcion",), store)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/reportes/senias-pendientes")

    assert response.status_code == 200
    reporte = response.json()
    assert len(reporte) == 1
    assert reporte[0]["turno_id"] == str(turno.id)
    assert reporte[0]["estado"] == ESTADO_COBRO_PENDIENTE
    assert reporte[0]["monto"] == 4500.0


def test_app_monta_endpoints_de_agenda_y_reporte() -> None:
    """WHEN se crea la app THEN ambos endpoints quedan documentados en OpenAPI."""
    from app.main import create_app

    paths = create_app().openapi()["paths"]

    assert "get" in paths["/api/turnos/agenda"]
    assert "get" in paths["/api/reportes/senias-pendientes"]


def test_endpoint_reporte_senias_sin_jwt_responde_401() -> None:
    """WHEN no hay JWT THEN el reporte responde 401."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router, prefix="/api")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/reportes/senias-pendientes")

    assert response.status_code == 401


# --- Store DB: scoping tenant (compiled SQL, sin live DB) -------------------


def test_db_store_exige_tenant() -> None:
    """WHEN se construye sin tenant THEN TenantScopeError (fail-closed)."""
    with pytest.raises(TenantScopeError):
        DbAgendaCobroStore(session=None, tenant_id=None)
    with pytest.raises(TenantScopeError):
        DbAgendaCobroStore(session=None, tenant_id="no-es-uuid")


def test_db_store_agenda_filtra_tenant_y_rango() -> None:
    """WHEN se compila la query de agenda THEN filtra tenant + rango + filtros."""
    store = DbAgendaCobroStore(session=None, tenant_id=TENANT)
    desde, hasta = rango_agenda(FECHA, "dia")

    stmt = store._stmt_turnos(
        desde=desde, hasta=hasta, profesional_id=PROF, sillon_id=SILLON
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "turno.tenant_id" in compiled
    assert str(TENANT).replace("-", "") in compiled
    assert "turno.profesional_id" in compiled
    assert "turno.sillon_id" in compiled
    assert "turno.inicio" in compiled


def test_db_store_senias_filtra_tenant_y_estado_pendiente() -> None:
    """WHEN se compila la query del reporte THEN filtra tenant + estado pendiente."""
    store = DbAgendaCobroStore(session=None, tenant_id=TENANT)

    stmt = store._stmt_senias_pendientes(limit=50)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "pago.tenant_id" in compiled
    assert str(TENANT).replace("-", "") in compiled
    assert ESTADO_COBRO_PENDIENTE in compiled
    assert "LIMIT 50" in compiled.upper()
