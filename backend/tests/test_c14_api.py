"""C-14 task 5: HTTP contract over the real routers (memory stores)."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import presupuestos as presupuestos_api
from app.shared.exceptions import register_exception_handlers
from tests.support_c14 import (
    TENANT_B,
    build_full_client,
    build_stores,
    principal,
    seed_paciente_historia,
    seed_prestacion,
)


def _setup():
    stores = build_stores()
    paciente, historia = seed_paciente_historia(stores)
    prestacion = seed_prestacion(
        stores,
        nombre="Limpieza ficticia",
        precio="15000.50",
        requiere_consentimiento=False,
    )
    return stores, paciente, historia, prestacion


def _payload(paciente_id, prestacion_id, **extra):  # type: ignore[no-untyped-def]
    body = {
        "paciente_id": str(paciente_id),
        "items": [
            {
                "prestacion_id": str(prestacion_id),
                "cantidad": 2,
                "pieza_fdi": 16,
                "superficie": "oclusal",
            }
        ],
    }
    body.update(extra)
    return body


def test_create_and_read_budget() -> None:
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    response = client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["estado"] == "borrador"
    assert data["moneda"] == "ARS"
    assert data["total"] == "30001.00"
    assert len(data["items"]) == 1
    assert data["items"][0]["pieza_fdi"] == 16

    detail = client.get(f"/api/presupuestos/{data['id']}")
    assert detail.status_code == 200
    assert detail.json()["items"][0]["importe"] == "30001.00"

    listed = client.get(
        "/api/presupuestos", params={"paciente_id": str(paciente.id)}
    )
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [data["id"]]


def test_extra_field_and_foreign_currency_are_422() -> None:
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    extra = client.post(
        "/api/presupuestos",
        json=_payload(paciente.id, prestacion.id, moneda_personalizada="USD"),
    )
    assert extra.status_code == 422
    moneda = client.post(
        "/api/presupuestos",
        json=_payload(paciente.id, prestacion.id, moneda="USD"),
    )
    assert moneda.status_code == 422
    assert not stores.presupuestos._rows


def test_invalid_fdi_and_surface_are_422() -> None:
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    for item in (
        {"prestacion_id": str(prestacion.id), "pieza_fdi": 49},
        {
            "prestacion_id": str(prestacion.id),
            "superficie": "oclusal",
        },
        {
            "prestacion_id": str(prestacion.id),
            "pieza_fdi": 16,
            "superficie": "inventada",
        },
    ):
        response = client.post(
            "/api/presupuestos",
            json={"paciente_id": str(paciente.id), "items": [item]},
        )
        assert response.status_code == 422, response.text
    assert not stores.presupuestos._rows


def test_roles_and_clinical_access() -> None:
    stores, paciente, _historia, prestacion = _setup()
    recepcion = build_full_client(
        stores, principal(roles=("recepcion",))
    )
    assert (
        recepcion.post(
            "/api/presupuestos",
            json=_payload(paciente.id, prestacion.id),
        ).status_code
        == 403
    )
    ajeno = build_full_client(stores, principal(roles=("odontologo",)))
    assert (
        ajeno.post(
            "/api/presupuestos",
            json=_payload(paciente.id, prestacion.id),
        ).status_code
        == 403
    )


def test_cross_tenant_read_is_404() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    client = build_full_client(stores, owner)
    created = client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    ).json()
    other = build_full_client(stores, principal(tenant_id=TENANT_B))
    assert other.get(f"/api/presupuestos/{created['id']}").status_code == 404
    assert (
        other.get(
            "/api/presupuestos", params={"paciente_id": str(paciente.id)}
        ).status_code
        == 404
    )


def test_item_crud_and_total_recalculation() -> None:
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    created = client.post(
        "/api/presupuestos",
        json={"paciente_id": str(paciente.id), "items": []},
    ).json()
    budget_id = created["id"]

    added = client.post(
        f"/api/presupuestos/{budget_id}/items",
        json={
            "prestacion_id": str(prestacion.id),
            "precio_unitario": "1000.00",
        },
    )
    assert added.status_code == 201
    assert added.json()["total"] == "1000.00"
    item_id = added.json()["items"][0]["id"]

    patched = client.patch(
        f"/api/presupuestos/{budget_id}/items/{item_id}",
        json={"cantidad": 3},
    )
    assert patched.status_code == 200
    assert patched.json()["total"] == "3000.00"

    cleared = client.patch(
        f"/api/presupuestos/{budget_id}/items/{item_id}",
        json={"pieza_fdi": None, "superficie": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["items"][0]["pieza_fdi"] is None

    removed = client.delete(
        f"/api/presupuestos/{budget_id}/items/{item_id}"
    )
    assert removed.status_code == 200
    assert removed.json()["total"] == "0.00"


def test_transitions_and_acceptance_response() -> None:
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    created = client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    ).json()
    budget_id = created["id"]

    invalid = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert invalid.status_code == 409

    sent = client.post(f"/api/presupuestos/{budget_id}/enviar")
    assert sent.status_code == 200
    assert sent.json()["estado"] == "enviado"
    assert sent.json()["enviado_at"] is not None

    accepted = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert accepted.status_code == 200, accepted.text
    data = accepted.json()
    assert data["estado"] == "aceptado"
    assert data["plan_id"] is not None
    assert data["movimiento_id"] is not None

    repeated = client.post(f"/api/presupuestos/{budget_id}/aceptar")
    assert repeated.status_code == 200
    assert repeated.json()["plan_id"] == data["plan_id"]
    assert repeated.json()["movimiento_id"] == data["movimiento_id"]

    plans = client.get(
        "/api/planes-tratamiento", params={"paciente_id": str(paciente.id)}
    )
    assert plans.status_code == 200
    assert len(plans.json()) == 1
    plan = client.get(f"/api/planes-tratamiento/{data['plan_id']}")
    assert plan.status_code == 200
    assert plan.json()["etapas"] == 1
    assert len(plan.json()["detalle"]) == 1


def test_rejected_budget_stays_without_debt() -> None:
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    budget_id = client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    ).json()["id"]
    client.post(f"/api/presupuestos/{budget_id}/enviar")
    rejected = client.post(f"/api/presupuestos/{budget_id}/rechazar")
    assert rejected.status_code == 200
    assert rejected.json()["estado"] == "rechazado"
    assert not stores.movimientos._rows


def test_delete_only_in_draft() -> None:
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    budget_id = client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    ).json()["id"]
    assert client.delete(f"/api/presupuestos/{budget_id}").status_code == 204

    otro = client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    ).json()["id"]
    client.post(f"/api/presupuestos/{otro}/enviar")
    assert client.delete(f"/api/presupuestos/{otro}").status_code == 409


def test_cuenta_corriente_contract_and_roles() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner_client = build_full_client(stores, principal())
    budget_id = owner_client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    ).json()["id"]
    owner_client.post(f"/api/presupuestos/{budget_id}/enviar")
    owner_client.post(f"/api/presupuestos/{budget_id}/aceptar")

    recepcion = build_full_client(
        stores, principal(roles=("recepcion",))
    )
    response = recepcion.get(
        f"/api/pacientes/{paciente.id}/cuenta-corriente"
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) >= {"moneda", "saldo", "movimientos"}
    assert data["moneda"] == "ARS"
    assert data["saldo"] == "30001.00"
    assert len(data["movimientos"]) == 1

    asistente = build_full_client(
        stores, principal(roles=("asistente",))
    )
    assert (
        asistente.get(
            f"/api/pacientes/{paciente.id}/cuenta-corriente"
        ).status_code
        == 403
    )

    other = build_full_client(stores, principal(tenant_id=TENANT_B))
    assert (
        other.get(
            f"/api/pacientes/{paciente.id}/cuenta-corriente"
        ).status_code
        == 404
    )


def test_budget_routes_require_authentication() -> None:
    """WHEN the router is exposed without overrides THEN JWT is mandatory."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(presupuestos_api.router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)
    for path in (
        "/api/presupuestos",
        f"/api/presupuestos/{uuid.uuid4()}",
        f"/api/planes-tratamiento/{uuid.uuid4()}",
        f"/api/pacientes/{uuid.uuid4()}/cuenta-corriente",
    ):
        assert client.get(path).status_code == 401


def test_money_is_serialized_as_decimal_string() -> None:
    """WHEN a budget is read THEN money keeps exact cents (no float drift)."""
    stores, paciente, _historia, prestacion = _setup()
    client = build_full_client(stores, principal())
    data = client.post(
        "/api/presupuestos", json=_payload(paciente.id, prestacion.id)
    ).json()
    assert Decimal(data["total"]) == Decimal("30001.00")
    assert data["items"][0]["precio_unitario"] == "15000.50"
