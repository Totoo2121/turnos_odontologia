"""C-10 cobros service unit tests (task 2.1) — Strict TDD."""

from __future__ import annotations

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.cobros import (
    ESTADO_COBRO_ACREDITADO,
    ESTADO_COBRO_RECHAZADO,
    ESTADO_COBRO_VENCIDO,
    ESTADO_TURNO_CANCELADO,
    ESTADO_TURNO_CONFIRMADO,
    CobroService,
    MemoryCobroStore,
    PagoRecord,
)


class FakeMPClient:
    def __init__(self, result=None):
        self.result = result or {"id": "mp-order-123", "checkout_url": "https://mp/checkout/123"}
        self.calls = []

    async def create_order(self, payload):
        self.calls.append(payload)
        return self.result


@pytest.mark.asyncio
async def test_crear_orden_creates_mp_order_and_links_turno():
    client = FakeMPClient()
    store = MemoryCobroStore()
    svc = CobroService(store=store, client=client)
    turno_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    pago = await svc.crear_orden(turno_id=turno_id, tenant_id=tenant_id, monto=5000.0)
    assert pago.turno_id == turno_id
    assert pago.tenant_id == tenant_id
    assert pago.mp_order_id == "mp-order-123"
    assert pago.checkout_url == "https://mp/checkout/123"
    assert pago.estado == "pendiente"
    # persisted
    found = await store.find_by_turno(turno_id)
    assert found is not None and found.id == pago.id
    # client called with payload
    assert client.calls and client.calls[0]["turno_id"] == str(turno_id)


@pytest.mark.asyncio
async def test_crear_orden_requires_client():
    svc = CobroService()
    with pytest.raises(Exception):
        await svc.crear_orden(turno_id=uuid.uuid4(), tenant_id=uuid.uuid4(), monto=100.0)


@pytest.mark.asyncio
async def test_crear_orden_rejects_non_positive_monto():
    svc = CobroService(client=FakeMPClient())
    with pytest.raises(Exception):
        await svc.crear_orden(turno_id=uuid.uuid4(), tenant_id=uuid.uuid4(), monto=0)


@pytest.mark.asyncio
async def test_crear_orden_uses_init_point_fallback():
    client = FakeMPClient(result={"id": "o2", "init_point": "https://mp/init"})
    svc = CobroService(client=client)
    pago = await svc.crear_orden(turno_id=uuid.uuid4(), tenant_id=uuid.uuid4(), monto=100.0)
    assert pago.checkout_url == "https://mp/init"


@pytest.mark.asyncio
async def test_acreditar_mueve_turno_a_confirmado():
    """C-10 task 3.2: IPN aprobado → `pago.acreditado` + turno `confirmado`."""
    store = MemoryCobroStore()
    svc = CobroService(store=store)
    turno_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    pago = await svc.acreditar(
        turno_id=turno_id,
        tenant_id=tenant_id,
        mp_payment_id="pay-unit-approved",
        mp_order_id="ord-unit-1",
        monto=5000.0,
    )
    assert pago.estado == ESTADO_COBRO_ACREDITADO
    assert pago.acreditado_at is not None
    stored = await store.find_by_mp_payment_id("pay-unit-approved")
    assert stored is not None and stored.estado == ESTADO_COBRO_ACREDITADO
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_CONFIRMADO
    # el hueco queda ocupado por el turno confirmado (no liberado)
    assert svc.hueco_liberado(turno_id) is False


@pytest.mark.asyncio
async def test_anular_vencido_cancela_turno_y_libera_hueco():
    """C-10 task 3.2: orden vencido → `pago.vencido` + turno `cancelado` + liberar hueco."""
    svc = CobroService()
    turno_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    pago = await svc.anular(
        turno_id=turno_id,
        tenant_id=tenant_id,
        mp_payment_id="pay-unit-expired",
        monto=5000.0,
        motivo="vencido",
    )
    assert pago.estado == ESTADO_COBRO_VENCIDO
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_CANCELADO
    assert svc.hueco_liberado(turno_id) is True


@pytest.mark.asyncio
async def test_anular_rechazado_cancela_turno_y_libera_hueco():
    """C-10 task 3.2: pago rechazado → `pago.rechazado` + turno `cancelado` + liberar hueco."""
    svc = CobroService()
    turno_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    pago = await svc.anular(
        turno_id=turno_id,
        tenant_id=tenant_id,
        mp_payment_id="pay-unit-rejected",
        monto=5000.0,
        motivo="rechazado",
    )
    assert pago.estado == ESTADO_COBRO_RECHAZADO
    assert svc.estado_turno(turno_id) == ESTADO_TURNO_CANCELADO
    assert svc.hueco_liberado(turno_id) is True