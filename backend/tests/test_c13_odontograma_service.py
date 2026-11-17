"""C-13 task 3.x: odontogram service (FDI events, current state, access).

Seams under test: ``OdontogramaService.obtener`` / ``listar_eventos`` /
``registrar_evento`` over in-memory stores. No HTTP, no Postgres.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import uuid
from datetime import UTC, datetime, timedelta

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.clinica import OdontogramaService
from app.shared.exceptions import AppError
from tests.support_c13 import (
    TENANT_B,
    build_services,
    build_stores,
    principal,
    seed_paciente_historia,
    seed_tratante,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _rig():  # type: ignore[no-untyped-def]
    stores = build_stores()
    owner = principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    return build_services(stores), stores, owner, paciente, historia


def test_obtener_creates_one_odontogram_per_history() -> None:
    """WHEN obtener runs twice THEN the same odontogram is returned."""
    services, stores, owner, _paciente, historia = _rig()
    first = _run(services.odontogramas.obtener(owner, historia.id))
    second = _run(services.odontogramas.obtener(owner, historia.id))
    assert first.odontograma.id == second.odontograma.id
    assert first.odontograma.historia_clinica_id == historia.id
    stored = _run(stores.odontogramas.get_by_historia(owner.tenant_id, historia.id))
    assert stored is not None and stored.id == first.odontograma.id


def test_obtener_unknown_history_is_404() -> None:
    """WHEN the history does not exist THEN 404 (no tenant leak)."""
    services, _stores, owner, _paciente, _historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(services.odontogramas.obtener(owner, uuid.uuid4()))
    assert exc.value.status_code == 404


def test_obtener_history_from_another_tenant_is_404() -> None:
    """WHEN a principal of tenant B asks for tenant A history THEN 404."""
    services, _stores, _owner, _paciente, historia = _rig()
    intruso = principal(tenant_id=TENANT_B)
    with pytest.raises(AppError) as exc:
        _run(services.odontogramas.obtener(intruso, historia.id))
    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    ("pieza", "estado", "superficie"),
    [
        (11, "sano", None),
        (16, "caries", "oclusal"),
        (18, "obturacion", "vestibular"),
        (21, "corona", None),
        (28, "endodoncia", None),
        (31, "sellador", "lingual"),
        (38, "extraccion", None),
        (41, "implante", None),
        (48, "sano", "incisal"),
    ],
)
def test_registrar_evento_accepts_valid_fdi(
    pieza: int, estado: str, superficie: str | None
) -> None:
    """WHEN a valid FDI piece/surface/state arrives THEN the event is stored."""
    services, stores, owner, _paciente, historia = _rig()
    evento = _run(
        services.odontogramas.registrar_evento(
            owner,
            historia.id,
            pieza_fdi=pieza,
            estado=estado,
            superficie=superficie,
        )
    )
    assert evento.pieza_fdi == pieza
    assert evento.estado == estado
    assert evento.superficie == superficie
    eventos = _run(
        services.odontogramas.listar_eventos(owner, historia.id)
    )
    assert [row.id for row in eventos] == [evento.id]


@pytest.mark.parametrize("pieza", [0, 9, 10, 19, 29, 39, 49, 50, 55, 100])
def test_registrar_evento_rejects_invalid_fdi(pieza: int) -> None:
    """WHEN FDI is outside 11..48 or has unit/decade 0/9 THEN 422."""
    services, _stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(
            services.odontogramas.registrar_evento(
                owner, historia.id, pieza_fdi=pieza, estado="sano"
            )
        )
    assert exc.value.status_code == 422


def test_caries_requires_surface() -> None:
    """WHEN caries arrives without surface THEN 422."""
    services, _stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(
            services.odontogramas.registrar_evento(
                owner, historia.id, pieza_fdi=16, estado="caries"
            )
        )
    assert exc.value.status_code == 422


def test_corona_forbids_surface() -> None:
    """WHEN corona arrives with surface THEN 422."""
    services, _stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(
            services.odontogramas.registrar_evento(
                owner,
                historia.id,
                pieza_fdi=16,
                estado="corona",
                superficie="oclusal",
            )
        )
    assert exc.value.status_code == 422


def test_unknown_surface_or_state_is_422() -> None:
    """WHEN surface/state are outside the enum THEN 422."""
    services, _stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(
            services.odontogramas.registrar_evento(
                owner,
                historia.id,
                pieza_fdi=16,
                estado="caries",
                superficie="raro",
            )
        )
    assert exc.value.status_code == 422
    with pytest.raises(AppError) as exc:
        _run(
            services.odontogramas.registrar_evento(
                owner, historia.id, pieza_fdi=16, estado="misterioso"
            )
        )
    assert exc.value.status_code == 422


def test_future_event_date_is_422() -> None:
    """WHEN fecha is more than 5 minutes ahead THEN 422."""
    services, _stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(
            services.odontogramas.registrar_evento(
                owner,
                historia.id,
                pieza_fdi=16,
                estado="sano",
                fecha=datetime.now(UTC) + timedelta(minutes=30),
            )
        )
    assert exc.value.status_code == 422


def test_state_is_last_event_per_piece_and_surface() -> None:
    """WHEN events accumulate THEN current state is the latest per key."""
    services, _stores, owner, _paciente, historia = _rig()
    base = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    for offset, (estado, superficie) in enumerate(
        [("caries", "oclusal"), ("obturacion", "oclusal"), ("sano", "oclusal")]
    ):
        _run(
            services.odontogramas.registrar_evento(
                owner,
                historia.id,
                pieza_fdi=16,
                estado=estado,
                superficie=superficie,
                fecha=base + timedelta(days=offset),
            )
        )
    _run(
        services.odontogramas.registrar_evento(
            owner,
            historia.id,
            pieza_fdi=16,
            estado="caries",
            superficie="mesial",
            fecha=base,
        )
    )

    view = _run(services.odontogramas.obtener(owner, historia.id))
    estado = {
        (row.pieza_fdi, row.superficie): row.estado
        for row in view.estado_actual
    }
    assert estado == {(16, "oclusal"): "sano", (16, "mesial"): "caries"}

    historial = _run(services.odontogramas.listar_eventos(owner, historia.id))
    assert len(historial) == 4, "append-only history must keep every event"


def test_same_date_uses_created_at_then_id_for_ordering() -> None:
    """WHEN two events share fecha THEN the later insert wins the projection."""
    services, _stores, owner, _paciente, historia = _rig()
    fecha = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    _run(
        services.odontogramas.registrar_evento(
            owner,
            historia.id,
            pieza_fdi=26,
            estado="caries",
            superficie="distal",
            fecha=fecha,
        )
    )
    latest = _run(
        services.odontogramas.registrar_evento(
            owner,
            historia.id,
            pieza_fdi=26,
            estado="obturacion",
            superficie="distal",
            fecha=fecha,
        )
    )
    view = _run(services.odontogramas.obtener(owner, historia.id))
    [actual] = view.estado_actual
    assert actual.estado == "obturacion"
    assert actual.evento_id == latest.id


def test_event_author_comes_from_the_principal() -> None:
    """WHEN an event is registered THEN author is the token principal."""
    stores = build_stores()
    owner = principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    services = build_services(stores)
    tratante, usuario_id, profesional_id = seed_tratante(
        stores, paciente.id
    )
    evento = _run(
        services.odontogramas.registrar_evento(
            tratante, historia.id, pieza_fdi=36, estado="sano"
        )
    )
    assert evento.autor_usuario_id == usuario_id
    assert evento.autor_profesional_id == profesional_id
    params = set(inspect.signature(OdontogramaService.registrar_evento).parameters)
    assert not {"autor_usuario_id", "autor_profesional_id"} & params


def test_treating_professional_can_read_and_write() -> None:
    """WHEN a treating professional acts THEN access is granted (RN-SE-02)."""
    stores = build_stores()
    owner = principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    services = build_services(stores)
    tratante, _usuario, _profesional = seed_tratante(stores, paciente.id)
    view = _run(services.odontogramas.obtener(tratante, historia.id))
    assert view.odontograma.historia_clinica_id == historia.id


def test_non_treating_clinician_is_403() -> None:
    """WHEN an odontologo has no turno/derivation THEN 403."""
    services, _stores, _owner, _paciente, historia = _rig()
    ajeno = principal(roles=("odontologo",))
    with pytest.raises(AppError) as exc:
        _run(services.odontogramas.obtener(ajeno, historia.id))
    assert exc.value.status_code == 403


def test_reception_cannot_write_events() -> None:
    """WHEN recepcion writes an event THEN 403 (RN-SE-03)."""
    services, _stores, _owner, _paciente, historia = _rig()
    recepcion = principal(roles=("recepcion",))
    with pytest.raises(AppError) as exc:
        _run(
            services.odontogramas.registrar_evento(
                recepcion, historia.id, pieza_fdi=16, estado="sano"
            )
        )
    assert exc.value.status_code == 403


def test_observaciones_are_trimmed() -> None:
    """WHEN observaciones carry whitespace THEN they are stored trimmed."""
    services, _stores, owner, _paciente, historia = _rig()
    evento = _run(
        services.odontogramas.registrar_evento(
            owner,
            historia.id,
            pieza_fdi=16,
            estado="sano",
            observaciones="  control anual ficticio  ",
        )
    )
    assert evento.observaciones == "control anual ficticio"
