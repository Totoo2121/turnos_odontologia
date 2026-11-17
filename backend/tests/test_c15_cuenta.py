"""C-15 group 1: counter payments, receipts and daily cash close."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid
from decimal import Decimal

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import caja as caja_api
from app.application.agenda_cobros import AGENDA_TZ
from app.application.caja import CajaService, TurnoDia
from app.application.cuenta_corriente import (
    MovimientoCCRecord,
    build_referencia_pago,
    parse_referencia_pago,
)
from app.shared.exceptions import AppError, register_exception_handlers
from tests.support_c14 import (
    TENANT_A,
    TENANT_B,
    cuenta_service,
    principal,
    seed_paciente_historia,
)
from tests.support_c15 import build_c15_client, build_c15_stores, pago


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _status(exc: pytest.ExceptionInfo[AppError]) -> int:
    return exc.value.status_code


def _hoy() -> datetime.date:
    return datetime.datetime.now(AGENDA_TZ).date()


def _setup():
    stores = build_c15_stores()
    paciente, historia = seed_paciente_historia(stores.c14)
    return stores, paciente, historia


# --- 1.1 Store -------------------------------------------------------------


def test_movimiento_store_get_and_list_between() -> None:
    stores = build_c15_stores()
    tenant = TENANT_A
    base = datetime.datetime(2026, 5, 1, 12, tzinfo=AGENDA_TZ)
    dentro = MovimientoCCRecord(
        id=uuid.uuid4(),
        tenant_id=tenant,
        cuenta_id=uuid.uuid4(),
        tipo="credito",
        monto=Decimal("100.00"),
        descripcion="Dentro del dia",
        ocurrido_at=base,
    )
    fuera = MovimientoCCRecord(
        id=uuid.uuid4(),
        tenant_id=tenant,
        cuenta_id=uuid.uuid4(),
        tipo="credito",
        monto=Decimal("200.00"),
        descripcion="Otro dia",
        ocurrido_at=base + datetime.timedelta(days=2),
    )
    ajeno = MovimientoCCRecord(
        id=uuid.uuid4(),
        tenant_id=TENANT_B,
        cuenta_id=uuid.uuid4(),
        tipo="debito",
        monto=Decimal("300.00"),
        descripcion="Otro tenant",
        ocurrido_at=base,
    )
    for row in (dentro, fuera, ajeno):
        _run(stores.c14.movimientos.add(row))

    row = _run(stores.c14.movimientos.get(tenant, dentro.id))
    assert row is not None
    assert (row.id, row.monto, row.descripcion) == (
        dentro.id,
        dentro.monto,
        dentro.descripcion,
    )
    assert _run(stores.c14.movimientos.get(TENANT_B, dentro.id)) is None

    desde = datetime.datetime(2026, 5, 1, tzinfo=AGENDA_TZ)
    hasta = desde + datetime.timedelta(days=1)
    rows = _run(stores.c14.movimientos.list_between(tenant, desde, hasta))
    assert [row.id for row in rows] == [dentro.id]

    vacio = desde + datetime.timedelta(days=10)
    assert (
        _run(
            stores.c14.movimientos.list_between(
                tenant, vacio, vacio + datetime.timedelta(days=1)
            )
        )
        == []
    )
    assert [
        row.id
        for row in _run(
            stores.c14.movimientos.list_between(TENANT_B, desde, hasta)
        )
    ] == [ajeno.id]


def test_referencia_parser_round_trip() -> None:
    referencia = build_referencia_pago("transferencia", "clave-ficticia-1")
    assert referencia == "pago:transferencia:clave-ficticia-1"
    assert parse_referencia_pago(referencia) == (
        "transferencia",
        "clave-ficticia-1",
    )
    for invalida in (None, "", "otra:cosa", "pago:tarjeta:abc", "pago:efectivo:"):
        assert parse_referencia_pago(invalida) is None


# --- 1.2 Payments ----------------------------------------------------------


def test_registrar_pago_balance_and_idempotency() -> None:
    stores, paciente, _historia = _setup()
    cuenta = cuenta_service(stores.c14)
    recepcion = principal(roles=("recepcion",))
    _run(
        cuenta.registrar_debito(
            recepcion.tenant_id,
            paciente.id,
            monto="18000.75",
            descripcion="Debito ficticio C-15",
            referencia="ficticio:c15:1",
        )
    )

    primero = pago(
        stores,
        recepcion,
        paciente.id,
        monto="8000.00",
        medio="efectivo",
        idempotency_key="clave-pago-1",
    )
    assert primero.movimiento.tipo == "credito"
    assert primero.movimiento.monto == Decimal("8000.00")
    assert primero.referencia == "pago:efectivo:clave-pago-1"
    assert primero.saldo == Decimal("10000.75")

    repetido = pago(
        stores,
        recepcion,
        paciente.id,
        monto="8000.00",
        medio="efectivo",
        idempotency_key="clave-pago-1",
    )
    assert repetido.movimiento.id == primero.movimiento.id
    assert repetido.saldo == Decimal("10000.75")

    otro = pago(
        stores,
        recepcion,
        paciente.id,
        monto="20000.00",
        medio="transferencia",
        idempotency_key="clave-pago-2",
    )
    assert otro.movimiento.id != primero.movimiento.id
    assert otro.saldo == Decimal("-9999.25")

    view = _run(cuenta.obtener(recepcion, paciente.id))
    assert len(view.movimientos) == 3


def test_pago_rejects_invalid_amount_medium_and_roles() -> None:
    stores, paciente, _historia = _setup()
    recepcion = principal(roles=("recepcion",))
    with pytest.raises(AppError) as exc:
        pago(stores, recepcion, paciente.id, monto="0")
    assert _status(exc) == 422
    with pytest.raises(AppError) as exc:
        pago(stores, recepcion, paciente.id, monto="-100")
    assert _status(exc) == 422
    with pytest.raises(AppError) as exc:
        pago(stores, recepcion, paciente.id, medio="tarjeta")
    assert _status(exc) == 422
    for rol in ("odontologo", "asistente"):
        with pytest.raises(AppError) as exc:
            pago(stores, principal(roles=(rol,)), paciente.id)
        assert _status(exc) == 403
    with pytest.raises(AppError) as exc:
        pago(stores, principal(tenant_id=TENANT_B), paciente.id)
    assert _status(exc) == 404
    cuenta_recepcion = _run(
        cuenta_service(stores.c14).obtener(recepcion, paciente.id)
    )
    assert cuenta_recepcion.movimientos == []


# --- 1.3 Receipt -----------------------------------------------------------


def test_recibo_pdf_is_deterministic_and_tenant_scoped() -> None:
    stores, paciente, _historia = _setup()
    recepcion = principal(roles=("recepcion",))
    resultado = pago(
        stores,
        recepcion,
        paciente.id,
        monto="15000.00",
        medio="efectivo",
        idempotency_key="recibo-1",
    )
    cuenta = cuenta_service(stores.c14)
    recibo = _run(cuenta.recibo(recepcion, resultado.movimiento.id))
    assert recibo.medio == "efectivo"
    assert recibo.paciente.id == paciente.id
    assert recibo.saldo == Decimal("-15000.00")

    pdf = caja_api.render_recibo(recibo)
    assert pdf.startswith(b"%PDF-1.4")
    assert b"15000.00" in pdf
    assert b"Efectivo" in pdf
    assert caja_api.render_recibo(recibo) == pdf

    otra = pago(
        stores,
        recepcion,
        paciente.id,
        monto="500.00",
        medio="mp",
        idempotency_key="recibo-2",
    )
    assert caja_api.render_recibo(
        _run(cuenta.recibo(recepcion, otra.movimiento.id))
    ) != pdf

    recibo_odontologo = _run(
        cuenta.recibo(principal(roles=("odontologo",)), resultado.movimiento.id)
    )
    assert recibo_odontologo.medio == "efectivo"
    with pytest.raises(AppError) as exc:
        _run(cuenta.recibo(principal(roles=("asistente",)), resultado.movimiento.id))
    assert _status(exc) == 403
    with pytest.raises(AppError) as exc:
        _run(
            cuenta.recibo(
                principal(tenant_id=TENANT_B), resultado.movimiento.id
            )
        )
    assert _status(exc) == 404
    with pytest.raises(AppError) as exc:
        _run(cuenta.recibo(recepcion, uuid.uuid4()))
    assert _status(exc) == 404


# --- 1.4 Daily close -------------------------------------------------------


def test_cierre_caja_totals_and_empty_day() -> None:
    stores, paciente, _historia = _setup()
    recepcion = principal(roles=("recepcion",))
    cuenta = cuenta_service(stores.c14)
    _run(
        cuenta.registrar_debito(
            recepcion.tenant_id,
            paciente.id,
            monto="18000.75",
            descripcion="Debito ficticio C-15",
            referencia="ficticio:c15:cierre",
        )
    )
    pago(stores, recepcion, paciente.id, monto="8000.00", medio="efectivo")
    pago(stores, recepcion, paciente.id, monto="2500.00", medio="efectivo")
    pago(stores, recepcion, paciente.id, monto="1000.00", medio="mp")

    hoy = _hoy()
    inicio = datetime.datetime.combine(
        hoy, datetime.time(10, 0), tzinfo=AGENDA_TZ
    )
    stores.turnos_dia.add(
        TurnoDia(
            id=uuid.uuid4(),
            inicio=inicio,
            fin=inicio + datetime.timedelta(minutes=40),
            estado="atendido",
            paciente_id=paciente.id,
        )
    )
    stores.turnos_dia.add(
        TurnoDia(
            id=uuid.uuid4(),
            inicio=inicio + datetime.timedelta(hours=1),
            fin=inicio + datetime.timedelta(hours=1, minutes=40),
            estado="pendiente",
            paciente_id=paciente.id,
        )
    )

    view = _run(
        CajaService(stores.c14.movimientos, stores.turnos_dia).cerrar(
            recepcion, hoy
        )
    )
    assert view.cobrado_total == Decimal("11500.00")
    assert view.por_medio["efectivo"] == Decimal("10500.00")
    assert view.por_medio["mp"] == Decimal("1000.00")
    assert view.por_medio["transferencia"] == Decimal("0.00")
    assert view.cantidad_pagos == 3
    assert view.deuda_generada == Decimal("18000.75")
    assert view.diferencia_caja == Decimal("-6500.75")
    assert view.turnos_atendidos == 1
    assert len(view.movimientos) == 4
    assert len(view.turnos) == 2

    vacio = _run(
        CajaService(stores.c14.movimientos, stores.turnos_dia).cerrar(
            recepcion, datetime.date(2000, 1, 1)
        )
    )
    assert vacio.cobrado_total == Decimal("0.00")
    assert vacio.cantidad_pagos == 0
    assert vacio.turnos_atendidos == 0
    assert vacio.movimientos == []

    with pytest.raises(AppError) as exc:
        _run(
            CajaService(stores.c14.movimientos, stores.turnos_dia).cerrar(
                principal(roles=("asistente",)), hoy
            )
        )
    assert _status(exc) == 403


# --- 1.5 HTTP API ----------------------------------------------------------


def test_pago_http_contract_and_roles() -> None:
    stores, paciente, _historia = _setup()
    recepcion = principal(roles=("recepcion",))
    _run(
        cuenta_service(stores.c14).registrar_debito(
            recepcion.tenant_id,
            paciente.id,
            monto="18000.75",
            descripcion="Debito ficticio C-15",
            referencia="ficticio:c15:http",
        )
    )
    client = build_c15_client(stores, recepcion)
    response = client.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "8000.00",
            "medio": "efectivo",
            "idempotency_key": "http-pago-1",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["medio"] == "efectivo"
    assert data["saldo"] == "10000.75"
    assert data["referencia"] == "pago:efectivo:http-pago-1"
    assert data["movimiento"]["tipo"] == "credito"

    repetido = client.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "8000.00",
            "medio": "efectivo",
            "idempotency_key": "http-pago-1",
        },
    )
    assert repetido.status_code == 201
    assert repetido.json()["movimiento"]["id"] == data["movimiento"]["id"]

    assert (
        client.post(
            f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
            json={"monto": "0", "medio": "efectivo"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
            json={"monto": "10", "medio": "tarjeta"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
            json={"monto": "10", "medio": "efectivo", "extra": True},
        ).status_code
        == 422
    )

    for rol in ("odontologo", "asistente"):
        ajeno = build_c15_client(stores, principal(roles=(rol,)))
        assert (
            ajeno.post(
                f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
                json={"monto": "10", "medio": "efectivo"},
            ).status_code
            == 403
        )


def test_recibo_y_cierre_http() -> None:
    stores, paciente, _historia = _setup()
    recepcion = principal(roles=("recepcion",))
    client = build_c15_client(stores, recepcion)
    created = client.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={"monto": "15000.00", "medio": "transferencia"},
    ).json()
    movimiento_id = created["movimiento"]["id"]

    recibo = client.get(f"/api/movimientos-cc/{movimiento_id}/recibo")
    assert recibo.status_code == 200
    assert recibo.headers["content-type"] == "application/pdf"
    assert recibo.content.startswith(b"%PDF-1.4")
    assert b"15000.00" in recibo.content
    assert "attachment" in recibo.headers["content-disposition"]

    assert (
        client.get(f"/api/movimientos-cc/{uuid.uuid4()}/recibo").status_code
        == 404
    )
    assert (
        build_c15_client(stores, principal(roles=("asistente",)))
        .get(f"/api/movimientos-cc/{movimiento_id}/recibo")
        .status_code
        == 403
    )

    cierre = client.get(f"/api/caja/cierre?fecha={_hoy().isoformat()}")
    assert cierre.status_code == 200, cierre.text
    data = cierre.json()
    assert data["cobrado_total"] == "15000.00"
    assert data["por_medio"]["transferencia"] == "15000.00"
    assert data["cantidad_pagos"] == 1
    assert data["deuda_generada"] == "0.00"
    assert data["diferencia_caja"] == "15000.00"
    assert data["moneda"] == "ARS"
    assert len(data["movimientos"]) == 1

    assert (
        build_c15_client(stores, principal(roles=("asistente",)))
        .get("/api/caja/cierre")
        .status_code
        == 403
    )
    assert (
        build_c15_client(stores, principal(roles=("odontologo",)))
        .get("/api/caja/cierre")
        .status_code
        == 200
    )


def test_caja_routes_require_authentication_and_are_in_openapi() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(caja_api.router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)
    for method, path in (
        ("post", f"/api/pacientes/{uuid.uuid4()}/cuenta-corriente/pagos"),
        ("get", f"/api/movimientos-cc/{uuid.uuid4()}/recibo"),
        ("get", "/api/caja/cierre"),
    ):
        assert getattr(client, method)(path).status_code == 401

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/pacientes/{paciente_id}/cuenta-corriente/pagos"]
    assert "get" in paths["/api/movimientos-cc/{movimiento_id}/recibo"]
    assert "get" in paths["/api/caja/cierre"]
