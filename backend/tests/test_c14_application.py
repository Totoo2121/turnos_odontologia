"""C-14 application-level tests: stores, service, account and plans."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.auth_service import Principal
from app.application.presupuestos import (
    PlanTratamientoRecord,
    PrestacionSnapshot,
)
from app.shared.exceptions import AppError
from tests.support_c14 import (
    TENANT_A,
    TENANT_B,
    build_stores,
    cuenta_service,
    firmar_consentimiento,
    item_input,
    presupuestos_service,
    principal,
    seed_paciente_historia,
    seed_prestacion,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _setup(*, precio: str | None = "15000.50", invasiva: bool = False):
    stores = build_stores()
    paciente, historia = seed_paciente_historia(stores)
    prestacion = seed_prestacion(
        stores,
        nombre="Prestacion Ficticia C-14",
        precio=precio,
        requiere_consentimiento=invasiva,
    )
    return stores, paciente, historia, prestacion


def _crear(stores, who, paciente, items=()):  # type: ignore[no-untyped-def]
    service = presupuestos_service(stores)
    return _run(
        service.crear(who, paciente_id=paciente.id, items=list(items))
    )


def _enviado(stores, who, paciente, items=()):  # type: ignore[no-untyped-def]
    service = presupuestos_service(stores)
    view = _crear(stores, who, paciente, items)
    return _run(service.enviar(who, view.presupuesto.id))


def _status(exc: pytest.ExceptionInfo[AppError]) -> int:
    return exc.value.status_code


# --- Budgets and items -----------------------------------------------------


def test_price_is_inherited_from_catalog() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    item = view.items[0]
    assert item.precio_unitario == Decimal("15000.50")
    assert item.descripcion == "Prestacion Ficticia C-14"


def test_manual_price_is_used_when_catalog_has_none() -> None:
    stores, paciente, _historia, prestacion = _setup(precio=None)
    owner = principal()
    view = _crear(
        stores,
        owner,
        paciente,
        [item_input(prestacion.id, precio_unitario="9999.99")],
    )
    assert view.items[0].precio_unitario == Decimal("9999.99")


def test_missing_price_is_422() -> None:
    stores, paciente, _historia, prestacion = _setup(precio=None)
    owner = principal()
    with pytest.raises(AppError) as exc:
        _crear(stores, owner, paciente, [item_input(prestacion.id)])
    assert _status(exc) == 422
    assert not stores.presupuestos._rows


def test_catalog_change_does_not_rewrite_the_quote() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    stores.prestaciones.add(
        PrestacionSnapshot(
            id=prestacion.id,
            nombre="Nombre nuevo",
            precio=Decimal("99999.00"),
        )
    )
    service = presupuestos_service(stores)
    again = _run(service.obtener(owner, view.presupuesto.id))
    assert again.items[0].precio_unitario == Decimal("15000.50")
    assert again.items[0].descripcion == "Prestacion Ficticia C-14"


def test_total_is_exact_and_recalculated() -> None:
    stores, paciente, _historia, prestacion = _setup()
    otro = seed_prestacion(stores, nombre="Otra", precio="3000.25")
    owner = principal()
    service = presupuestos_service(stores)
    view = _crear(
        stores,
        owner,
        paciente,
        [
            item_input(prestacion.id, precio_unitario="15000.50"),
            item_input(otro.id, precio_unitario="3000.25"),
        ],
    )
    assert view.presupuesto.total == Decimal("18000.75")
    assert view.presupuesto.moneda == "ARS"

    view = _run(
        service.agregar_item(
            owner,
            view.presupuesto.id,
            item_input(prestacion.id, cantidad=2, precio_unitario="1000.00"),
        )
    )
    assert view.presupuesto.total == Decimal("20000.75")
    item_id = view.items[-1].id
    view = _run(
        service.editar_item(
            owner, view.presupuesto.id, item_id, cantidad=3
        )
    )
    assert view.presupuesto.total == Decimal("21000.75")
    view = _run(service.quitar_item(owner, view.presupuesto.id, item_id))
    assert view.presupuesto.total == Decimal("18000.75")


def test_invalid_quantity_and_stage_are_422() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    with pytest.raises(AppError) as exc:
        _crear(
            stores,
            owner,
            paciente,
            [item_input(prestacion.id, cantidad=0)],
        )
    assert _status(exc) == 422
    with pytest.raises(AppError) as exc:
        _crear(
            stores,
            owner,
            paciente,
            [item_input(prestacion.id, etapa=21)],
        )
    assert _status(exc) == 422


def test_fdi_and_surface_rules() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    view = _crear(
        stores,
        owner,
        paciente,
        [item_input(prestacion.id, pieza_fdi=16, superficie="oclusal")],
    )
    assert view.items[0].pieza_fdi == 16
    assert view.items[0].superficie == "oclusal"

    for kwargs in (
        {"pieza_fdi": 49},
        {"pieza_fdi": 16, "superficie": "inventada"},
        {"superficie": "oclusal"},
    ):
        with pytest.raises(AppError) as exc:
            _crear(stores, owner, paciente, [item_input(prestacion.id, **kwargs)])
        assert _status(exc) == 422


def test_history_must_belong_to_the_patient() -> None:
    stores, paciente, _historia, prestacion = _setup()
    otro_paciente, otra_historia = seed_paciente_historia(
        stores, dni="91000015", nombre="Otro Ficticio"
    )
    owner = principal()
    service = presupuestos_service(stores)
    with pytest.raises(AppError) as exc:
        _run(
            service.crear(
                owner,
                paciente_id=paciente.id,
                historia_clinica_id=otra_historia.id,
                items=[item_input(prestacion.id)],
            )
        )
    assert _status(exc) == 422


def test_author_comes_from_the_token() -> None:
    stores, paciente, _historia, prestacion = _setup()
    usuario = uuid.uuid4()
    owner = principal(sub=usuario)
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    assert view.presupuesto.creado_por_usuario_id == usuario

    invalido = Principal(
        sub="not-a-uuid",
        tenant_id=principal().tenant_id,
        roles=("propietario",),
        email="ficticio@demo-ficticia.invalid",
    )
    with pytest.raises(AppError) as exc:
        _crear(stores, invalido, paciente, [item_input(prestacion.id)])
    assert _status(exc) == 422


def test_stores_are_tenant_scoped() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    assert _run(
        stores.presupuestos.get(TENANT_B, view.presupuesto.id)
    ) is None
    assert (
        _run(
            stores.items.list_by_presupuesto(
                TENANT_B, view.presupuesto.id
            )
        )
        == []
    )


def test_reception_cannot_write_and_foreign_professional_is_403() -> None:
    stores, paciente, _historia, prestacion = _setup()
    service = presupuestos_service(stores)
    with pytest.raises(AppError) as exc:
        _run(
            service.crear(
                principal(roles=("recepcion",)),
                paciente_id=paciente.id,
                items=[item_input(prestacion.id)],
            )
        )
    assert _status(exc) == 403

    with pytest.raises(AppError) as exc:
        _run(
            service.crear(
                principal(roles=("odontologo",)),
                paciente_id=paciente.id,
                items=[item_input(prestacion.id)],
            )
        )
    assert _status(exc) == 403


# --- Transitions and validity ---------------------------------------------


def test_valid_transitions_and_timestamps() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    enviado = _run(service.enviar(owner, view.presupuesto.id))
    assert enviado.presupuesto.estado == "enviado"
    assert enviado.presupuesto.enviado_at is not None
    aceptado = _run(service.aceptar(owner, view.presupuesto.id))
    assert aceptado.presupuesto.estado == "aceptado"
    assert aceptado.presupuesto.aceptado_at is not None


def test_rejection_generates_no_plan_or_debt() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _enviado(stores, owner, paciente, [item_input(prestacion.id)])
    rechazado = _run(service.rechazar(owner, view.presupuesto.id))
    assert rechazado.presupuesto.estado == "rechazado"
    assert rechazado.presupuesto.rechazado_at is not None
    assert not stores.planes._rows
    assert not stores.movimientos._rows


def test_invalid_transitions_are_409() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    with pytest.raises(AppError) as exc:
        _run(service.aceptar(owner, view.presupuesto.id))
    assert _status(exc) == 409
    _run(service.enviar(owner, view.presupuesto.id))
    with pytest.raises(AppError) as exc:
        _run(service.enviar(owner, view.presupuesto.id))
    assert _status(exc) == 409


def test_editing_is_limited_to_draft() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _enviado(stores, owner, paciente, [item_input(prestacion.id)])
    with pytest.raises(AppError) as exc:
        _run(
            service.editar(
                owner, view.presupuesto.id, observaciones="tarde"
            )
        )
    assert _status(exc) == 409
    with pytest.raises(AppError) as exc:
        _run(
            service.agregar_item(
                owner,
                view.presupuesto.id,
                item_input(prestacion.id),
            )
        )
    assert _status(exc) == 409


def test_delete_is_limited_to_draft() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    _run(service.eliminar(owner, view.presupuesto.id))
    assert _run(
        stores.presupuestos.get(owner.tenant_id, view.presupuesto.id)
    ) is None
    assert (
        _run(
            stores.items.list_by_presupuesto(
                owner.tenant_id, view.presupuesto.id
            )
        )
        == []
    )


def test_default_validity_and_expired_acceptance() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _crear(stores, owner, paciente, [item_input(prestacion.id)])
    assert view.presupuesto.validez_hasta == date.today() + timedelta(
        days=30
    )

    vencido = _run(
        service.crear(
            owner,
            paciente_id=paciente.id,
            validez_hasta=date.today() - timedelta(days=1),
            items=[item_input(prestacion.id)],
        )
    )
    _run(service.enviar(owner, vencido.presupuesto.id))
    with pytest.raises(AppError) as exc:
        _run(service.aceptar(owner, vencido.presupuesto.id))
    assert _status(exc) == 409
    assert not stores.planes._rows
    assert not stores.movimientos._rows


def test_send_and_accept_require_items() -> None:
    stores, paciente, _historia, _prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _crear(stores, owner, paciente)
    with pytest.raises(AppError) as exc:
        _run(service.enviar(owner, view.presupuesto.id))
    assert _status(exc) == 422


# --- Acceptance, plans and debt -------------------------------------------


def test_acceptance_builds_staged_plan_and_exact_debt() -> None:
    stores, paciente, _historia, prestacion = _setup()
    otro = seed_prestacion(stores, nombre="Otra", precio="3000.25")
    owner = principal()
    service = presupuestos_service(stores)
    view = _enviado(
        stores,
        owner,
        paciente,
        [
            item_input(prestacion.id, precio_unitario="15000.50", etapa=1),
            item_input(otro.id, precio_unitario="3000.25", etapa=2),
            item_input(otro.id, precio_unitario="0.00", etapa=2),
        ],
    )
    aceptado = _run(service.aceptar(owner, view.presupuesto.id))
    assert aceptado.plan.etapas == 2
    assert aceptado.plan.etapa_actual == 1
    assert aceptado.plan.total == Decimal("18000.75")
    assert aceptado.movimiento is not None
    assert aceptado.movimiento.monto == Decimal("18000.75")
    assert aceptado.movimiento.referencia == (
        f"presupuesto:{view.presupuesto.id}"
    )

    plan_view = _run(service.obtener_plan(owner, aceptado.plan.id))
    assert [etapa.etapa for etapa in plan_view.etapas] == [1, 2]
    assert len(plan_view.etapas[1].items) == 2
    assert plan_view.etapas[0].subtotal == Decimal("15000.50")

    cuenta = _run(cuenta_service(stores).obtener(owner, paciente.id))
    assert cuenta.saldo == Decimal("18000.75")
    assert len(cuenta.movimientos) == 1


def test_acceptance_is_idempotent() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _enviado(stores, owner, paciente, [item_input(prestacion.id)])
    first = _run(service.aceptar(owner, view.presupuesto.id))
    second = _run(service.aceptar(owner, view.presupuesto.id))
    assert first.plan.id == second.plan.id
    assert first.movimiento is not None and second.movimiento is not None
    assert first.movimiento.id == second.movimiento.id
    assert len(stores.planes._rows) == 1
    assert len(stores.movimientos._rows) == 1
    cuenta = _run(cuenta_service(stores).obtener(owner, paciente.id))
    assert cuenta.saldo == Decimal("15000.50")


def test_plan_store_keeps_one_plan_per_budget() -> None:
    stores = build_stores()
    plan = PlanTratamientoRecord(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        presupuesto_id=uuid.uuid4(),
        paciente_id=uuid.uuid4(),
        total=Decimal("1.00"),
        etapas=1,
    )
    _run(stores.planes.add(plan))
    _run(
        stores.planes.add(
            PlanTratamientoRecord(
                id=uuid.uuid4(),
                tenant_id=plan.tenant_id,
                presupuesto_id=plan.presupuesto_id,
                paciente_id=plan.paciente_id,
                total=Decimal("2.00"),
                etapas=1,
            )
        )
    )
    assert len(stores.planes._rows) == 1
    stored = _run(
        stores.planes.get_by_presupuesto(
            plan.tenant_id, plan.presupuesto_id
        )
    )
    assert stored is not None
    assert stored.id == plan.id
    assert stored.total == Decimal("1.00")


def test_invasive_plan_requires_signed_consent() -> None:
    stores, paciente, historia, prestacion = _setup(invasiva=True)
    owner = principal()
    service = presupuestos_service(stores)
    view = _enviado(stores, owner, paciente, [item_input(prestacion.id)])

    with pytest.raises(AppError) as exc:
        _run(service.aceptar(owner, view.presupuesto.id))
    assert _status(exc) == 409
    assert not stores.planes._rows
    assert not stores.movimientos._rows
    sigue = _run(service.obtener(owner, view.presupuesto.id))
    assert sigue.presupuesto.estado == "enviado"

    consentimiento = firmar_consentimiento(
        stores, owner, historia_id=historia.id
    )
    aceptado = _run(service.aceptar(owner, view.presupuesto.id))
    assert aceptado.plan.consentimiento_id == consentimiento.id


def test_non_invasive_plan_needs_no_consent() -> None:
    stores, paciente, _historia, prestacion = _setup(invasiva=False)
    owner = principal()
    service = presupuestos_service(stores)
    view = _enviado(stores, owner, paciente, [item_input(prestacion.id)])
    aceptado = _run(service.aceptar(owner, view.presupuesto.id))
    assert aceptado.plan.consentimiento_id is None


# --- Account ---------------------------------------------------------------


def test_account_balance_and_tenant_scope() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    cuenta = cuenta_service(stores)
    vacia = _run(cuenta.obtener(owner, paciente.id))
    assert vacia.saldo == Decimal("0.00")
    assert vacia.movimientos == []

    _run(
        cuenta.registrar_debito(
            owner.tenant_id,
            paciente.id,
            monto="18000.75",
            descripcion="Debito ficticio",
            referencia="ficticio:1",
        )
    )
    _run(
        cuenta.registrar_debito(
            owner.tenant_id,
            paciente.id,
            monto="18000.75",
            descripcion="Duplicado",
            referencia="ficticio:1",
        )
    )
    saldo = _run(cuenta.obtener(owner, paciente.id))
    assert saldo.saldo == Decimal("18000.75")
    assert len(saldo.movimientos) == 1

    otro_paciente, _ = seed_paciente_historia(
        stores, dni="91000016", nombre="Otro Ficticio"
    )
    otro = _run(cuenta.obtener(owner, otro_paciente.id))
    assert otro.saldo == Decimal("0.00")


def test_movements_are_append_only() -> None:
    stores = build_stores()
    with pytest.raises(AppError) as exc:
        _run(stores.movimientos.update())
    assert _status(exc) == 409
    with pytest.raises(AppError) as exc:
        _run(stores.movimientos.delete())
    assert _status(exc) == 409


def test_account_read_roles_and_tenant_isolation() -> None:
    stores, paciente, _historia, _prestacion = _setup()
    cuenta = cuenta_service(stores)
    for rol in ("propietario", "odontologo", "recepcion"):
        assert _run(
            cuenta.obtener(principal(roles=(rol,)), paciente.id)
        ).saldo == Decimal("0.00")
    with pytest.raises(AppError) as exc:
        _run(cuenta.obtener(principal(roles=("asistente",)), paciente.id))
    assert _status(exc) == 403
    with pytest.raises(AppError) as exc:
        _run(cuenta.obtener(principal(tenant_id=TENANT_B), paciente.id))
    assert _status(exc) == 404


def test_plan_visibility_follows_clinical_access() -> None:
    stores, paciente, _historia, prestacion = _setup()
    owner = principal()
    service = presupuestos_service(stores)
    view = _enviado(stores, owner, paciente, [item_input(prestacion.id)])
    aceptado = _run(service.aceptar(owner, view.presupuesto.id))
    with pytest.raises(AppError) as exc:
        _run(
            service.obtener_plan(
                principal(roles=("odontologo",)), aceptado.plan.id
            )
        )
    assert _status(exc) == 403
    with pytest.raises(AppError) as exc:
        _run(
            service.obtener_plan(
                principal(tenant_id=TENANT_B), aceptado.plan.id
            )
        )
    assert _status(exc) == 404
