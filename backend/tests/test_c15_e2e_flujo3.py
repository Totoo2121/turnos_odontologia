"""C-15 task 6.1: E2E Flujo 3 completo (HCE -> odontograma -> presupuesto ->
consentimiento -> plan -> deuda -> cobro -> saldo), sin Postgres ni red.

Datos 100% ficticios. El objetivo es verificar que C-15 cierra el ciclo
administrativo sobre los contratos de C-12/C-13/C-14 sin migracion nueva.
"""

from __future__ import annotations

import datetime
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from app.application.agenda_cobros import AGENDA_TZ
from tests.support_c14 import (
    principal,
    seed_paciente_historia,
    seed_prestacion,
)
from tests.support_c15 import build_c15_client, build_c15_stores


def test_flujo3_hce_invasiva_deuda_y_cobro_hasta_saldo_cero() -> None:
    stores = build_c15_stores()
    paciente, historia = seed_paciente_historia(
        stores.c14, nombre="Paciente Ficticio Flujo 3"
    )
    invasiva = seed_prestacion(
        stores.c14,
        nombre="Cirugia ficticia Flujo 3",
        precio="20000.00",
        requiere_consentimiento=True,
    )
    consulta = seed_prestacion(
        stores.c14,
        nombre="Consulta ficticia Flujo 3",
        precio="5000.25",
        requiere_consentimiento=False,
    )
    owner = principal()
    client = build_c15_client(stores, owner)

    # HCE: anamnesis + evolucion append-only + correccion como nueva entrada.
    anamnesis = client.patch(
        f"/api/historias-clinicas/{historia.id}",
        json={
            "alergias": "Ninguna (ficticio)",
            "medicacion": "Ninguna (ficticio)",
        },
    )
    assert anamnesis.status_code == 200, anamnesis.text

    evolucion = client.post(
        f"/api/historias-clinicas/{historia.id}/evoluciones",
        json={"contenido": "Evolucion ficticia inicial del Flujo 3."},
    )
    assert evolucion.status_code == 201, evolucion.text
    evolucion_id = evolucion.json()["id"]

    correccion = client.post(
        f"/api/historias-clinicas/{historia.id}/evoluciones",
        json={
            "contenido": "Correccion ficticia del Flujo 3.",
            "corrige_evolucion_id": evolucion_id,
        },
    )
    assert correccion.status_code == 201, correccion.text
    evoluciones = client.get(
        f"/api/historias-clinicas/{historia.id}/evoluciones"
    ).json()
    assert [row["id"] for row in evoluciones] == [
        evolucion_id,
        correccion.json()["id"],
    ]
    assert evoluciones[0]["contenido"].startswith("Evolucion ficticia")

    # Odontograma: evento caries/oclusal sobre la pieza 16.
    evento = client.post(
        f"/api/odontogramas/{historia.id}/eventos",
        json={
            "pieza_fdi": 16,
            "estado": "caries",
            "superficie": "oclusal",
        },
    )
    assert evento.status_code == 201, evento.text

    # Presupuesto en dos etapas: 20000.00 invasiva + 5000.25 consulta.
    created = client.post(
        "/api/presupuestos",
        json={
            "paciente_id": str(paciente.id),
            "historia_clinica_id": str(historia.id),
            "observaciones": "Presupuesto ficticio Flujo 3.",
            "items": [
                {
                    "prestacion_id": str(invasiva.id),
                    "pieza_fdi": 16,
                    "superficie": "oclusal",
                    "etapa": 1,
                },
                {"prestacion_id": str(consulta.id), "etapa": 2},
            ],
        },
    )
    assert created.status_code == 201, created.text
    budget = created.json()
    assert budget["total"] == "25000.25"
    assert budget["moneda"] == "ARS"
    budget_id = budget["id"]

    assert client.post(f"/api/presupuestos/{budget_id}/enviar").status_code == 200

    blocked = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"] == "consentimiento_requerido"
    assert (
        client.get(f"/api/presupuestos/{budget_id}").json()["estado"]
        == "enviado"
    )
    assert client.get(
        f"/api/pacientes/{paciente.id}/cuenta-corriente"
    ).json()["saldo"] == "0.00"

    consent = client.post(
        "/api/consentimientos",
        json={
            "historia_clinica_id": str(historia.id),
            "tipo": "invasivo",
            "texto": "Texto ficticio de consentimiento informado Flujo 3.",
            "texto_version": "c15-e2e-flujo3-1",
            "firmante_nombre": "Firmante Ficticio Flujo 3",
            "firmante_dni": "90000015",
            "plan_invasivo": True,
        },
    )
    assert consent.status_code == 201, consent.text

    accepted = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert accepted.status_code == 200, accepted.text
    aceptado = accepted.json()
    assert aceptado["estado"] == "aceptado"
    assert aceptado["plan_id"] is not None
    assert aceptado["movimiento_id"] is not None

    plan = client.get(f"/api/planes-tratamiento/{aceptado['plan_id']}")
    assert plan.status_code == 200, plan.text
    plan_data = plan.json()
    assert plan_data["etapas"] == 2
    assert plan_data["etapa_actual"] == 1
    assert plan_data["total"] == "25000.25"
    assert [etapa["etapa"] for etapa in plan_data["detalle"]] == [1, 2]

    # Deuda exacta: un solo debito por el total del plan aceptado.
    cuenta = client.get(f"/api/pacientes/{paciente.id}/cuenta-corriente")
    assert cuenta.status_code == 200, cuenta.text
    assert cuenta.json()["saldo"] == "25000.25"
    assert [mov["tipo"] for mov in cuenta.json()["movimientos"]] == ["debito"]

    # Cobro parcial idempotente y cobro del saldo restante.
    primero = client.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "10000.00",
            "medio": "efectivo",
            "idempotency_key": "flujo3-pago-1",
            "descripcion": "Pago parcial ficticio Flujo 3",
        },
    )
    assert primero.status_code == 201, primero.text
    pago_uno = primero.json()
    assert pago_uno["saldo"] == "15000.25"
    assert pago_uno["referencia"] == "pago:efectivo:flujo3-pago-1"

    repetido = client.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "10000.00",
            "medio": "efectivo",
            "idempotency_key": "flujo3-pago-1",
        },
    )
    assert repetido.status_code == 201
    assert repetido.json()["movimiento"]["id"] == pago_uno["movimiento"]["id"]
    assert repetido.json()["saldo"] == "15000.25"

    recibo = client.get(
        f"/api/movimientos-cc/{pago_uno['movimiento']['id']}/recibo"
    )
    assert recibo.status_code == 200
    assert recibo.headers["content-type"] == "application/pdf"
    assert recibo.content.startswith(b"%PDF-1.4")
    assert b"10000.00" in recibo.content
    assert b"Efectivo" in recibo.content

    segundo = client.post(
        f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
        json={
            "monto": "15000.25",
            "medio": "transferencia",
            "idempotency_key": "flujo3-pago-2",
        },
    )
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["saldo"] == "0.00"

    final = client.get(f"/api/pacientes/{paciente.id}/cuenta-corriente").json()
    assert final["saldo"] == "0.00"
    assert len(final["movimientos"]) == 3

    cierre = client.get(
        "/api/caja/cierre"
        f"?fecha={datetime.datetime.now(AGENDA_TZ).date().isoformat()}"
    )
    assert cierre.status_code == 200, cierre.text
    cierre_data = cierre.json()
    assert cierre_data["cobrado_total"] == "25000.25"
    assert cierre_data["por_medio"]["efectivo"] == "10000.00"
    assert cierre_data["por_medio"]["transferencia"] == "15000.25"
    assert cierre_data["cantidad_pagos"] == 2
    assert cierre_data["deuda_generada"] == "25000.25"
    assert cierre_data["diferencia_caja"] == "0.00"

    # Matriz de roles: recepcion cobra y consulta, pero no firma clinica.
    recepcion = build_c15_client(stores, principal(roles=("recepcion",)))
    assert (
        recepcion.get(
            f"/api/pacientes/{paciente.id}/cuenta-corriente"
        ).status_code
        == 200
    )
    assert (
        recepcion.get(
            f"/api/movimientos-cc/{pago_uno['movimiento']['id']}/recibo"
        ).status_code
        == 200
    )
    assert (
        recepcion.post(
            "/api/presupuestos",
            json={"paciente_id": str(paciente.id), "items": []},
        ).status_code
        == 403
    )
    assert (
        recepcion.post(
            "/api/consentimientos",
            json={
                "historia_clinica_id": str(historia.id),
                "tipo": "invasivo",
                "texto": "Texto ficticio no autorizado.",
                "texto_version": "c15-e2e-flujo3-2",
                "firmante_nombre": "Firmante Ficticio",
                "plan_invasivo": True,
            },
        ).status_code
        == 403
    )
    assert (
        recepcion.get(
            f"/api/historias-clinicas/{historia.id}/evoluciones"
        ).status_code
        == 403
    )

    # Odontologo no tratante: sin datos clinicos ni plan.
    ajeno = build_c15_client(stores, principal(roles=("odontologo",)))
    assert ajeno.get(f"/api/presupuestos/{budget_id}").status_code == 403
    assert (
        ajeno.get(
            "/api/planes-tratamiento",
            params={"paciente_id": str(paciente.id)},
        ).status_code
        == 403
    )
    assert (
        ajeno.get(
            f"/api/historias-clinicas/{historia.id}/evoluciones"
        ).status_code
        == 403
    )
    # Odontologo si puede leer caja y recibo, pero no cobrar.
    assert (
        ajeno.get(f"/api/pacientes/{paciente.id}/cuenta-corriente").status_code
        == 200
    )
    assert (
        ajeno.post(
            f"/api/pacientes/{paciente.id}/cuenta-corriente/pagos",
            json={"monto": "10.00", "medio": "efectivo"},
        ).status_code
        == 403
    )

    # Asistente sin acceso al modulo de cobros.
    asistente = build_c15_client(stores, principal(roles=("asistente",)))
    assert (
        asistente.get(
            f"/api/pacientes/{paciente.id}/cuenta-corriente"
        ).status_code
        == 403
    )
    assert (
        asistente.get(
            f"/api/movimientos-cc/{uuid.uuid4()}/recibo"
        ).status_code
        == 403
    )
    assert (
        asistente.get(
            f"/api/caja/cierre?fecha={cierre_data['fecha']}"
        ).status_code
        == 403
    )
