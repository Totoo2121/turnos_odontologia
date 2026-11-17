from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import turnero_publico as tp


def test_portal_get_returns_turno() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/p/token-demo")
    assert r.status_code == 200
    body = r.json()
    assert body["token"] == "token-demo"
    assert "estado" in body
    assert "politica" in body


def test_portal_cancel_within_plazo() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/p/token-future/cancelar")
    assert r.status_code in (200, 204)
    body = r.json() if r.content else {}
    assert body.get("cancelado") is True


def test_portal_cancel_outside_plazo_rejected() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/p/token-past/cancelar")
    assert r.status_code in (400, 403, 409)
    body = r.json()
    assert "politica" in body or "detail" in body or "mensaje" in body


def test_portal_reprogramar_within_plazo() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    payload = {"inicio": "2026-12-01T10:00:00"}
    r = client.post("/p/token-future/reprogramar", json=payload)
    assert r.status_code in (200, 201)
    body = r.json()
    assert body.get("reprogramado") is True
