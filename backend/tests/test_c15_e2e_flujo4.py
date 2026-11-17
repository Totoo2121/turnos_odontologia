"""C-15 task 6.2: E2E Flujo 4 (agenda del dia con cobro MP -> deuda -> pago
idempotente -> recibo PDF -> cierre de caja con turnos atendidos).

Sin Postgres ni red; datos 100% ficticios. Verifica totales por medio, deuda
generada y diferencia de caja antes y despues del cobro total.
"""

from __future__ import annotations

import datetime
import os
import uuid
from decimal import Decimal

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from app.application.agenda_cobros import (
    AGENDA_TZ,
    AgendaTurno,
    MemoryAgendaCobroStore,
)
from app.application.caja import TurnoDia
from app.application.cobros import ESTADO_COBRO_ACREDITADO, PagoRecord
from tests.support_c14 import (
    TENANT_A,
    principal,
    seed_paciente_historia,
    seed_prestacion,
)
from tests.support_c15 import build_c15_client, build_c15_stores


def _hoy() -> datetime.date:
    return datetime.datetime.now(AGENDA_TZ).date()


def test_flujo4_agenda_mp_pago_idempotente_recibo_y_cierre() -> None:
    stores = build_c15_stores()
    paciente, historia = seed_paciente_historia(
        stores.c14, nombre="Paciente Ficticio Flujo 4"
    )
    prestacion = seed_prestacion(
        stores.c14,
        nombre="Tratamiento ficticio Flujo 4",
        precio="25000.00",
        requiere_consentimiento=False,
    )
    owner = principal()
    client = build_c15_client(stores, owner)

    # Deuda del dia: presupuesto aceptado (sin gate invasivo).
    created = client.post(
        "/api/presupuestos",
        json={
            "paciente_id": str(paciente.id),
            "historia_clinica_id": str(historia.id),
            "items": [
                {
                    "prestacion_id": str(prestacion.id),
                    "etapa": 1,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    budget_id = created.json()["id"]
    assert created.json()["total"] == "25000.00"
    assert client.post(f"/api/presupuestos/{budget_id}/enviar").status_code == 200
    accepted = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["movimiento_id"] is not None

    # Agenda del dia: turno atendido con sena MP acreditada.
    hoy = _hoy()
    inicio = datetime.datetime.combine(
        hoy, datetime.time(10, 0), tzinfo=AGENDA_TZ
    )
    turno_id = uuid.uuid4()
    profesional_id = uuid.uuid4()
    sillon_id = uuid.uuid4()
    ahora = datetime.datetime.now(AGENDA_TZ)
    agenda = MemoryAgendaCobroStore()
    agenda.add_turno(
        AgendaTurno(
            id=turno_id,
            inicio=inicio,
            fin=inicio + datetime.timedelta(minutes=30),
            estado="atendido",
            profesional_id=profesional_id,
            sillon_id=sillon_id,
            prestacion_id=prestacion.id,
            paciente_id=paciente.id,
        )
    )
    agenda.add_pago(
        PagoRecord(
            id=uuid.uuid4(),
            tenant_id=TENANT_A,
            turno_id=turno_id,
            mp_order_id="mp-order-ficticia-flujo4",
            monto=5000.0,
            moneda="ARS",
            estado=ESTADO_COBRO_ACREDITADO,
            acreditado_at=ahora,
            created_at=ahora,
        )
    )
    stores.turnos_dia.add(
        TurnoDia(
            id=turno_id,
            inicio=inicio,
            fin=inicio + datetime.timedelta(minutes=30),
            estado="atendido",
            paciente_id=paciente.id,
            profesional_id=profesional_id,
            sillon_id=sillon_id,
        )
    )

    recepcion = principal(roles=("recepcion",))
    caja = build_c15_client(stores, recepcion, agenda=agenda)

    agenda_dia = caja.get(f"/api/turnos/agenda?fecha={hoy.isoformat()}")
    assert agenda_dia.status_code == 200, agenda_dia.text
    turnos = agenda_dia.json()
    assert len(turnos) == 1
    assert turnos[0]["id"] == str(turno_id)
    assert turnos[0]["estado"] == "atendido"
    assert turnos[0]["cobro"] == "acreditado"
    assert turnos[0]["cobro_monto"] == 5000.0
    assert turnos[0]["cobro_mp_order_id"] == "mp-order-ficticia-flujo4"
    assert turnos[0]["prestacion_id"] == str(prestacion.id)

    # Pago parcial idempotente: repetir la clave no duplica el credito.
    primero = caja.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "20000.00",
            "medio": "efectivo",
            "idempotency_key": "flujo4-pago-1",
            "descripcion": "Pago parcial ficticio Flujo 4",
        },
    )
    assert primero.status_code == 201, primero.text
    pago_uno = primero.json()
    assert pago_uno["saldo"] == "5000.00"
    assert pago_uno["referencia"] == "pago:efectivo:flujo4-pago-1"

    repetido = caja.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "20000.00",
            "medio": "efectivo",
            "idempotency_key": "flujo4-pago-1",
        },
    )
    assert repetido.status_code == 201
    assert repetido.json()["movimiento"]["id"] == pago_uno["movimiento"]["id"]
    assert repetido.json()["saldo"] == "5000.00"

    # Recibo PDF deterministico del pago parcial.
    recibo = caja.get(
        f"/api/movimientos-cc/{pago_uno['movimiento']['id']}/recibo"
    )
    assert recibo.status_code == 200
    assert recibo.headers["content-type"] == "application/pdf"
    assert recibo.content.startswith(b"%PDF-1.4")
    assert b"Monto: $ 20000.00" in recibo.content
    assert b"Efectivo" in recibo.content
    assert b"Saldo resultante: $ 5000.00" in recibo.content

    # Cierre intermedio: cobrado 20000, deuda 25000, diferencia -5000.
    intermedio = caja.get(f"/api/caja/cierre?fecha={hoy.isoformat()}")
    assert intermedio.status_code == 200, intermedio.text
    data = intermedio.json()
    assert data["cobrado_total"] == "20000.00"
    assert data["por_medio"]["efectivo"] == "20000.00"
    assert Decimal(data["por_medio"]["transferencia"]) == Decimal("0.00")
    assert data["cantidad_pagos"] == 1
    assert data["deuda_generada"] == "25000.00"
    assert data["diferencia_caja"] == "-5000.00"
    assert data["turnos_atendidos"] == 1
    assert len(data["movimientos"]) == 2
    assert len(data["turnos"]) == 1
    assert data["turnos"][0]["id"] == str(turno_id)

    # Cobro del saldo restante y cierre cuadrado.
    segundo = caja.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "5000.00",
            "medio": "transferencia",
            "idempotency_key": "flujo4-pago-2",
        },
    )
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["saldo"] == "0.00"

    final = caja.get(f"/api/caja/cierre?fecha={hoy.isoformat()}")
    assert final.status_code == 200, final.text
    final_data = final.json()
    assert final_data["cobrado_total"] == "25000.00"
    assert final_data["por_medio"]["efectivo"] == "20000.00"
    assert final_data["por_medio"]["transferencia"] == "5000.00"
    assert Decimal(final_data["por_medio"]["mp"]) == Decimal("0.00")
    assert final_data["cantidad_pagos"] == 2
    assert final_data["deuda_generada"] == "25000.00"
    assert final_data["diferencia_caja"] == "0.00"
    assert final_data["turnos_atendidos"] == 1
    assert len(final_data["movimientos"]) == 3

    cuenta = caja.get(f"/api/pacientes/{paciente.id}/cuenta-corriente")
    assert cuenta.status_code == 200
    assert cuenta.json()["saldo"] == "0.00"

    # Matriz de roles sobre caja: odontologo lee y descarga, no cobra.
    odontologo = build_c15_client(stores, principal(roles=("odontologo",)))
    assert (
        odontologo.get(
            f"/api/caja/cierre?fecha={hoy.isoformat()}"
        ).status_code
        == 200
    )
    assert (
        odontologo.get(
            f"/api/movimientos-cc/{pago_uno['movimiento']['id']}/recibo"
        ).status_code
        == 200
    )
    assert (
        odontologo.post(
            f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
            json={"monto": "10.00", "medio": "efectivo"},
        ).status_code
        == 403
    )

    # Asistente sin acceso al cierre ni a la cuenta.
    asistente = build_c15_client(stores, principal(roles=("asistente",)))
    assert asistente.get(f"/api/caja/cierre?fecha={hoy.isoformat()}").status_code == 403
    assert (
        asistente.get(
            f"/api/pacientes/{paciente.id}/cuenta-corriente"
        ).status_code
        == 403
    )
