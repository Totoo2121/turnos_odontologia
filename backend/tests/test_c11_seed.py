"""C-11 task 1.4: idempotent approved-template seed."""

from __future__ import annotations

import asyncio
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from app.application.notificaciones import MemoryPlantillaStore
from app.infrastructure.seed_c11 import PLANTILLAS_C11, seed_plantillas

TENANT = uuid.uuid4()


def test_seed_adds_all_templates() -> None:
    """WHEN seed runs THEN every documented template exists per channel."""
    store = MemoryPlantillaStore()
    added = asyncio.run(seed_plantillas(store, tenant_id=TENANT))
    assert added == len(PLANTILLAS_C11)
    rows = asyncio.run(store.list_plantillas(TENANT))
    keys = {(r.clave, r.canal, r.version) for r in rows}
    for expected in PLANTILLAS_C11:
        assert (expected["clave"], expected["canal"], 1) in keys
    for clave in (
        "recordatorio_t48h",
        "recordatorio_t24h",
        "confirmacion",
        "recall_ausente",
        "control",
        "aviso_recepcion",
        "politica_cancelacion",
    ):
        assert any(r.clave == clave for r in rows)


def test_seed_is_idempotent() -> None:
    """WHEN seed runs twice THEN no row is duplicated or overwritten."""
    store = MemoryPlantillaStore()
    asyncio.run(seed_plantillas(store, tenant_id=TENANT))
    first = asyncio.run(store.list_plantillas(TENANT))
    added = asyncio.run(seed_plantillas(store, tenant_id=TENANT))
    second = asyncio.run(store.list_plantillas(TENANT))
    assert added == 0
    assert len(first) == len(second)
    assert [r.id for r in first] == [r.id for r in second]


def test_seed_does_not_overwrite_existing_body() -> None:
    """WHEN the tenant edited a template THEN re-seed keeps its body."""
    store = MemoryPlantillaStore()
    asyncio.run(seed_plantillas(store, tenant_id=TENANT))
    row = asyncio.run(
        store.get_activa(
            tenant_id=TENANT, clave="recordatorio_t48h", canal="whatsapp"
        )
    )
    assert row is not None
    row_edited = type(row)(
        id=row.id,
        tenant_id=row.tenant_id,
        clave=row.clave,
        canal=row.canal,
        idioma=row.idioma,
        version=row.version,
        cuerpo="Texto editado por el consultorio (ficticio)",
        meta_template_name=row.meta_template_name,
        activo=True,
    )
    asyncio.run(store.add(row_edited))
    asyncio.run(seed_plantillas(store, tenant_id=TENANT))
    current = asyncio.run(
        store.get_activa(
            tenant_id=TENANT, clave="recordatorio_t48h", canal="whatsapp"
        )
    )
    assert current is not None
    assert current.cuerpo == "Texto editado por el consultorio (ficticio)"
