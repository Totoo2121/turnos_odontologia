"""Worker oferta hueco liberado (C-09 task 3.1)."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import datetime, timedelta, timezone

from app.worker.tasks import ofertar_hueco_liberado


def test_oferta_por_antiguedad() -> None:
    now = datetime.now(timezone.utc)
    regs = [
        {"id": "a", "estado": "activa", "prestacion_id": "P", "franja": "manana", "profesional_id": None, "created_at": now - timedelta(hours=1)},
        {"id": "b", "estado": "activa", "prestacion_id": "P", "franja": "manana", "profesional_id": None, "created_at": now},
    ]
    n = ofertar_hueco_liberado("P", "manana", registros=regs, ahora=now)
    assert n == 1
    assert regs[0]["estado"] == "ofrecida"
    assert regs[1]["estado"] == "activa"
