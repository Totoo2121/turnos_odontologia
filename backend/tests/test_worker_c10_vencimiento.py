"""C-10 task 4.1: worker periódico vence órdenes sin acreditar y libera hueco."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.cobros import (
    ESTADO_COBRO_PENDIENTE,
    ESTADO_COBRO_VENCIDO,
    ESTADO_TURNO_CANCELADO,
    ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO,
    CobroService,
    MemoryCobroStore,
    PagoRecord,
)
from app.worker.tasks import vencer_ordenes_sin_acreditar


class FakeMPClient:
    async def create_order(self, payload):
        return {"id": "mp-order-w", "checkout_url": "https://mp/checkout/w"}


def _svc() -> CobroService:
    return CobroService(store=MemoryCobroStore(), client=FakeMPClient())


async def _crear_orden_vencible(svc: CobroService) -> tuple[uuid.UUID, PagoRecord]:
    """Crea una orden pendiente (seña) con su turno en reservado-pendiente-pago."""
    turno_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    await svc.crear_orden(turno_id=turno_id, tenant_id=tenant_id, monto=5000.0)
    svc.turnos[turno_id] = ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO
    pendiente = await svc.store.find_by_turno(turno_id)
    assert pendiente is not None
    return turno_id, pendiente


def _vencida(pendiente: PagoRecord) -> datetime:
    """Devuelve un instante de 'hoy' ya mas alla del plazo de cobro (24h)."""
    creada = pendiente.created_at or datetime.now(timezone.utc)
    return creada + timedelta(hours=25)


@pytest.mark.asyncio
async def test_worker_vence_orden_vencida_y_libera_hueco() -> None:
    """WHEN una orden sin acreditar supera el plazo THEN worker la vence y libera hueco."""
    svc = _svc()
    turno_id, pendiente = await _crear_orden_vencible(svc)

    ahora = _vencida(pendiente)
    liberados = await vencer_ordenes_sin_acreditar(
        plazo_hs=24, ahora=ahora, service=svc
    )

    assert liberados == 1
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_CANCELADO
    assert svc.hueco_liberado(turno_id) is True


@pytest.mark.asyncio
async def test_worker_no_vence_orden_fresh() -> None:
    """WHEN la orden todavia no supera el plazo THEN no la vence (turno reservado)."""
    svc = _svc()
    turno_id, _ = await _crear_orden_vencible(svc)

    ahora = datetime.now(timezone.utc)
    liberados = await vencer_ordenes_sin_acreditar(
        plazo_hs=24, ahora=ahora, service=svc
    )

    assert liberados == 0
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO
    assert svc.hueco_liberado(turno_id) is False


def test_worker_c10_job_esta_programado_periodicamente() -> None:
    """WHEN se inspecciona Celery beat THEN el job C-10 corre periódicamente."""
    from app.worker.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("c10-vencer-ordenes-sin-acreditar")
    assert entry is not None
    assert entry["task"] == "app.worker.tasks.vencer_ordenes_sin_acreditar"
    assert entry["schedule"]


def test_worker_c10_celery_task_es_sincronica_y_ejecutable() -> None:
    """WHEN Celery ejecuta el task THEN es sync (no coroutine) y devuelve el conteo."""
    import app.worker.tasks  # noqa: F401  (registra el task en Celery)
    from app.worker.celery_app import celery_app

    task = celery_app.tasks["app.worker.tasks.vencer_ordenes_sin_acreditar"]
    resultado = task.run(plazo_hs=24)

    assert isinstance(resultado, int)
    assert resultado == 0


def test_worker_c10_tasks_module_se_importa_en_el_worker() -> None:
    """WHEN el worker arranca THEN importa app.worker.tasks (registra el job)."""
    from app.worker.celery_app import celery_app

    assert "app.worker.tasks" in celery_app.conf.include


def test_worker_c10_job_lee_plazo_configurable_por_env(monkeypatch) -> None:
    """WHEN COBROS_PLAZO_HS se configura THEN el job usa ese plazo (default 24h)."""
    import asyncio

    from app.worker.tasks import vencer_ordenes_sin_acreditar_job

    svc = _svc()
    turno_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    svc.turnos[turno_id] = ESTADO_TURNO_RESERVADO_PENDIENTE_PAGO
    pago = PagoRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        turno_id=turno_id,
        monto=5000.0,
        estado=ESTADO_COBRO_PENDIENTE,
        created_at=datetime.now(UTC) - timedelta(hours=10),
    )
    asyncio.run(svc.store.record(pago))
    monkeypatch.setenv("COBROS_PLAZO_HS", "8")

    vencidas = vencer_ordenes_sin_acreditar_job(service=svc)

    assert vencidas == 1
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_CANCELADO


@pytest.mark.asyncio
async def test_worker_vencida_registra_cobro_vencido() -> None:
    """WHEN el worker vence THEN el cobro queda en estado `vencido`."""
    svc = _svc()
    turno_id, pendiente = await _crear_orden_vencible(svc)

    ahora = _vencida(pendiente)
    await vencer_ordenes_sin_acreditar(plazo_hs=24, ahora=ahora, service=svc)

    vencido = await svc.store.find_by_turno(turno_id)
    assert vencido is not None
    assert vencido.estado == ESTADO_COBRO_VENCIDO
