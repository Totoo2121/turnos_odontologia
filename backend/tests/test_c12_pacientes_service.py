"""C-12 tasks 2.1/2.2: patient store + service rules (in-memory)."""

from __future__ import annotations

import asyncio
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.pacientes import PacienteService
from app.shared.exceptions import AppError
from tests.support_c12 import TENANT_A, TENANT_B, build_stores


def _service() -> PacienteService:
    return PacienteService(build_stores().pacientes)


def _crear(
    service: PacienteService,
    *,
    tenant_id: uuid.UUID = TENANT_A,
    nombre: str = "Paciente Ficticio",
    telefono: str = "+5491100000000",
    dni: str | None = "90000001",
    consentimiento_datos: bool = False,
    consentimiento_at=None,  # type: ignore[no-untyped-def]
):
    import datetime

    if consentimiento_datos and consentimiento_at is None:
        consentimiento_at = datetime.datetime(2026, 11, 14, tzinfo=datetime.UTC)
    return asyncio.run(
        service.crear(
            tenant_id=tenant_id,
            nombre=nombre,
            telefono=telefono,
            dni=dni,
            consentimiento_datos=consentimiento_datos,
            consentimiento_at=consentimiento_at,
        )
    )


def test_crear_y_obtener_paciente() -> None:
    """WHEN a patient is created THEN it is retrievable in its tenant."""
    service = _service()
    paciente = _crear(service)
    assert paciente.tenant_id == TENANT_A
    assert asyncio.run(
        service.obtener(TENANT_A, paciente.id)
    ).nombre == "Paciente Ficticio"


def test_paciente_aislado_por_tenant() -> None:
    """WHEN another tenant asks for the id THEN 404 (no data leaked)."""
    service = _service()
    paciente = _crear(service)
    with pytest.raises(AppError) as exc:
        asyncio.run(service.obtener(TENANT_B, paciente.id))
    assert exc.value.status_code == 404


def test_dni_duplicado_rechazado() -> None:
    """WHEN the same DNI is created twice in a tenant THEN 409."""
    service = _service()
    _crear(service, dni="90000002")
    with pytest.raises(AppError) as exc:
        _crear(service, nombre="Otro Ficticio", dni="90000002")
    assert exc.value.status_code == 409


def test_dni_duplicado_permitido_en_otro_tenant() -> None:
    """WHEN the same DNI exists in tenant B THEN tenant A accepts it."""
    service = _service()
    _crear(service, tenant_id=TENANT_A, dni="90000003")
    other = _crear(service, tenant_id=TENANT_B, dni="90000003")
    assert other.tenant_id == TENANT_B


def test_paciente_sin_dni_permitido() -> None:
    """WHEN DNI is absent THEN the patient is still usable."""
    service = _service()
    paciente = _crear(service, dni=None)
    assert paciente.dni is None


def test_consentimiento_verdadero_exige_fecha() -> None:
    """WHEN consent=True without a date THEN 422."""
    service = _service()
    with pytest.raises(AppError) as exc:
        asyncio.run(
            service.crear(
                tenant_id=TENANT_A,
                nombre="Paciente Ficticio",
                telefono="+5491100000000",
                consentimiento_datos=True,
                consentimiento_at=None,
            )
        )
    assert exc.value.status_code == 422


def test_consentimiento_con_fecha_se_guarda() -> None:
    """WHEN consent and date are provided THEN both persist."""
    service = _service()
    paciente = _crear(service, consentimiento_datos=True)
    assert paciente.consentimiento_datos is True
    assert paciente.consentimiento_at is not None


def test_fecha_sin_consentimiento_rechazada() -> None:
    """WHEN a date is sent with consent=False THEN 422."""
    import datetime

    service = _service()
    with pytest.raises(AppError) as exc:
        asyncio.run(
            service.crear(
                tenant_id=TENANT_A,
                nombre="Paciente Ficticio",
                telefono="+5491100000000",
                consentimiento_datos=False,
                consentimiento_at=datetime.datetime(
                    2026, 11, 14, tzinfo=datetime.UTC
                ),
            )
        )
    assert exc.value.status_code == 422


def test_actualizar_dni_duplicado_rechazado() -> None:
    """WHEN updating to an existing DNI THEN 409."""
    service = _service()
    uno = _crear(service, nombre="Uno Ficticio", dni="90000004")
    _crear(service, nombre="Dos Ficticio", dni="90000005")
    with pytest.raises(AppError) as exc:
        asyncio.run(
            service.actualizar(TENANT_A, uno.id, {"dni": "90000005"})
        )
    assert exc.value.status_code == 409


def test_borrado_sin_historial() -> None:
    """WHEN owner deletes a clean patient THEN it disappears from reads."""
    stores = build_stores()
    service = PacienteService(stores.pacientes)
    paciente = _crear(service)
    asyncio.run(service.borrar(TENANT_A, paciente.id))
    with pytest.raises(AppError) as exc:
        asyncio.run(service.obtener(TENANT_A, paciente.id))
    assert exc.value.status_code == 404


def test_borrado_con_turnos_rechazado() -> None:
    """WHEN a patient has turnos THEN delete is 409."""
    stores = build_stores()
    service = PacienteService(stores.pacientes)
    paciente = _crear(service)
    stores.pacientes.registrar_turno(TENANT_A, paciente.id)
    with pytest.raises(AppError) as exc:
        asyncio.run(service.borrar(TENANT_A, paciente.id))
    assert exc.value.status_code == 409


def test_borrado_con_evoluciones_rechazado() -> None:
    """WHEN a patient has evolutions THEN delete is 409."""
    stores = build_stores()
    service = PacienteService(stores.pacientes)
    paciente = _crear(service)
    stores.pacientes.registrar_evolucion(TENANT_A, paciente.id)
    with pytest.raises(AppError) as exc:
        asyncio.run(service.borrar(TENANT_A, paciente.id))
    assert exc.value.status_code == 409


def test_listado_paginado_y_busqueda() -> None:
    """WHEN listing THEN limit/offset and q filter name or DNI."""
    service = _service()
    for index in range(5):
        _crear(
            service,
            nombre=f"Paciente {index} Ficticio",
            dni=f"9000010{index}",
        )
    page = asyncio.run(service.listar(TENANT_A, limit=2, offset=1))
    assert len(page) == 2
    found = asyncio.run(service.listar(TENANT_A, q="90000103"))
    assert [p.dni for p in found] == ["90000103"]
