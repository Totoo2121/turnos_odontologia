"""C-18 stubs expose the stage boundary without invoking integrations."""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db")
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import etapa2
from app.api.deps import get_current_principal
from app.application.auth_service import Principal
from app.shared.exceptions import register_exception_handlers


def _client(roles: tuple[str, ...]) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(etapa2.router, prefix="/api")
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        sub=str(uuid.uuid4()), tenant_id=uuid.uuid4(), roles=roles,
        email="usuario-ficticio@example.invalid",
    )
    return TestClient(app, raise_server_exceptions=False)


def test_owner_gets_explicit_501_for_stage_two_route() -> None:
    response = _client(("propietario",)).post("/api/etapa2/arca/comprobantes")
    assert response.status_code == 501
    assert "etapa 2" in response.json()["detail"]


def test_non_owner_cannot_call_stage_two_stub() -> None:
    response = _client(("recepcion",)).post("/api/etapa2/arca/comprobantes")
    assert response.status_code == 403


def test_stubs_are_not_public() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(etapa2.router, prefix="/api")
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/etapa2/arca/comprobantes"
    )
    assert response.status_code == 401
