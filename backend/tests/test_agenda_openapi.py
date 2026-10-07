"""C-05 OpenAPI documentation tests (task 2.3) — RED first.

The 4 catalog resources + huecos query must appear in the generated
OpenAPI with descriptions and the 201/400/401/403/404/422 codes. Pure
schema inspection: no DB.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from fastapi import FastAPI

from app.api import catalog as catalog_module


def _spec() -> dict:
    app = FastAPI(title="Turnos Odontologia API (test)")
    app.include_router(catalog_module.router, prefix="/api")
    return app.openapi()


def test_cuatro_recursos_en_openapi() -> None:
    """WHEN openapi generado THEN los 4 paths CRUD presentes."""
    paths = _spec()["paths"]
    for resource in ("profesionales", "sillones", "prestaciones", "bloqueos"):
        assert f"/api/{resource}" in paths, f"missing list path: {resource}"
        item_paths = [p for p in paths if p.startswith(f"/api/{resource}/")]
        assert item_paths, f"missing item path: {resource}/{{id}}"


def test_huecos_en_openapi() -> None:
    """WHEN openapi generado THEN GET /api/agenda/huecos documentado."""
    paths = _spec()["paths"]
    assert "/api/agenda/huecos" in paths
    assert "get" in paths["/api/agenda/huecos"]


def test_codigos_y_descripciones_documentados() -> None:
    """WHEN operacion POST inspeccionada THEN 201/401/403/422 + descripcion."""
    post = _spec()["paths"]["/api/prestaciones"]["post"]
    assert post["responses"]["201"]["description"] == "Prestacion creada"
    for code in ("401", "403", "422"):
        assert code in post["responses"], f"missing code {code} in POST prestaciones"
    assert post.get("description"), "missing route description"
    get_item = _spec()["paths"]["/api/prestaciones/{prestacion_id}"]["get"]
    assert "404" in get_item["responses"]
    delete_item = _spec()["paths"]["/api/prestaciones/{prestacion_id}"]["delete"]
    assert "204" in delete_item["responses"]


def test_bloqueos_y_huecos_documentan_errores() -> None:
    """WHEN bloqueos/huecos inspeccionados THEN 404/400/422 visibles (2do input)."""
    spec = _spec()
    post_bloqueo = spec["paths"]["/api/bloqueos"]["post"]
    assert "422" in post_bloqueo["responses"]
    huecos = spec["paths"]["/api/agenda/huecos"]["get"]
    for code in ("200", "400", "404", "422"):
        assert code in huecos["responses"], f"missing code {code} in huecos"
