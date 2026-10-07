"""C-05 catalog routers tests (tasks 2.2/4.1) — RED first.

Real FastAPI app with the REAL catalog routers; auth + store ports are
overridden with fakes (MemoryCatalogStore, no live DB). Verifies CRUD
cycles per resource, pagination, cross-tenant 404s and the RBAC matrix
(write propietario-only, read any staff).
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import catalog as catalog_module
from app.application.auth_service import Principal
from app.application.catalog_store import MemoryCatalogStore, reset_memory_catalog
from app.shared.exceptions import register_exception_handlers

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()

PRESTACION_BODY = {
    "nombre": "Limpieza (ficticia)",
    "duracion_min": 45,
    "buffer_min": 10,
    "precio": "15000.00",
    "anticipacion_min_cancel_hs": 24,
}


def _principal(
    tenant: uuid.UUID = TENANT_A, roles: tuple[str, ...] = ("propietario",)
) -> Principal:
    return Principal(
        sub=f"user-{roles[0]}-ficticio",
        tenant_id=tenant,
        roles=roles,
        email=f"{roles[0]}@demo-ficticia.invalid",
    )


@pytest.fixture()
def client_owner():  # type: ignore[no-untyped-def]
    reset_memory_catalog()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(catalog_module.router, prefix="/api")
    app.dependency_overrides[catalog_module.get_current_principal] = lambda: _principal()
    app.dependency_overrides[catalog_module.get_catalog_store] = (
        lambda: MemoryCatalogStore(tenant_id=TENANT_A)
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    reset_memory_catalog()


def _client_as(roles: tuple[str, ...], tenant: uuid.UUID = TENANT_A) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(catalog_module.router, prefix="/api")
    app.dependency_overrides[catalog_module.get_current_principal] = (
        lambda: _principal(tenant, roles)
    )
    app.dependency_overrides[catalog_module.get_catalog_store] = (
        lambda: MemoryCatalogStore(tenant_id=tenant)
    )
    return TestClient(app, raise_server_exceptions=False)


def test_prestaciones_ciclo_crud_propietario(client_owner: TestClient) -> None:
    """WHEN propietario opera prestaciones THEN 201→200→200→204→404."""
    created = client_owner.post("/api/prestaciones", json=PRESTACION_BODY)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["duracion_min"] == 45

    listed = client_owner.get("/api/prestaciones")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = client_owner.get(f"/api/prestaciones/{pid}")
    assert fetched.status_code == 200

    patched = client_owner.patch(f"/api/prestaciones/{pid}", json={"duracion_min": 50})
    assert patched.status_code == 200
    assert patched.json()["duracion_min"] == 50

    deleted = client_owner.delete(f"/api/prestaciones/{pid}")
    assert deleted.status_code == 204
    assert client_owner.get(f"/api/prestaciones/{pid}").status_code == 404
    assert client_owner.get("/api/prestaciones").json() == []


def test_sillones_ciclo_crud_propietario(client_owner: TestClient) -> None:
    """WHEN propietario opera sillones THEN Box 1 queda disponible (201)."""
    created = client_owner.post("/api/sillones", json={"nombre": "Box 1 (demo)"})
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    assert client_owner.get(f"/api/sillones/{sid}").status_code == 200
    patched = client_owner.patch(f"/api/sillones/{sid}", json={"activo": False})
    assert patched.status_code == 200
    assert patched.json()["activo"] is False
    assert client_owner.delete(f"/api/sillones/{sid}").status_code == 204


def test_profesional_requiere_habilitacion_y_la_guarda(
    client_owner: TestClient,
) -> None:
    """WHEN profesional con 2 prestaciones THEN 201 agendable solo en esas."""
    prest_a = client_owner.post("/api/prestaciones", json=PRESTACION_BODY).json()
    prest_b = client_owner.post(
        "/api/prestaciones",
        json={**PRESTACION_BODY, "nombre": "Consulta (ficticia)", "duracion_min": 30},
    ).json()
    body = {
        "nombre": "Dra. Demo (ficticia)",
        "especialidades": ["Ortodoncia (ficticia)"],
        "prestacion_ids": [prest_a["id"], prest_b["id"]],
    }
    created = client_owner.post("/api/profesionales", json=body)
    assert created.status_code == 201, created.text
    assert sorted(created.json()["prestacion_ids"]) == sorted(
        [prest_a["id"], prest_b["id"]]
    )

    sin_habilitacion = client_owner.post(
        "/api/profesionales", json={"nombre": "Dr. X (ficticio)", "prestacion_ids": []}
    )
    assert sin_habilitacion.status_code == 422


def test_profesional_con_prestacion_ajena_rechazado(
    client_owner: TestClient,
) -> None:
    """WHEN prestacion_id inexistente en tenant THEN 422 (no agendable)."""
    body = {"nombre": "Dr. X (ficticio)", "prestacion_ids": [str(uuid.uuid4())]}
    response = client_owner.post("/api/profesionales", json=body)
    assert response.status_code == 422


def test_bloqueos_ciclo_y_sin_objetivo_422(client_owner: TestClient) -> None:
    """WHEN bloqueo valido THEN 201; sin objetivo THEN 422."""
    prof = client_owner.post(
        "/api/profesionales",
        json={
            "nombre": "Dr. Demo (ficticio)",
            "prestacion_ids": [
                client_owner.post("/api/prestaciones", json=PRESTACION_BODY).json()["id"]
            ],
        },
    ).json()
    body = {
        "profesional_id": prof["id"],
        "inicio": "2026-12-25T09:00:00+00:00",
        "fin": "2026-12-25T17:00:00+00:00",
        "motivo": "feriado",
    }
    created = client_owner.post("/api/bloqueos", json=body)
    assert created.status_code == 201, created.text
    bid = created.json()["id"]
    assert client_owner.get(f"/api/bloqueos/{bid}").status_code == 200

    sin_objetivo = client_owner.post(
        "/api/bloqueos",
        json={
            "inicio": "2026-12-25T09:00:00+00:00",
            "fin": "2026-12-25T17:00:00+00:00",
            "motivo": "feriado",
        },
    )
    assert sin_objetivo.status_code == 422
    assert client_owner.delete(f"/api/bloqueos/{bid}").status_code == 204


def test_paginacion_limit_offset(client_owner: TestClient) -> None:
    """WHEN 3 prestaciones y limit=2 THEN 2+1 (paginacion honrada)."""
    for i in range(3):
        body = {**PRESTACION_BODY, "nombre": f"P-{i} (ficticia)"}
        assert client_owner.post("/api/prestaciones", json=body).status_code == 201
    assert len(client_owner.get("/api/prestaciones?limit=2&offset=0").json()) == 2
    assert len(client_owner.get("/api/prestaciones?limit=2&offset=2").json()) == 1


def test_id_inexistente_404(client_owner: TestClient) -> None:
    """WHEN id desconocido THEN 404 en los 4 recursos (sin fuga)."""
    missing = str(uuid.uuid4())
    assert client_owner.get(f"/api/prestaciones/{missing}").status_code == 404
    assert client_owner.get(f"/api/profesionales/{missing}").status_code == 404
    assert client_owner.get(f"/api/sillones/{missing}").status_code == 404
    assert client_owner.get(f"/api/bloqueos/{missing}").status_code == 404


def test_cross_tenant_por_id_404() -> None:
    """WHEN token tenant B pide id del tenant A THEN 404 sin revelar datos."""
    reset_memory_catalog()
    owner_a = _client_as(("propietario",), TENANT_A)
    created = owner_a.post("/api/prestaciones", json=PRESTACION_BODY)
    assert created.status_code == 201
    pid = created.json()["id"]

    reader_b = _client_as(("propietario",), TENANT_B)
    response = reader_b.get(f"/api/prestaciones/{pid}")
    assert response.status_code == 404
    assert "Limpieza" not in response.text
    assert reader_b.get("/api/prestaciones").json() == []
    reset_memory_catalog()


def test_recepcion_lee_pero_no_escribe() -> None:
    """WHEN recepcion escribe THEN 403 sin efecto; leer THEN 200."""
    reset_memory_catalog()
    owner = _client_as(("propietario",), TENANT_A)
    assert owner.post("/api/prestaciones", json=PRESTACION_BODY).status_code == 201

    recep = _client_as(("recepcion",), TENANT_A)
    assert recep.get("/api/prestaciones").status_code == 200
    assert len(recep.get("/api/prestaciones").json()) == 1
    denied = recep.post("/api/prestaciones", json=PRESTACION_BODY)
    assert denied.status_code == 403
    denied_patch = recep.patch(
        f"/api/prestaciones/{owner.get('/api/prestaciones').json()[0]['id']}",
        json={"duracion_min": 99},
    )
    assert denied_patch.status_code == 403
    denied_delete = recep.delete(
        f"/api/prestaciones/{owner.get('/api/prestaciones').json()[0]['id']}"
    )
    assert denied_delete.status_code == 403
    # Sin efecto lateral: la recepcion no altero nada.
    assert owner.get("/api/prestaciones").json()[0]["duracion_min"] == 45
    reset_memory_catalog()


def test_sin_autenticacion_401() -> None:
    """WHEN sin principal THEN 401 uniforme."""
    from app.api.deps import get_current_principal
    from app.shared.exceptions import AppError

    async def _deny() -> Any:
        raise AppError("unauthorized", 401)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(catalog_module.router, prefix="/api")
    app.dependency_overrides[get_current_principal] = _deny
    app.dependency_overrides[catalog_module.get_current_principal] = _deny
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/prestaciones").status_code == 401


def test_odontologo_lee_pero_no_escribe() -> None:
    """WHEN odontologo escribe THEN 403; leer THEN 200 (triangula matriz)."""
    reset_memory_catalog()
    owner = _client_as(("propietario",), TENANT_A)
    assert owner.post("/api/prestaciones", json=PRESTACION_BODY).status_code == 201
    odonto = _client_as(("odontologo",), TENANT_A)
    assert odonto.get("/api/profesionales").status_code == 200
    assert odonto.post("/api/sillones", json={"nombre": "Box X"}).status_code == 403
    reset_memory_catalog()


def test_asistente_lee_pero_no_borra() -> None:
    """WHEN asistente borra THEN 403; leer bloqueos THEN 200 (triangula)."""
    reset_memory_catalog()
    owner = _client_as(("propietario",), TENANT_A)
    pid = owner.post("/api/prestaciones", json=PRESTACION_BODY).json()["id"]
    asis = _client_as(("asistente",), TENANT_A)
    assert asis.get("/api/bloqueos").status_code == 200
    assert asis.delete(f"/api/prestaciones/{pid}").status_code == 403
    assert owner.get(f"/api/prestaciones/{pid}").status_code == 200
    reset_memory_catalog()
