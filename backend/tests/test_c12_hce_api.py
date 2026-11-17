"""C-12 tasks 3.2/4.3/5.2: HCE HTTP surface + clinical visibility."""

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

PACIENTE = {
    "nombre": "Paciente Ficticio",
    "telefono": "+5491100000000",
    "dni": "90000040",
}


def _paciente(stores, who=None) -> str:  # type: ignore[no-untyped-def]
    client = build_client(stores, who or principal())
    response = client.post("/api/pacientes", json=PACIENTE)
    assert response.status_code == 201
    return response.json()["id"]


def _historia(stores, paciente_id: str, who) -> str:  # type: ignore[no-untyped-def]
    client = build_client(stores, who)
    response = client.post(
        "/api/historias-clinicas", json={"paciente_id": paciente_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _tratante(stores, paciente_id: str):  # type: ignore[no-untyped-def]
    usuario_id = uuid.uuid4()
    profesional_id = uuid.uuid4()
    stores.acceso.registrar_profesional(usuario_id, profesional_id)
    stores.acceso.registrar_turno(TENANT_A, uuid.UUID(paciente_id), profesional_id)
    return principal(sub=usuario_id, roles=("odontologo",)), profesional_id


def test_owner_opens_history_idempotently() -> None:
    """WHEN owner opens twice THEN the same history id is returned."""
    stores = build_stores()
    owner = principal(roles=("propietario",))
    paciente_id = _paciente(stores, owner)
    primera = _historia(stores, paciente_id, owner)
    segunda = _historia(stores, paciente_id, owner)
    assert primera == segunda


def test_recepcion_cannot_open_history() -> None:
    """WHEN reception opens HCE THEN 403 (RN-SE-03)."""
    stores = build_stores()
    paciente_id = _paciente(stores, principal())
    recepcion = principal(roles=("recepcion",))
    client = build_client(stores, recepcion)
    response = client.post(
        "/api/historias-clinicas", json={"paciente_id": paciente_id}
    )
    assert response.status_code == 403


def test_unrelated_professional_gets_403() -> None:
    """WHEN odontologo has no turno/derivation THEN 403 (RN-SE-02)."""
    stores = build_stores()
    paciente_id = _paciente(stores)
    ajeno = principal(roles=("odontologo",))
    client = build_client(stores, ajeno)
    response = client.post(
        "/api/historias-clinicas", json={"paciente_id": paciente_id}
    )
    assert response.status_code == 403


def test_treating_professional_reads_and_writes_evolutions() -> None:
    """WHEN treating professional writes THEN evolution is listed."""
    stores = build_stores()
    paciente_id = _paciente(stores)
    treating, profesional_id = _tratante(stores, paciente_id)
    historia_id = _historia(stores, paciente_id, treating)
    client = build_client(stores, treating)

    created = client.post(
        f"/api/historias-clinicas/{historia_id}/evoluciones",
        json={"contenido": "Control ficticio"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["autor_profesional_id"] == str(profesional_id)

    listed = client.get(
        f"/api/historias-clinicas/{historia_id}/evoluciones"
    )
    assert listed.status_code == 200
    assert [row["contenido"] for row in listed.json()] == [
        "Control ficticio"
    ]


def test_recepcion_cannot_list_evolutions() -> None:
    """WHEN reception lists evolutions THEN 403."""
    stores = build_stores()
    paciente_id = _paciente(stores)
    historia_id = _historia(stores, paciente_id, principal())
    recepcion = principal(roles=("recepcion",))
    client = build_client(stores, recepcion)
    response = client.get(
        f"/api/historias-clinicas/{historia_id}/evoluciones"
    )
    assert response.status_code == 403


def test_no_destructive_evolution_endpoints() -> None:
    """WHEN PUT/DELETE are attempted THEN no route exists (404/405)."""
    stores = build_stores()
    paciente_id = _paciente(stores)
    historia_id = _historia(stores, paciente_id, principal())
    client = build_client(stores, principal())
    evolucion_id = uuid.uuid4()
    put = client.put(
        f"/api/historias-clinicas/{historia_id}/evoluciones/{evolucion_id}",
        json={"contenido": "x"},
    )
    delete = client.delete(
        f"/api/historias-clinicas/{historia_id}/evoluciones/{evolucion_id}"
    )
    assert put.status_code in (404, 405)
    assert delete.status_code in (404, 405)


def test_anamnesis_patch_by_owner() -> None:
    """WHEN owner patches anamnesis THEN values are returned."""
    stores = build_stores()
    paciente_id = _paciente(stores)
    historia_id = _historia(stores, paciente_id, principal())
    client = build_client(stores, principal())
    response = client.patch(
        f"/api/historias-clinicas/{historia_id}",
        json={"alergias": "Penicilina (ficticia)"},
    )
    assert response.status_code == 200
    assert response.json()["alergias"] == "Penicilina (ficticia)"


def test_derivation_grants_visibility() -> None:
    """WHEN owner derives THEN the recipient can read the history."""
    stores = build_stores()
    owner = principal()
    paciente_id = _paciente(stores, owner)
    historia_id = _historia(stores, paciente_id, owner)

    destinatario_usuario = uuid.uuid4()
    destinatario_profesional = uuid.uuid4()
    stores.acceso.registrar_profesional(
        destinatario_usuario, destinatario_profesional
    )
    destinatario = principal(
        sub=destinatario_usuario, roles=("odontologo",)
    )
    denied = build_client(stores, destinatario).get(
        f"/api/historias-clinicas/{historia_id}"
    )
    assert denied.status_code == 403

    created = build_client(stores, owner).post(
        f"/api/historias-clinicas/{historia_id}/derivaciones",
        json={
            "hacia_profesional_id": str(destinatario_profesional),
            "motivo": "Interconsulta ficticia",
        },
    )
    assert created.status_code == 201, created.text

    allowed = build_client(stores, destinatario).get(
        f"/api/historias-clinicas/{historia_id}"
    )
    assert allowed.status_code == 200
    assert allowed.json()["id"] == historia_id
