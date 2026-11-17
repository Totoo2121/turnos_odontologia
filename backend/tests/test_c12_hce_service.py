"""C-12 tasks 3.1/4.1/4.2/5.1/5.2: HCE, append-only notes, access."""

from __future__ import annotations

import asyncio
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.auth_service import Principal
from app.application.pacientes import PacienteService
from app.shared.exceptions import AppError
from tests.support_c12 import (
    TENANT_A,
    build_services,
    build_stores,
    principal,
)


def _setup():  # type: ignore[no-untyped-def]
    stores = build_stores()
    pacientes, historias, acceso = build_services(stores)
    owner = principal(roles=("propietario",))
    paciente = asyncio.run(
        PacienteService(stores.pacientes).crear(
            tenant_id=TENANT_A,
            nombre="Paciente Ficticio",
            telefono="+5491100000000",
            dni="90000010",
        )
    )
    return stores, pacientes, historias, acceso, owner, paciente


def _treating(stores, paciente, acceso):  # type: ignore[no-untyped-def]
    usuario_id = uuid.uuid4()
    profesional_id = uuid.uuid4()
    stores.acceso.registrar_profesional(usuario_id, profesional_id)
    stores.acceso.registrar_turno(TENANT_A, paciente.id, profesional_id)
    return principal(sub=usuario_id, roles=("odontologo",)), usuario_id


def test_primera_apertura_crea_historia() -> None:
    """WHEN no history exists THEN one empty history is created."""
    _stores, _pacientes, historias, _acceso, owner, paciente = _setup()
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    assert historia.paciente_id == paciente.id
    assert historia.alergias is None


def test_segunda_apertura_no_duplica() -> None:
    """WHEN the history already exists THEN the same row is returned."""
    _stores, _pacientes, historias, _acceso, owner, paciente = _setup()
    primera = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    segunda = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    assert primera.id == segunda.id


def test_actualizar_anamnesis() -> None:
    """WHEN a clinical role updates anamnesis THEN fields persist."""
    _stores, _pacientes, historias, _acceso, owner, paciente = _setup()
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    actualizada = asyncio.run(
        historias.actualizar_anamnesis(
            owner,
            historia.id,
            {
                "alergias": "Penicilina (ficticia)",
                "medicacion": "Ninguna (ficticia)",
                "antecedentes": "Sin antecedentes (ficticio)",
            },
        )
    )
    assert actualizada.alergias == "Penicilina (ficticia)"
    assert actualizada.medicacion == "Ninguna (ficticia)"
    assert actualizada.antecedentes == "Sin antecedentes (ficticio)"


def test_recepcion_no_edita_anamnesis() -> None:
    """WHEN reception updates anamnesis THEN 403 (RN-SE-03)."""
    _stores, _pacientes, historias, _acceso, owner, paciente = _setup()
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    recepcion = principal(roles=("recepcion",))
    with pytest.raises(AppError) as exc:
        asyncio.run(
            historias.actualizar_anamnesis(
                recepcion, historia.id, {"alergias": "x"}
            )
        )
    assert exc.value.status_code == 403


def test_evolucion_autor_sale_del_principal() -> None:
    """WHEN a treating professional writes THEN author comes from the JWT."""
    stores, _pacientes, historias, acceso, owner, paciente = _setup()
    treating, usuario_id = _treating(stores, paciente, acceso)
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    evolucion = asyncio.run(
        historias.registrar_evolucion(
            treating, historia.id, contenido="Control ficticio"
        )
    )
    assert evolucion.autor_usuario_id == usuario_id
    assert evolucion.autor_profesional_id is not None
    assert evolucion.created_at is None  # store stamps it


def test_evolucion_sin_usuario_valido_rechazada() -> None:
    """WHEN principal.sub is not a UUID THEN 422 (no anonymous author)."""
    stores, _pacientes, historias, acceso, owner, paciente = _setup()
    treating, _usuario_id = _treating(stores, paciente, acceso)
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    sin_sub = Principal(
        sub="no-es-uuid",
        tenant_id=TENANT_A,
        roles=("propietario",),
        email="sin-sub@demo-ficticia.invalid",
    )
    with pytest.raises(AppError) as exc:
        asyncio.run(
            historias.registrar_evolucion(
                sin_sub, historia.id, contenido="Nota ficticia"
            )
        )
    assert exc.value.status_code == 422


def test_correccion_trazable_y_referencia_invalida() -> None:
    """WHEN correcting THEN a new row references the original; cross is 404."""
    stores, _pacientes, historias, acceso, owner, paciente = _setup()
    treating, _usuario_id = _treating(stores, paciente, acceso)
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    original = asyncio.run(
        historias.registrar_evolucion(
            treating, historia.id, contenido="Original ficticia"
        )
    )
    correccion = asyncio.run(
        historias.registrar_evolucion(
            treating,
            historia.id,
            contenido="Correccion ficticia",
            corrige_evolucion_id=original.id,
        )
    )
    assert correccion.corrige_evolucion_id == original.id
    assert correccion.id != original.id

    otro_paciente = asyncio.run(
        PacienteService(stores.pacientes).crear(
            tenant_id=TENANT_A,
            nombre="Otro Ficticio",
            telefono="+5491100000001",
            dni="90000011",
        )
    )
    otra_historia = asyncio.run(
        historias.obtener_o_crear(owner, otro_paciente.id)
    )
    with pytest.raises(AppError) as exc:
        asyncio.run(
            historias.registrar_evolucion(
                owner,
                otra_historia.id,
                contenido="Correccion invalida ficticia",
                corrige_evolucion_id=original.id,
            )
        )
    assert exc.value.status_code == 404


def test_tratante_accede_y_ajeno_denegado() -> None:
    """WHEN treating opens HCE THEN allowed; unrelated professional is 403."""
    stores, _pacientes, historias, acceso, owner, paciente = _setup()
    treating, _usuario_id = _treating(stores, paciente, acceso)
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    assert asyncio.run(historias.obtener(treating, historia.id)).id == historia.id

    ajeno = principal(roles=("odontologo",))
    with pytest.raises(AppError) as exc:
        asyncio.run(historias.obtener(ajeno, historia.id))
    assert exc.value.status_code == 403


def test_recepcion_no_lee_evoluciones() -> None:
    """WHEN reception lists evolutions THEN 403 (RN-SE-03)."""
    _stores, _pacientes, historias, _acceso, owner, paciente = _setup()
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    recepcion = principal(roles=("recepcion",))
    with pytest.raises(AppError) as exc:
        asyncio.run(historias.listar_evoluciones(recepcion, historia.id))
    assert exc.value.status_code == 403


def test_derivacion_habilita_acceso_del_destinatario() -> None:
    """WHEN owner derives to another professional THEN that one can read."""
    stores, _pacientes, historias, acceso, owner, paciente = _setup()
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))

    destinatario_id = uuid.uuid4()
    destinatario_usuario = uuid.uuid4()
    stores.acceso.registrar_profesional(destinatario_usuario, destinatario_id)
    destinatario = principal(
        sub=destinatario_usuario, roles=("odontologo",)
    )
    with pytest.raises(AppError):
        asyncio.run(historias.obtener(destinatario, historia.id))

    asyncio.run(
        historias.registrar_derivacion(
            owner,
            historia.id,
            hacia_profesional_id=destinatario_id,
            motivo="Interconsulta ficticia",
        )
    )
    assert asyncio.run(
        historias.obtener(destinatario, historia.id)
    ).id == historia.id


def test_derivacion_de_otro_paciente_no_habilita() -> None:
    """WHEN a derivation exists for another patient THEN access stays denied."""
    stores, _pacientes, historias, acceso, owner, paciente = _setup()
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    otro_paciente = asyncio.run(
        PacienteService(stores.pacientes).crear(
            tenant_id=TENANT_A,
            nombre="Otro Ficticio",
            telefono="+5491100000002",
            dni="90000012",
        )
    )
    otra_historia = asyncio.run(
        historias.obtener_o_crear(owner, otro_paciente.id)
    )
    destinatario_id = uuid.uuid4()
    destinatario_usuario = uuid.uuid4()
    stores.acceso.registrar_profesional(destinatario_usuario, destinatario_id)
    destinatario = principal(
        sub=destinatario_usuario, roles=("odontologo",)
    )
    asyncio.run(
        historias.registrar_derivacion(
            owner,
            otra_historia.id,
            hacia_profesional_id=destinatario_id,
        )
    )
    with pytest.raises(AppError) as exc:
        asyncio.run(historias.obtener(destinatario, historia.id))
    assert exc.value.status_code == 403


def test_no_clinico_no_deriva() -> None:
    """WHEN reception tries to derive THEN 403."""
    _stores, _pacientes, historias, _acceso, owner, paciente = _setup()
    historia = asyncio.run(historias.obtener_o_crear(owner, paciente.id))
    recepcion = principal(roles=("recepcion",))
    with pytest.raises(AppError) as exc:
        asyncio.run(
            historias.registrar_derivacion(
                recepcion,
                historia.id,
                hacia_profesional_id=uuid.uuid4(),
            )
        )
    assert exc.value.status_code == 403
