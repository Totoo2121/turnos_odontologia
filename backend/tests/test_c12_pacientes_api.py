"""C-12 task 2.3: pacientes CRUD RBAC + pagination over the real router."""

from __future__ import annotations

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from tests.support_c12 import (
    TENANT_A,
    TENANT_B,
    build_client,
    build_stores,
    principal,
)

PACIENTE = {
    "nombre": "Paciente Ficticio",
    "telefono": "+5491100000000",
    "dni": "90000020",
}


def test_owner_creates_reads_and_lists() -> None:
    """WHEN owner creates a patient THEN reads and lists it."""
    stores = build_stores()
    client = build_client(stores, principal(roles=("propietario",)))
    created = client.post("/api/pacientes", json=PACIENTE)
    assert created.status_code == 201
    paciente_id = created.json()["id"]
    assert client.get(f"/api/pacientes/{paciente_id}").status_code == 200
    listed = client.get("/api/pacientes")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [paciente_id]


def test_cross_tenant_read_is_404() -> None:
    """WHEN tenant B reads a tenant-A patient THEN 404 (no leak)."""
    stores = build_stores()
    owner_a = build_client(stores, principal(tenant_id=TENANT_A))
    paciente_id = owner_a.post("/api/pacientes", json=PACIENTE).json()["id"]

    owner_b = build_client(stores, principal(tenant_id=TENANT_B))
    assert owner_b.get(f"/api/pacientes/{paciente_id}").status_code == 404


@pytest.mark.parametrize("roles", [("recepcion",), ("asistente",)])
def test_staff_can_create_patients(roles: tuple[str, ...]) -> None:
    """WHEN reception/assistant creates a patient THEN 201."""
    stores = build_stores()
    client = build_client(stores, principal(roles=roles))
    assert client.post("/api/pacientes", json=PACIENTE).status_code == 201


def test_delete_is_owner_only() -> None:
    """WHEN odontologo deletes THEN 403; owner deletes clean patient 204."""
    stores = build_stores()
    owner = build_client(stores, principal(roles=("propietario",)))
    paciente_id = owner.post(
        "/api/pacientes", json={**PACIENTE, "dni": "90000021"}
    ).json()["id"]

    odontologo = build_client(stores, principal(roles=("odontologo",)))
    assert (
        odontologo.delete(f"/api/pacientes/{paciente_id}").status_code == 403
    )
    assert owner.delete(f"/api/pacientes/{paciente_id}").status_code == 204


def test_duplicate_dni_returns_409() -> None:
    """WHEN the same DNI is posted twice THEN 409."""
    stores = build_stores()
    client = build_client(stores, principal())
    assert client.post("/api/pacientes", json=PACIENTE).status_code == 201
    duplicate = client.post(
        "/api/pacientes", json={**PACIENTE, "nombre": "Otro Ficticio"}
    )
    assert duplicate.status_code == 409


def test_consent_without_date_returns_422() -> None:
    """WHEN consent=True without a date THEN 422."""
    stores = build_stores()
    client = build_client(stores, principal())
    response = client.post(
        "/api/pacientes",
        json={**PACIENTE, "consentimiento_datos": True},
    )
    assert response.status_code == 422


def test_pagination_limits_results() -> None:
    """WHEN limit/offset are sent THEN the slice is honored."""
    stores = build_stores()
    client = build_client(stores, principal())
    for index in range(4):
        client.post(
            "/api/pacientes",
            json={
                "nombre": f"Paciente {index} Ficticio",
                "telefono": "+5491100000000",
                "dni": f"9000003{index}",
            },
        )
    page = client.get("/api/pacientes", params={"limit": 2, "offset": 1})
    assert page.status_code == 200
    assert len(page.json()) == 2


def test_unknown_patient_returns_404() -> None:
    """WHEN the id does not exist THEN 404."""
    stores = build_stores()
    client = build_client(stores, principal())
    assert client.get(f"/api/pacientes/{uuid.uuid4()}").status_code == 404
