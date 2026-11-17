"""C-14 task 6.1: E2E Flujo 3 (HCE -> odontograma -> presupuesto -> plan)."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from tests.support_c14 import (
    build_full_client,
    build_stores,
    principal,
    seed_paciente_historia,
    seed_prestacion,
)


def test_flujo3_invasive_budget_to_exact_debt() -> None:
    stores = build_stores()
    paciente, historia = seed_paciente_historia(stores)
    invasiva = seed_prestacion(
        stores,
        nombre="Cirugia ficticia",
        precio="20000.00",
        requiere_consentimiento=True,
    )
    consulta = seed_prestacion(
        stores,
        nombre="Consulta ficticia",
        precio="5000.25",
        requiere_consentimiento=False,
    )
    owner = principal()
    client = build_full_client(stores, owner)

    evento = client.post(
        f"/api/odontogramas/{historia.id}/eventos",
        json={
            "pieza_fdi": 16,
            "estado": "caries",
            "superficie": "oclusal",
        },
    )
    assert evento.status_code == 201, evento.text

    created = client.post(
        "/api/presupuestos",
        json={
            "paciente_id": str(paciente.id),
            "historia_clinica_id": str(historia.id),
            "items": [
                {
                    "prestacion_id": str(invasiva.id),
                    "pieza_fdi": 16,
                    "superficie": "oclusal",
                    "etapa": 1,
                },
                {
                    "prestacion_id": str(consulta.id),
                    "etapa": 2,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    budget = created.json()
    budget_id = budget["id"]
    assert budget["total"] == "25000.25"
    assert budget["moneda"] == "ARS"

    assert client.post(f"/api/presupuestos/{budget_id}/enviar").status_code == 200

    blocked = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"] == "consentimiento_requerido"
    assert (
        client.get(f"/api/presupuestos/{budget_id}").json()["estado"]
        == "enviado"
    )

    consent = client.post(
        "/api/consentimientos",
        json={
            "historia_clinica_id": str(historia.id),
            "tipo": "invasivo",
            "texto": "Texto ficticio de consentimiento informado C-14.",
            "texto_version": "c14-e2e-1",
            "firmante_nombre": "Paciente Ficticio C-14",
            "plan_invasivo": True,
        },
    )
    assert consent.status_code == 201, consent.text

    accepted = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert accepted.status_code == 200, accepted.text
    data = accepted.json()
    assert data["estado"] == "aceptado"
    assert data["plan_id"] is not None
    assert data["movimiento_id"] is not None

    plan = client.get(f"/api/planes-tratamiento/{data['plan_id']}")
    assert plan.status_code == 200
    plan_data = plan.json()
    assert plan_data["etapas"] == 2
    assert plan_data["etapa_actual"] == 1
    assert plan_data["total"] == "25000.25"
    assert [etapa["etapa"] for etapa in plan_data["detalle"]] == [1, 2]

    recepcion = build_full_client(stores, principal(roles=("recepcion",)))
    cuenta = recepcion.get(
        f"/api/pacientes/{paciente.id}/cuenta-corriente"
    )
    assert cuenta.status_code == 200
    assert cuenta.json()["saldo"] == "25000.25"
    assert len(cuenta.json()["movimientos"]) == 1
    assert cuenta.json()["movimientos"][0]["tipo"] == "debito"

    # Reception never quotes; a non-treating professional never sees the HCE.
    assert (
        recepcion.post(
            "/api/presupuestos",
            json={"paciente_id": str(paciente.id), "items": []},
        ).status_code
        == 403
    )
    ajeno = build_full_client(stores, principal(roles=("odontologo",)))
    assert (
        ajeno.get(f"/api/presupuestos/{budget_id}").status_code == 403
    )
    assert (
        ajeno.get(
            "/api/planes-tratamiento", params={"paciente_id": str(paciente.id)}
        ).status_code
        == 403
    )
