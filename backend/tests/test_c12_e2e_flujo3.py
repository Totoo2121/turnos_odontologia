"""C-12 task 6.1: E2E Flujo 3 (paciente → HCE → evolucion → derivacion)."""

from __future__ import annotations

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from tests.support_c12 import (
    TENANT_A,
    build_client,
    build_stores,
    principal,
)


def test_flujo3_completo_sin_postgres_ni_red() -> None:
    """WHEN the full clinical flow runs THEN all three actors see the rules."""
    stores = build_stores()
    owner = principal(roles=("propietario",))

    owner_client = build_client(stores, owner)
    paciente = owner_client.post(
        "/api/pacientes",
        json={
            "nombre": "Paciente Flujo 3 Ficticio",
            "telefono": "+5491100000000",
            "dni": "90000050",
            "consentimiento_datos": True,
            "consentimiento_at": "2026-11-14T10:00:00Z",
        },
    )
    assert paciente.status_code == 201
    paciente_id = paciente.json()["id"]

    tratante_usuario = uuid.uuid4()
    tratante_profesional = uuid.uuid4()
    stores.acceso.registrar_profesional(
        tratante_usuario, tratante_profesional
    )
    stores.acceso.registrar_turno(
        TENANT_A, uuid.UUID(paciente_id), tratante_profesional
    )
    tratante = principal(sub=tratante_usuario, roles=("odontologo",))
    tratante_client = build_client(stores, tratante)

    historia = tratante_client.post(
        "/api/historias-clinicas", json={"paciente_id": paciente_id}
    )
    assert historia.status_code == 201, historia.text
    historia_id = historia.json()["id"]

    anamnesis = tratante_client.patch(
        f"/api/historias-clinicas/{historia_id}",
        json={
            "alergias": "Ninguna (ficticia)",
            "medicacion": "Ninguna (ficticia)",
            "antecedentes": "Sin antecedentes (ficticio)",
        },
    )
    assert anamnesis.status_code == 200

    original = tratante_client.post(
        f"/api/historias-clinicas/{historia_id}/evoluciones",
        json={"contenido": "Evolucion original ficticia"},
    )
    assert original.status_code == 201, original.text
    correccion = tratante_client.post(
        f"/api/historias-clinicas/{historia_id}/evoluciones",
        json={
            "contenido": "Correccion ficticia",
            "corrige_evolucion_id": original.json()["id"],
        },
    )
    assert correccion.status_code == 201, correccion.text

    derivado_usuario = uuid.uuid4()
    derivado_profesional = uuid.uuid4()
    stores.acceso.registrar_profesional(
        derivado_usuario, derivado_profesional
    )
    derivado = principal(sub=derivado_usuario, roles=("odontologo",))
    assert (
        build_client(stores, derivado)
        .get(f"/api/historias-clinicas/{historia_id}")
        .status_code
        == 403
    )

    derivacion = owner_client.post(
        f"/api/historias-clinicas/{historia_id}/derivaciones",
        json={
            "hacia_profesional_id": str(derivado_profesional),
            "desde_profesional_id": str(tratante_profesional),
            "motivo": "Derivacion ficticia",
        },
    )
    assert derivacion.status_code == 201, derivacion.text

    derivado_client = build_client(stores, derivado)
    visible = derivado_client.get(f"/api/historias-clinicas/{historia_id}")
    assert visible.status_code == 200
    evoluciones = derivado_client.get(
        f"/api/historias-clinicas/{historia_id}/evoluciones"
    )
    assert evoluciones.status_code == 200
    assert [row["contenido"] for row in evoluciones.json()] == [
        "Evolucion original ficticia",
        "Correccion ficticia",
    ]

    ajeno = build_client(stores, principal(roles=("odontologo",)))
    assert (
        ajeno.get(f"/api/historias-clinicas/{historia_id}").status_code
        == 403
    )
