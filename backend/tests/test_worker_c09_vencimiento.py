"""Worker vencimiento y rotación (C-09 task 3.2)."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import datetime, timedelta, timezone

from app.worker.tasks import vencer_y_rotar_ofertas


def test_vencimiento_rota_al_siguiente() -> None:
    now = datetime.now(timezone.utc)
    expired_until = now - timedelta(minutes=1)
    regs = [
        {"id": "a", "estado": "ofrecida", "prestacion_id": "P", "franja": "manana", "profesional_id": None, "created_at": now - timedelta(hours=2), "ofrecida_hasta": expired_until},
        {"id": "b", "estado": "activa", "prestacion_id": "P", "franja": "manana", "profesional_id": None, "created_at": now - timedelta(hours=1)},
    ]
    n = vencer_y_rotar_ofertas(registros=regs, ahora=now)
    assert n == 1
    assert regs[0]["estado"] == "vencida"
    assert regs[1]["estado"] == "ofrecida"