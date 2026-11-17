"""C-15 group 2: minimal appointment lifecycle (create, state, cancel)."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import turnos as turnos_api
from app.application.agenda_cobros import AGENDA_TZ
from app.application.turnos import (
    BloqueoAgenda,
    MemoryTurnoStore,
    ProfesionalAgenda,
    SillonAgenda,
    TurnoRecord,
)
from app.shared.exceptions import AppError, register_exception_handlers
from tests.support_c14 import TENANT_A, TENANT_B, principal
from tests.support_c15 import (
    build_c15_stores,
    build_turno_client,
    build_turno_rig,
    crear_turno,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _status(exc: pytest.ExceptionInfo[AppError]) -> int:
    return exc.value.status_code


def _inicio(day: int = 1, hour: int = 10) -> datetime.datetime:
    return datetime.datetime(2030, 1, day, hour, 0, tzinfo=AGENDA_TZ)


# --- 2.1 Stores ------------------------------------------------------------


def test_memory_turno_store_tenant_scope_and_overlaps() -> None:
    store = MemoryTurnoStore()
    turno = TurnoRecord(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        profesional_id=uuid.uuid4(),
        sillon_id=uuid.uuid4(),
        prestacion_id=uuid.uuid4(),
        inicio=_inicio(),
        fin=_inicio() + datetime.timedelta(minutes=40),
    )
    _run(store.add(turno))
    assert _run(store.get(TENANT_A, turno.id)) == turno
    assert _run(store.get(TENANT_B, turno.id)) is None

    overlaps = _run(
        store.list_overlaps(
            TENANT_A,
            profesional_id=turno.profesional_id,
            sillon_id=turno.sillon_id,
            inicio=_inicio(hour=10) + datetime.timedelta(minutes=20),
            fin=_inicio(hour=11),
        )
    )
    assert [row.id for row in overlaps] == [turno.id]
    assert (
        _run(
            store.list_overlaps(
                TENANT_A,
                profesional_id=turno.profesional_id,
                sillon_id=turno.sillon_id,
                inicio=_inicio(hour=11),
                fin=_inicio(hour=12),
            )
        )
        == []
    )

    cancelado = TurnoRecord(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        profesional_id=turno.profesional_id,
        sillon_id=turno.sillon_id,
        prestacion_id=turno.prestacion_id,
        inicio=_inicio(hour=11),
        fin=_inicio(hour=12),
        estado="cancelado",
    )
    _run(store.add(cancelado))
    assert (
        _run(
            store.list_overlaps(
                TENANT_A,
                profesional_id=turno.profesional_id,
                sillon_id=turno.sillon_id,
                inicio=_inicio(hour=11),
                fin=_inicio(hour=12),
            )
        )
        == []
    )


# --- 2.2 Create ------------------------------------------------------------


def test_crear_calcula_fin_y_origen() -> None:
    stores = build_c15_stores()
    rig = build_turno_rig(stores, duracion_min=30, buffer_min=10)
    turno = crear_turno(rig, principal(), inicio=_inicio())
    assert turno.estado == "pendiente"
    assert turno.origen == "recepcion"
    assert turno.inicio == _inicio()
    assert turno.fin == _inicio() + datetime.timedelta(minutes=40)
    assert _run(rig.turnos.get(TENANT_A, turno.id)) == turno

    control = crear_turno(rig, principal(), inicio=_inicio(hour=12), origen="control")
    assert control.origen == "control"
    assert control.fin == _inicio(hour=12) + datetime.timedelta(minutes=40)


def test_crear_rechaza_solape_bloqueo_y_referencias() -> None:
    stores = build_c15_stores()
    rig = build_turno_rig(stores)
    owner = principal()
    crear_turno(rig, owner, inicio=_inicio())

    with pytest.raises(AppError) as exc:
        crear_turno(
            rig, owner, inicio=_inicio() + datetime.timedelta(minutes=20)
        )
    assert _status(exc) == 409

    otro_profesional = ProfesionalAgenda(
        id=uuid.uuid4(), tenant_id=TENANT_A, nombre="Otro Ficticio"
    )
    rig.catalogo.profesionales[otro_profesional.id] = otro_profesional
    with pytest.raises(AppError) as exc:
        crear_turno(
            rig,
            owner,
            inicio=_inicio() + datetime.timedelta(minutes=20),
            profesional_id=otro_profesional.id,
        )
    assert _status(exc) == 409

    rig.bloqueos.add(
        BloqueoAgenda(
            id=uuid.uuid4(),
            tenant_id=TENANT_A,
            inicio=_inicio(hour=13),
            fin=_inicio(hour=14),
            motivo="licencia",
            profesional_id=rig.profesional.id,
        )
    )
    with pytest.raises(AppError) as exc:
        crear_turno(rig, owner, inicio=_inicio(hour=13))
    assert _status(exc) == 409
    assert "licencia" in exc.value.message

    with pytest.raises(AppError) as exc:
        crear_turno(rig, owner, inicio=_inicio(day=2), prestacion_id=uuid.uuid4())
    assert _status(exc) == 422
    with pytest.raises(AppError) as exc:
        crear_turno(rig, owner, inicio=_inicio(day=2), profesional_id=uuid.uuid4())
    assert _status(exc) == 422
    with pytest.raises(AppError) as exc:
        crear_turno(rig, owner, inicio=_inicio(day=2), sillon_id=uuid.uuid4())
    assert _status(exc) == 422
    with pytest.raises(AppError) as exc:
        crear_turno(rig, owner, inicio=_inicio(day=2), paciente_id=uuid.uuid4())
    assert _status(exc) == 404

    for rol in ("odontologo", "asistente"):
        with pytest.raises(AppError) as exc:
            crear_turno(
                rig, principal(roles=(rol,)), inicio=_inicio(day=3)
            )
        assert _status(exc) == 403


def test_crear_rechaza_catalogo_inactivo() -> None:
    stores = build_c15_stores()
    rig = build_turno_rig(stores)
    rig.catalogo.profesionales[rig.profesional.id] = ProfesionalAgenda(
        id=rig.profesional.id,
        tenant_id=TENANT_A,
        nombre="Inactivo",
        activo=False,
    )
    with pytest.raises(AppError) as exc:
        crear_turno(rig, principal(), inicio=_inicio())
    assert _status(exc) == 422

    rig.catalogo.profesionales[rig.profesional.id] = rig.profesional
    rig.catalogo.sillones[rig.sillon.id] = SillonAgenda(
        id=rig.sillon.id, tenant_id=TENANT_A, nombre="Inactivo", activo=False
    )
    with pytest.raises(AppError) as exc:
        crear_turno(rig, principal(), inicio=_inicio())
    assert _status(exc) == 422


# --- 2.3 State machine and cancellation -----------------------------------


def test_maquina_de_estados() -> None:
    stores = build_c15_stores()
    rig = build_turno_rig(stores)
    owner = principal()
    turno = crear_turno(rig, owner, inicio=_inicio())

    confirmado = _run(
        rig.service.cambiar_estado(owner, turno.id, "confirmado")
    )
    assert confirmado.estado == "confirmado"
    assert confirmado.confirmado_at is not None

    repetido = _run(
        rig.service.cambiar_estado(owner, turno.id, "confirmado")
    )
    assert repetido.estado == "confirmado"

    atendido = _run(rig.service.cambiar_estado(owner, turno.id, "atendido"))
    assert atendido.estado == "atendido"

    with pytest.raises(AppError) as exc:
        _run(rig.service.cambiar_estado(owner, turno.id, "confirmado"))
    assert _status(exc) == 409
    with pytest.raises(AppError) as exc:
        _run(rig.service.cambiar_estado(owner, turno.id, "en-curso"))
    assert _status(exc) == 422

    otro = crear_turno(rig, owner, inicio=_inicio(day=2))
    assert (
        _run(rig.service.cambiar_estado(owner, otro.id, "ausente")).estado
        == "ausente"
    )
    with pytest.raises(AppError) as exc:
        _run(rig.service.cambiar_estado(owner, uuid.uuid4(), "atendido"))
    assert _status(exc) == 404
    with pytest.raises(AppError) as exc:
        _run(
            rig.service.cambiar_estado(
                principal(tenant_id=TENANT_B), otro.id, "atendido"
            )
        )
    assert _status(exc) == 404
    with pytest.raises(AppError) as exc:
        _run(
            rig.service.cambiar_estado(
                principal(roles=("asistente",)), otro.id, "atendido"
            )
        )
    assert _status(exc) == 403


def test_cancelacion_con_politica_de_sena() -> None:
    stores = build_c15_stores()
    rig = build_turno_rig(
        stores, sena_obligatoria=True, anticipacion_min_cancel_hs=24
    )
    owner = principal()

    en_termino = crear_turno(rig, owner, inicio=_inicio(day=3))
    resultado = _run(
        rig.service.cancelar(
            owner,
            en_termino.id,
            ahora=_inicio(day=3) - datetime.timedelta(hours=48),
        )
    )
    assert resultado.turno.estado == "cancelado"
    assert resultado.cancelacion_tardia is False
    assert resultado.senia_perdida is False
    repetida = _run(rig.service.cancelar(owner, en_termino.id))
    assert repetida.turno.estado == "cancelado"
    assert repetida.senia_perdida is False

    tardia = crear_turno(rig, owner, inicio=_inicio(day=4))
    resultado = _run(
        rig.service.cancelar(
            owner,
            tardia.id,
            ahora=_inicio(day=4) - datetime.timedelta(hours=1),
        )
    )
    assert resultado.cancelacion_tardia is True
    assert resultado.senia_perdida is True

    stores_sin_sena = build_c15_stores()
    rig_sin_sena = build_turno_rig(
        stores_sin_sena, sena_obligatoria=False
    )
    turno = crear_turno(rig_sin_sena, owner, inicio=_inicio(day=4))
    resultado = _run(
        rig_sin_sena.service.cancelar(
            owner,
            turno.id,
            ahora=_inicio(day=4) - datetime.timedelta(hours=1),
        )
    )
    assert resultado.cancelacion_tardia is True
    assert resultado.senia_perdida is False

    atendido = crear_turno(rig, owner, inicio=_inicio(day=5))
    _run(rig.service.cambiar_estado(owner, atendido.id, "atendido"))
    with pytest.raises(AppError) as exc:
        _run(rig.service.cancelar(owner, atendido.id))
    assert _status(exc) == 409
    with pytest.raises(AppError) as exc:
        _run(
            rig.service.cancelar(
                principal(roles=("asistente",)), turno.id
            )
        )
    assert _status(exc) == 403


# --- 2.4 HTTP API ----------------------------------------------------------


def test_http_turnos_contract_and_roles() -> None:
    stores = build_c15_stores()
    rig = build_turno_rig(stores)
    recepcion = principal(roles=("recepcion",))
    client = build_turno_client(rig, recepcion)
    payload = {
        "paciente_id": str(rig.paciente.id),
        "profesional_id": str(rig.profesional.id),
        "sillon_id": str(rig.sillon.id),
        "prestacion_id": str(rig.prestacion.id),
        "inicio": _inicio(day=10).isoformat(),
    }
    response = client.post("/api/turnos", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["estado"] == "pendiente"
    assert data["fin"] == (_inicio(day=10) + datetime.timedelta(minutes=40)).isoformat()

    assert (
        client.post("/api/turnos", json={**payload, "extra": True}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/turnos",
            json={
                **payload,
                "inicio": _inicio(day=10, hour=10).isoformat(),
            },
        ).status_code
        == 409
    )

    turno_id = data["id"]
    confirmado = client.patch(
        f"/api/turnos/{turno_id}/estado", json={"estado": "confirmado"}
    )
    assert confirmado.status_code == 200
    assert confirmado.json()["estado"] == "confirmado"
    cancelado = client.post(f"/api/turnos/{turno_id}/cancelar")
    assert cancelado.status_code == 200
    assert cancelado.json()["turno"]["estado"] == "cancelado"
    assert set(cancelado.json()) >= {
        "turno",
        "cancelacion_tardia",
        "senia_perdida",
    }
    assert (
        client.patch(
            f"/api/turnos/{turno_id}/estado", json={"estado": "atendido"}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/turnos/{uuid.uuid4()}/estado", json={"estado": "atendido"}
        ).status_code
        == 404
    )

    odontologo = build_turno_client(rig, principal(roles=("odontologo",)))
    assert (
        odontologo.post(
            "/api/turnos",
            json={**payload, "inicio": _inicio(day=11).isoformat()},
        ).status_code
        == 403
    )
    assert (
        odontologo.patch(
            f"/api/turnos/{turno_id}/estado", json={"estado": "atendido"}
        ).status_code
        == 409
    )

    asistente = build_turno_client(rig, principal(roles=("asistente",)))
    for response in (
        asistente.post(
            "/api/turnos",
            json={**payload, "inicio": _inicio(day=12).isoformat()},
        ),
        asistente.patch(
            f"/api/turnos/{turno_id}/estado", json={"estado": "atendido"}
        ),
        asistente.post(f"/api/turnos/{turno_id}/cancelar"),
    ):
        assert response.status_code == 403

    otro = build_turno_client(rig, principal(tenant_id=TENANT_B))
    assert (
        otro.patch(
            f"/api/turnos/{turno_id}/estado", json={"estado": "atendido"}
        ).status_code
        == 404
    )


def test_turnos_routes_require_authentication_and_are_in_openapi() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(turnos_api.router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/api/turnos", json={}).status_code == 401
    assert (
        client.patch(
            f"/api/turnos/{uuid.uuid4()}/estado", json={"estado": "atendido"}
        ).status_code
        == 401
    )
    assert (
        client.post(f"/api/turnos/{uuid.uuid4()}/cancelar").status_code == 401
    )

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/turnos"]
    assert "patch" in paths["/api/turnos/{turno_id}/estado"]
    assert "post" in paths["/api/turnos/{turno_id}/cancelar"]
