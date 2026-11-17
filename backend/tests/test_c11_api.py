"""C-11 task 5.1: notification API (reception alerts + templates) RBAC."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import notificaciones as api_module
from app.application.auth_service import Principal
from app.application.notificaciones import (
    CANAL_INTERNO,
    CANAL_WHATSAPP,
    TIPO_AVISO_RECEPCION,
    TIPO_T24H,
    MemoryPlantillaStore,
    MemoryRecordatorioStore,
    NotificacionService,
    PlantillaRecord,
)
from app.infrastructure.smtp import FakeEmailClient
from app.infrastructure.whatsapp_bsp import FakeWhatsAppClient
from app.shared.exceptions import register_exception_handlers

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
NOW = datetime.datetime(2026, 11, 14, 12, 0, tzinfo=datetime.UTC)


def _principal(
    tenant: uuid.UUID = TENANT_A, roles: tuple[str, ...] = ("propietario",)
) -> Principal:
    return Principal(
        sub=f"user-{roles[0]}-ficticio",
        tenant_id=tenant,
        roles=roles,
        email=f"{roles[0]}@demo-ficticia.invalid",
    )


def _plantilla(tenant_id: uuid.UUID, clave: str) -> PlantillaRecord:
    return PlantillaRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        clave=clave,
        canal=CANAL_WHATSAPP,
        idioma="es",
        version=1,
        cuerpo=f"Cuerpo {clave} (ficticio)",
        meta_template_name=clave,
        activo=True,
    )


def _seeded_service() -> NotificacionService:
    """Service with one reminder and one reception alert per tenant."""
    plantillas = MemoryPlantillaStore()
    recordatorios = MemoryRecordatorioStore()
    for tenant in (TENANT_A, TENANT_B):
        asyncio.run(plantillas.add(_plantilla(tenant, "recordatorio_t24h")))
        asyncio.run(plantillas.add(_plantilla(tenant, "aviso_recepcion")))
    service = NotificacionService(
        recordatorios=recordatorios,
        plantillas=plantillas,
        whatsapp=FakeWhatsAppClient(),
        email=FakeEmailClient(),
        max_intentos=1,
        backoff_base_s=0.0,
        sleep=lambda _seconds: asyncio.sleep(0),
    )
    for tenant, tipo, canal in (
        (TENANT_A, TIPO_T24H, CANAL_WHATSAPP),
        (TENANT_A, TIPO_AVISO_RECEPCION, CANAL_INTERNO),
        (TENANT_B, TIPO_AVISO_RECEPCION, CANAL_INTERNO),
    ):
        rec = asyncio.run(
            service.programar(
                turno_id=uuid.uuid4(),
                tenant_id=tenant,
                tipo=tipo,
                canal=canal,
                destinatario="+5491100000000" if canal == CANAL_WHATSAPP else None,
                enviar_at=NOW,
            )
        )
        rec.created_at = NOW
        asyncio.run(recordatorios.update(rec))
    return service


def _client_as(
    roles: tuple[str, ...],
    tenant: uuid.UUID = TENANT_A,
    service: NotificacionService | None = None,
) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router, prefix="/api")
    app.dependency_overrides[api_module.get_current_principal] = (
        lambda: _principal(tenant, roles)
    )
    app.dependency_overrides[api_module.get_notificacion_service] = (
        lambda: service or _seeded_service()
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "roles",
    [("propietario",), ("odontologo",), ("recepcion",), ("asistente",)],
)
def test_recordatorios_readable_by_staff(roles: tuple[str, ...]) -> None:
    """WHEN any staff role reads alerts THEN 200 and the tenant rows only."""
    response = _client_as(roles).get("/api/recordatorios")
    assert response.status_code == 200, response.text
    assert len(response.json()) == 2


def test_recordatorios_rejects_patient_role() -> None:
    """WHEN the paciente role calls the operative API THEN 403."""
    response = _client_as(("paciente",)).get("/api/recordatorios")
    assert response.status_code == 403


def test_recordatorios_filter_by_tipo_recepcion() -> None:
    """WHEN tipo=aviso_recepcion THEN only the reception alert row returns."""
    response = _client_as(("recepcion",)).get(
        "/api/recordatorios", params={"tipo": "aviso_recepcion"}
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["tipo"] == "aviso_recepcion"
    assert rows[0]["canal"] == "interno"
    assert rows[0]["tenant_id"] == str(TENANT_A)


def test_recordatorios_are_scoped_to_the_jwt_tenant() -> None:
    """WHEN tenant B reads alerts THEN tenant A rows are never visible."""
    response = _client_as(("propietario",), tenant=TENANT_B).get(
        "/api/recordatorios"
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == str(TENANT_B)


def test_recordatorios_limit_is_validated() -> None:
    """WHEN limit is out of range THEN 422."""
    assert (
        _client_as(("propietario",))
        .get("/api/recordatorios", params={"limit": 0})
        .status_code
        == 422
    )


def test_plantillas_visible_to_owner_only() -> None:
    """WHEN propietario lists templates THEN 200; other roles get 403."""
    owner = _client_as(("propietario",)).get("/api/plantillas")
    assert owner.status_code == 200, owner.text
    rows = owner.json()
    assert {row["clave"] for row in rows} == {
        "recordatorio_t24h",
        "aviso_recepcion",
    }
    assert all(row["version"] == 1 for row in rows)

    for roles in (("recepcion",), ("odontologo",), ("asistente",), ("paciente",)):
        assert _client_as(roles).get("/api/plantillas").status_code == 403
