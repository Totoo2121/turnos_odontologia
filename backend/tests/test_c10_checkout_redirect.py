"""C-10 task 2.2: public checkout redirect endpoint — Strict TDD."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import turnero_publico as tp


def test_checkout_redirect_returns_200_with_url() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/checkout/turno-ficticio-1")
    assert r.status_code == 200
    body = r.json()
    assert "url" in body and isinstance(body["url"], str) and body["url"].startswith("http")


def test_portal_checkout_returns_200_with_url() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/p/token-demo/checkout")
    assert r.status_code == 200
    body = r.json()
    assert "url" in body and isinstance(body["url"], str)


def test_portal_retorno_returns_200() -> None:
    app = FastAPI()
    app.include_router(tp.router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/p/token-demo/retorno")
    assert r.status_code == 200
    body = r.json()
    assert "estado" in body