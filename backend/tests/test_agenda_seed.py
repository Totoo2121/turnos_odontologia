"""C-05 catalog seed tests (tasks 5.1/5.2) — RED first.

``seed_catalogo`` runs against the ``CatalogStore`` port: the memory fake
lets idempotency tests run without Postgres (double-run, counts 5/1/1).
All values fictitious.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import asyncio
import uuid
from typing import Any
from collections.abc import Coroutine

import pytest

from app.application.catalog_store import MemoryCatalogStore, reset_memory_catalog
from app.infrastructure import seed_catalogo as seed_module


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clean():  # type: ignore[no-untyped-def]
    reset_memory_catalog()
    yield
    reset_memory_catalog()


def test_seed_primera_corrida_crea_catalogo() -> None:
    """WHEN seed sobre tenant vacio THEN 5 prestaciones + 1 sillon + 1 profesional."""
    store = MemoryCatalogStore(tenant_id=uuid.uuid4())
    summary = _run(seed_module.seed_catalogo(store, year=2026))
    assert summary["prestaciones"] == 5
    assert summary["sillones"] == 1
    assert summary["profesionales"] == 1
    assert summary["bloqueos"] == len(seed_module.feriados_del_ano(2026))
    assert summary["bloqueos"] > 0


def test_seed_doble_corrida_no_duplica() -> None:
    """WHEN seed dos veces THEN conteos 5/1/1 y mismos ids (upsert)."""
    store = MemoryCatalogStore(tenant_id=uuid.uuid4())
    first = _run(seed_module.seed_catalogo(store, year=2026))
    second = _run(seed_module.seed_catalogo(store, year=2026))
    assert (second["prestaciones"], second["sillones"], second["profesionales"]) == (
        5,
        1,
        1,
    )
    assert second["bloqueos"] == first["bloqueos"]
    ids_first = {row["id"] for row in _run(store.list_prestaciones(limit=50, offset=0))}
    ids_second = {row["id"] for row in _run(store.list_prestaciones(limit=50, offset=0))}
    assert ids_first == ids_second


def test_seed_profesional_habilitado_y_feriados() -> None:
    """WHEN seed corre THEN profesional demo habilitado + bloqueos feriado."""
    store = MemoryCatalogStore(tenant_id=uuid.uuid4())
    _run(seed_module.seed_catalogo(store, year=2026))
    profesionales = _run(store.list_profesionales(limit=10, offset=0))
    assert len(profesionales) == 1
    assert "ficticio" in profesionales[0]["nombre"].lower()
    habilitadas = _run(store.get_habilitaciones(profesionales[0]["id"]))
    assert len(habilitadas) == 5
    bloqueos = _run(store.list_bloqueos(limit=100, offset=0))
    assert bloqueos, "feriados esperados como bloqueos"
    assert {b["motivo"] for b in bloqueos} == {"feriado"}
    assert all(b["profesional_id"] == profesionales[0]["id"] for b in bloqueos)


def test_seed_otro_ano_otras_fechas() -> None:
    """WHEN seed 2027 THEN bloqueos fechados en 2027 (triangula year)."""
    store = MemoryCatalogStore(tenant_id=uuid.uuid4())
    _run(seed_module.seed_catalogo(store, year=2027))
    bloqueos = _run(store.list_bloqueos(limit=100, offset=0))
    assert bloqueos
    assert all(b["inicio"].year == 2027 for b in bloqueos)
    assert len(bloqueos) == len(seed_module.feriados_del_ano(2027))


def test_seed_solo_datos_ficticios() -> None:
    """WHEN catalogo seed leido THEN ningun dato real (marcas ficticias)."""
    store = MemoryCatalogStore(tenant_id=uuid.uuid4())
    _run(seed_module.seed_catalogo(store, year=2026))
    nombres = [
        row["nombre"]
        for row in _run(store.list_prestaciones(limit=50, offset=0))
    ] + [row["nombre"] for row in _run(store.list_sillones(limit=10, offset=0))]
    assert nombres, "seed debe crear filas con nombre"
    assert all("fictici" in n.lower() or "demo" in n.lower() for n in nombres)


def test_seed_documenta_politica_de_feriados() -> None:
    """WHEN docstring leido THEN ejemplo recargable, no fuente oficial (5.2)."""
    doc = seed_module.seed_catalogo.__doc__ or ""
    assert "no es fuente oficial" in doc
    assert "recargar" in doc.lower() or "re-ejecut" in doc.lower()
    module_doc = (seed_module.__doc__ or "").lower()
    assert "fictici" in module_doc
