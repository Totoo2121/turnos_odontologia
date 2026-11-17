"""C-13 task 5.x: informed consent service (hash, PDF, invasivo gate)."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.clinica import (
    ConsentimientoRecord,
    ConsentimientoService,
    canonical_consent_payload,
)
from app.shared.exceptions import AppError
from tests.support_c13 import (
    TENANT_B,
    build_services,
    build_stores,
    principal,
    seed_paciente_historia,
    seed_tratante,
)

TEXTO = (
    "Autorizo la realizacion del tratamiento odontologico descripto en la "
    "historia clinica ficticia. Firma electronica simple de prueba."
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _rig():  # type: ignore[no-untyped-def]
    stores = build_stores()
    owner = principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    return build_services(stores), stores, owner, paciente, historia


def _crear(services, owner, historia, **overrides):  # type: ignore[no-untyped-def]
    payload = {
        "historia_id": historia.id,
        "tipo": "tratamiento",
        "texto": TEXTO,
        "texto_version": "v1-2026-11",
        "firmante_nombre": "Paciente Ficticio C-13",
        "firmante_dni": "91000001",
        "ip": "203.0.113.10",
        "dispositivo": "test-device/ficticio",
    }
    payload.update(overrides)
    return _run(services.consentimientos.crear(owner, **payload))


def test_crear_persists_signed_consent_with_valid_hash() -> None:
    """WHEN a consent is signed THEN the canonical hash verifies."""
    services, _stores, owner, paciente, historia = _rig()
    record = _crear(services, owner, historia)

    assert record.paciente_id == paciente.id
    assert record.historia_clinica_id == historia.id
    assert len(record.firma_hash) == 64
    assert record.plan_invasivo is False
    assert record.ip == "203.0.113.10"
    assert record.dispositivo == "test-device/ficticio"
    assert record.created_by_usuario_id == uuid.UUID(owner.sub)
    assert ConsentimientoService.verificar(record) is True

    stored, valido = _run(services.consentimientos.obtener(owner, record.id))
    assert stored.id == record.id
    assert valido is True


@pytest.mark.parametrize(
    ("field_name", "new_value"),
    [
        ("texto", TEXTO + " Alterado."),
        ("tipo", "cirugia"),
        ("texto_version", "v2-2026-11"),
        ("firmante_nombre", "Otra Persona Ficticia"),
        ("firmante_dni", "99999999"),
        ("ip", "198.51.100.7"),
        ("dispositivo", "otro-dispositivo"),
        ("plan_invasivo", True),
    ],
)
def test_tampering_any_signed_field_breaks_verification(
    field_name: str, new_value: object
) -> None:
    """WHEN any signed field changes THEN verificar() returns False."""
    services, _stores, owner, _paciente, historia = _rig()
    record = _crear(services, owner, historia)
    alterado = replace(record, **{field_name: new_value})
    assert ConsentimientoService.verificar(alterado) is False


def test_canonical_payload_is_stable_and_key_sorted() -> None:
    """WHEN the payload is encoded twice THEN bytes match (detached verify)."""
    services, _stores, owner, paciente, historia = _rig()
    record = _crear(services, owner, historia)
    payload = canonical_consent_payload(
        tenant_id=record.tenant_id,
        paciente_id=record.paciente_id,
        historia_clinica_id=record.historia_clinica_id,
        tipo=record.tipo,
        plan_invasivo=record.plan_invasivo,
        texto=record.texto,
        texto_version=record.texto_version,
        firmante_nombre=record.firmante_nombre,
        firmante_dni=record.firmante_dni,
        firmado_at=record.firmado_at,
        ip=record.ip,
        dispositivo=record.dispositivo,
    )
    assert payload == canonical_consent_payload(
        tenant_id=record.tenant_id,
        paciente_id=record.paciente_id,
        historia_clinica_id=record.historia_clinica_id,
        tipo=record.tipo,
        plan_invasivo=record.plan_invasivo,
        texto=record.texto,
        texto_version=record.texto_version,
        firmante_nombre=record.firmante_nombre,
        firmante_dni=record.firmante_dni,
        firmado_at=record.firmado_at,
        ip=record.ip,
        dispositivo=record.dispositivo,
    )
    assert hashlib.sha256(payload).hexdigest() == record.firma_hash
    assert payload.startswith(b'{"dispositivo":')


@pytest.mark.parametrize(
    ("tipo", "override", "esperado"),
    [
        ("tratamiento", None, False),
        ("ortodoncia", None, False),
        ("datos", None, False),
        ("invasivo", None, True),
        ("cirugia", None, True),
        ("cirugia", False, False),
        ("tratamiento", True, True),
    ],
)
def test_plan_invasivo_is_derived_from_tipo(
    tipo: str, override: bool | None, esperado: bool
) -> None:
    """WHEN tipo is invasivo/cirugia THEN the invasivo flag is set by default."""
    services, _stores, owner, _paciente, historia = _rig()
    record = _crear(
        services, owner, historia, tipo=tipo, plan_invasivo=override
    )
    assert record.plan_invasivo is esperado


def test_pdf_is_generated_stored_and_downloadable() -> None:
    """WHEN a consent is signed THEN a deterministic PDF is stored + signed."""
    services, stores, owner, _paciente, historia = _rig()
    record = _crear(services, owner, historia)

    assert "/consentimientos/" in record.pdf_storage_key
    assert record.pdf_storage_key.endswith(".pdf")
    data, content_type = stores.storage.objects[record.pdf_storage_key]
    assert content_type == "application/pdf"
    assert data.startswith(b"%PDF-1.4")
    assert hashlib.sha256(data).hexdigest() == record.pdf_sha256
    assert record.firma_hash.encode() in data

    signed = _run(services.consentimientos.pdf_url(owner, record.id))
    token = parse_qs(urlparse(signed.url).query)["token"][0]
    assert stores.storage.verify_token(record.pdf_storage_key, token) == owner.tenant_id
    assert _run(stores.storage.get(record.pdf_storage_key)) == data


def test_invasive_consent_satisfies_the_c14_contract() -> None:
    """WHEN no invasive consent exists THEN the gate denies until one is signed."""
    services, _stores, owner, paciente, historia = _rig()
    assert (
        _run(services.consentimientos.tiene_consentimiento_invasivo(
            owner.tenant_id, paciente.id
        ))
        is False
    )
    _crear(services, owner, historia, tipo="tratamiento")
    assert (
        _run(services.consentimientos.tiene_consentimiento_invasivo(
            owner.tenant_id, paciente.id
        ))
        is False
    )
    _crear(services, owner, historia, tipo="cirugia")
    assert (
        _run(services.consentimientos.tiene_consentimiento_invasivo(
            owner.tenant_id, paciente.id
        ))
        is True
    )


def test_listar_por_paciente_is_newest_first() -> None:
    """WHEN two consents are listed THEN the latest firmado_at comes first."""
    services, _stores, owner, paciente, historia = _rig()
    first = _crear(services, owner, historia)
    second = _crear(services, owner, historia, tipo="invasivo")
    rows = _run(services.consentimientos.listar_por_paciente(owner, paciente.id))
    assert [row.id for row in rows] == [second.id, first.id]


def test_listar_unknown_paciente_is_404() -> None:
    """WHEN the patient does not exist THEN 404."""
    services, _stores, owner, _paciente, _historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(services.consentimientos.listar_por_paciente(owner, uuid.uuid4()))
    assert exc.value.status_code == 404


def test_listar_without_access_is_403() -> None:
    """WHEN an unrelated clinician lists consents THEN 403."""
    services, _stores, _owner, paciente, _historia = _rig()
    ajeno = principal(roles=("odontologo",))
    with pytest.raises(AppError) as exc:
        _run(services.consentimientos.listar_por_paciente(ajeno, paciente.id))
    assert exc.value.status_code == 403


def test_obtener_foreign_tenant_consent_is_404() -> None:
    """WHEN tenant B asks for tenant A consent THEN 404."""
    services, _stores, owner, _paciente, historia = _rig()
    record = _crear(services, owner, historia)
    intruso = principal(tenant_id=TENANT_B)
    with pytest.raises(AppError) as exc:
        _run(services.consentimientos.obtener(intruso, record.id))
    assert exc.value.status_code == 404


def test_treating_professional_can_sign() -> None:
    """WHEN a treating professional signs THEN authorship is the token sub."""
    stores = build_stores()
    owner = principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    services = build_services(stores)
    tratante, usuario_id, _profesional = seed_tratante(stores, paciente.id)
    record = _crear(services, tratante, historia, tipo="cirugia")
    assert record.created_by_usuario_id == usuario_id
    assert record.plan_invasivo is True


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"tipo": "inexistente"}, 422),
        ({"texto": "   "}, 422),
        ({"texto_version": ""}, 422),
        ({"firmante_nombre": "  "}, 422),
    ],
)
def test_invalid_consent_payload_is_422(
    overrides: dict[str, object], status: int
) -> None:
    """WHEN required/typed fields are invalid THEN 422 (nothing is stored)."""
    services, stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _crear(services, owner, historia, **overrides)
    assert exc.value.status_code == status
    assert stores.storage.objects == {}


def test_reception_cannot_sign() -> None:
    """WHEN recepcion signs a consent THEN 403 (RN-SE-03)."""
    services, _stores, _owner, _paciente, historia = _rig()
    recepcion = principal(roles=("recepcion",))
    with pytest.raises(AppError) as exc:
        _crear(services, recepcion, historia)
    assert exc.value.status_code == 403


def test_record_hash_matches_dataclass_defaults_of_pdf() -> None:
    """WHEN the PDF is re-rendered from the record THEN sha256 still matches."""
    services, _stores, owner, _paciente, historia = _rig()
    record = _crear(services, owner, historia)
    writer = services.consentimientos.pdf
    rebuilt = writer.render(ConsentimientoService._pdf_lines(record))
    assert hashlib.sha256(rebuilt).hexdigest() == record.pdf_sha256
    assert isinstance(record, ConsentimientoRecord)
