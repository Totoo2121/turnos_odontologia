"""C-05 huecos endpoint tests (task 3.2) — RED first.

Integration over the REAL catalog router + shared memory store (no live
DB): propietario seeds (prestacion + profesional + bloqueo), staff queries
``GET /api/agenda/huecos`` and gets only valid holes.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import catalog as catalog_module
from app.application.auth_service import Principal
from app.application.catalog_store import MemoryCatalogStore, reset_memory_catalog
from app.shared.exceptions import register_exception_handlers

TENANT = uuid.uuid4()
DAY = "2026-12-25"


def _app_for(roles: tuple[str, ...]) -> FastAPI:
    principal = Principal(
        sub=f"user-{roles[0]}-ficticio",
        tenant_id=TENANT,
        roles=roles,
        email=f"{roles[0]}@demo-ficticia.invalid",
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(catalog_module.router, prefix="/api")
    app.dependency_overrides[catalog_module.get_current_principal] = lambda: principal
    app.dependency_overrides[catalog_module.get_catalog_store] = (
        lambda: MemoryCatalogStore(tenant_id=TENANT)
    )
    return app


@pytest.fixture()
def clients():  # type: ignore[no-untyped-def]
    """Owner + recepcion clients sharing the same memory store."""
    reset_memory_catalog()
    with TestClient(_app_for(("propietario",)), raise_server_exceptions=False) as owner:
        with TestClient(
            _app_for(("recepcion",)), raise_server_exceptions=False
        ) as staff:
            yield owner, staff
    reset_memory_catalog()


def _seed(owner: TestClient) -> tuple[str, str]:
    prest_id = owner.post(
        "/api/prestaciones",
        json={"nombre": "Consulta 30' (ficticia)", "duracion_min": 30},
    ).json()["id"]
    prof_id = owner.post(
        "/api/profesionales",
        json={"nombre": "Dr. Demo (ficticio)", "prestacion_ids": [prest_id]},
    ).json()["id"]
    bloqueo = owner.post(
        "/api/bloqueos",
        json={
            "profesional_id": prof_id,
            "inicio": f"{DAY}T12:00:00+00:00",
            "fin": f"{DAY}T13:00:00+00:00",
            "motivo": "feriado",
        },
    )
    assert bloqueo.status_code == 201, bloqueo.text
    return prof_id, prest_id


def test_huecos_descuentan_bloqueo(clients: tuple[TestClient, TestClient]) -> None:
    """WHEN bloqueo 12:00-13:00 THEN huecos 09-13 omiten 12:00/12:30."""
    owner, staff = clients
    prof_id, prest_id = _seed(owner)
    response = staff.get(
        "/api/agenda/huecos",
        params={
            "profesional_id": prof_id,
            "prestacion_id": prest_id,
            "desde": f"{DAY}T09:00:00+00:00",
            "hasta": f"{DAY}T13:00:00+00:00",
        },
    )
    assert response.status_code == 200, response.text
    inicios = [h["inicio"][11:16] for h in response.json()["huecos"]]
    assert inicios == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]


def test_huecos_profesional_inexistente_404(
    clients: tuple[TestClient, TestClient],
) -> None:
    """WHEN profesional ajeno/inexistente THEN 404 (sin fuga)."""
    owner, staff = clients
    _, prest_id = _seed(owner)
    response = staff.get(
        "/api/agenda/huecos",
        params={
            "profesional_id": str(uuid.uuid4()),
            "prestacion_id": prest_id,
            "desde": f"{DAY}T09:00:00+00:00",
            "hasta": f"{DAY}T13:00:00+00:00",
        },
    )
    assert response.status_code == 404


def test_huecos_prestacion_no_habilitada_422(
    clients: tuple[TestClient, TestClient],
) -> None:
    """WHEN prestacion no habilitada THEN 422 (no agendable ahi)."""
    owner, staff = clients
    prof_id, _ = _seed(owner)
    otra = owner.post(
        "/api/prestaciones",
        json={"nombre": "Corona (ficticia)", "duracion_min": 60},
    ).json()["id"]
    response = staff.get(
        "/api/agenda/huecos",
        params={
            "profesional_id": prof_id,
            "prestacion_id": otra,
            "desde": f"{DAY}T09:00:00+00:00",
            "hasta": f"{DAY}T13:00:00+00:00",
        },
    )
    assert response.status_code == 422


def test_huecos_ventana_invertida_400(
    clients: tuple[TestClient, TestClient],
) -> None:
    """WHEN hasta<=desde THEN 400 (ventana invalida)."""
    owner, staff = clients
    prof_id, prest_id = _seed(owner)
    response = staff.get(
        "/api/agenda/huecos",
        params={
            "profesional_id": prof_id,
            "prestacion_id": prest_id,
            "desde": f"{DAY}T13:00:00+00:00",
            "hasta": f"{DAY}T09:00:00+00:00",
        },
    )
    assert response.status_code == 400


def test_huecos_profesional_inactivo_vacio(
    clients: tuple[TestClient, TestClient],
) -> None:
    """WHEN profesional inactivo THEN [] (no se ofrece, 2do input)."""
    owner, staff = clients
    prof_id, prest_id = _seed(owner)
    assert (
        owner.patch(f"/api/profesionales/{prof_id}", json={"activo": False}).status_code
        == 200
    )
    response = staff.get(
        "/api/agenda/huecos",
        params={
            "profesional_id": prof_id,
            "prestacion_id": prest_id,
            "desde": f"{DAY}T09:00:00+00:00",
            "hasta": f"{DAY}T13:00:00+00:00",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"huecos": []}
