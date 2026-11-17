from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import turnero_publico as tp


def test_post_reservar_creates_reservado() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    payload = {
        "nombre": "Paciente Ficticio",
        "whatsapp": "+5491112345678",
        "profesional_id": "prof-1",
        "inicio": "2026-11-20T10:00:00",
    }
    r = client.post("/reservar/demo-ficticia/turnos", json=payload)
    assert r.status_code in (200, 201)
    body = r.json()
    assert body["estado"] == "reservado"
    assert "portal" in body or "token" in body


def test_post_reservar_race_returns_409_with_alternativas() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    payload = {
        "nombre": "Paciente Ficticio",
        "whatsapp": "+5491112345678",
        "profesional_id": "prof-race",
        "inicio": "2026-11-20T11:00:00",
    }
    first = client.post("/reservar/demo-ficticia/turnos", json=payload)
    assert first.status_code in (200, 201)
    second = client.post("/reservar/demo-ficticia/turnos", json=payload)
    assert second.status_code == 409
    body = second.json()
    assert isinstance(body.get("alternativas"), list)
