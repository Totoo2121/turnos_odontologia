from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import turnero_publico as tp


def test_get_reservar_returns_shape() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/reservar/demo-ficticia")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "demo-ficticia"
    assert isinstance(body["prestaciones"], list)
    assert isinstance(body["profesionales"], list)
    assert isinstance(body["huecos"], list)