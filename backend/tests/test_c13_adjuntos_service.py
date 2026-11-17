"""C-13 task 4.x: attachment service (history-bound, hashed, signed URLs)."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from dataclasses import fields
from urllib.parse import parse_qs, urlparse

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest

from app.application.clinica import AdjuntoRecord
from app.shared.exceptions import AppError
from tests.support_c13 import (
    TENANT_B,
    build_services,
    build_stores,
    principal,
    seed_paciente_historia,
    seed_tratante,
)

RX_FICTICIA = b"contenido-de-radiografia-ficticia"


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _rig(max_bytes: int = 1024 * 1024):  # type: ignore[no-untyped-def]
    stores = build_stores(max_bytes=max_bytes)
    owner = principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    services = build_services(stores, max_bytes=max_bytes)
    return services, stores, owner, paciente, historia


def _subir(services, owner, historia, **overrides):  # type: ignore[no-untyped-def]
    payload = {
        "tipo": "rx",
        "nombre_original": "rx-ficticia.jpg",
        "content_type": "image/jpeg",
        "data": RX_FICTICIA,
    }
    payload.update(overrides)
    return _run(services.adjuntos.subir(owner, historia.id, **payload))


def test_upload_stores_bytes_and_verifiable_metadata() -> None:
    """WHEN an RX is uploaded THEN bytes, size, MIME and SHA-256 are persisted."""
    services, stores, owner, _paciente, historia = _rig()
    adjunto = _subir(services, owner, historia)

    assert adjunto.historia_clinica_id == historia.id
    assert adjunto.tipo == "rx"
    assert adjunto.size_bytes == len(RX_FICTICIA)
    assert adjunto.sha256 == hashlib.sha256(RX_FICTICIA).hexdigest()
    assert adjunto.content_type == "image/jpeg"
    assert adjunto.storage_key.startswith(f"{owner.tenant_id}/{historia.id}/")
    assert stores.storage.objects[adjunto.storage_key][0] == RX_FICTICIA


def test_attachment_record_never_carries_a_turno() -> None:
    """WHEN the record shape is inspected THEN there is no turno_id field."""
    assert "turno_id" not in {field.name for field in fields(AdjuntoRecord)}


def test_mime_parameter_is_normalized() -> None:
    """WHEN the client sends ``image/jpeg; charset=binary`` THEN it is stored."""
    services, _stores, owner, _paciente, historia = _rig()
    adjunto = _subir(
        services, owner, historia, content_type="image/jpeg; charset=binary"
    )
    assert adjunto.content_type == "image/jpeg"


def test_disallowed_mime_is_422() -> None:
    """WHEN the declared MIME is outside the allowlist THEN 422."""
    services, _stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _subir(
            services,
            owner,
            historia,
            nombre_original="payload.exe",
            content_type="application/x-msdownload",
        )
    assert exc.value.status_code == 422


def test_empty_file_is_422() -> None:
    """WHEN there are no bytes THEN 422 (nothing is stored)."""
    services, stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _subir(services, owner, historia, data=b"")
    assert exc.value.status_code == 422
    assert stores.storage.objects == {}


def test_oversized_file_is_422() -> None:
    """WHEN bytes exceed ADJUNTO_MAX_BYTES THEN 422 (nothing is stored)."""
    services, stores, owner, _paciente, historia = _rig(max_bytes=16)
    with pytest.raises(AppError) as exc:
        _subir(services, owner, historia, data=b"x" * 17)
    assert exc.value.status_code == 422
    assert stores.storage.objects == {}


def test_invalid_tipo_is_422() -> None:
    """WHEN tipo is not rx|foto|documento THEN 422."""
    services, _stores, owner, _paciente, historia = _rig()
    with pytest.raises(AppError) as exc:
        _subir(services, owner, historia, tipo="video")
    assert exc.value.status_code == 422


def test_upload_requires_write_role() -> None:
    """WHEN recepcion uploads THEN 403 (RN-SE-03)."""
    services, _stores, _owner, _paciente, historia = _rig()
    recepcion = principal(roles=("recepcion",))
    with pytest.raises(AppError) as exc:
        _subir(services, recepcion, historia)
    assert exc.value.status_code == 403


def test_upload_requires_clinical_access() -> None:
    """WHEN an unrelated odontologo uploads THEN 403."""
    services, _stores, _owner, _paciente, historia = _rig()
    ajeno = principal(roles=("odontologo",))
    with pytest.raises(AppError) as exc:
        _subir(services, ajeno, historia)
    assert exc.value.status_code == 403


def test_treating_professional_can_upload() -> None:
    """WHEN a treating professional uploads THEN it is accepted."""
    stores = build_stores()
    owner = principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    services = build_services(stores)
    tratante, usuario_id, _profesional = seed_tratante(stores, paciente.id)
    adjunto = _subir(services, tratante, historia, tipo="foto")
    assert adjunto.subido_por_usuario_id == usuario_id


def test_listar_returns_only_that_history() -> None:
    """WHEN two histories exist THEN each list stays scoped."""
    stores = build_stores()
    owner = principal()
    _p1, h1 = seed_paciente_historia(stores, who=owner, dni="91000011")
    _p2, h2 = seed_paciente_historia(
        stores, who=owner, dni="91000012", nombre="Otro Paciente Ficticio"
    )
    services = build_services(stores)
    a = _subir(services, owner, h1)
    b = _subir(services, owner, h2, tipo="documento", nombre_original="informe.pdf")
    assert [row.id for row in _run(services.adjuntos.listar(owner, h1.id))] == [a.id]
    assert [row.id for row in _run(services.adjuntos.listar(owner, h2.id))] == [b.id]


def test_signed_url_downloads_the_same_bytes() -> None:
    """WHEN a signed URL is issued THEN the token is tenant-bound and works."""
    services, stores, owner, _paciente, historia = _rig()
    adjunto = _subir(services, owner, historia)
    signed = _run(services.adjuntos.url_firmada(owner, adjunto.id))

    token = parse_qs(urlparse(signed.url).query)["token"][0]
    path_key = urlparse(signed.url).path.removeprefix("/api/storage/")
    assert path_key == adjunto.storage_key
    assert stores.storage.verify_token(adjunto.storage_key, token) == owner.tenant_id
    assert _run(stores.storage.get(adjunto.storage_key)) == RX_FICTICIA


def test_signed_url_for_foreign_tenant_attachment_is_404() -> None:
    """WHEN tenant B asks for tenant A attachment THEN 404."""
    services, _stores, owner, _paciente, historia = _rig()
    adjunto = _subir(services, owner, historia)
    intruso = principal(tenant_id=TENANT_B)
    with pytest.raises(AppError) as exc:
        _run(services.adjuntos.url_firmada(intruso, adjunto.id))
    assert exc.value.status_code == 404


def test_listar_unknown_history_is_404() -> None:
    """WHEN the history does not exist THEN 404."""
    services, _stores, owner, _paciente, _historia = _rig()
    with pytest.raises(AppError) as exc:
        _run(services.adjuntos.listar(owner, uuid.uuid4()))
    assert exc.value.status_code == 404


def test_storage_is_cleaned_when_the_store_fails() -> None:
    """WHEN persisting metadata fails THEN the orphaned object is deleted."""
    services, stores, owner, _paciente, historia = _rig()

    async def boom(_record):  # type: ignore[no-untyped-def]
        raise RuntimeError("db down (simulated)")

    stores.adjuntos.add = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        _subir(services, owner, historia)
    assert stores.storage.objects == {}


def test_original_name_is_sanitized_length() -> None:
    """WHEN the filename is huge THEN it is truncated to the column size."""
    services, _stores, owner, _paciente, historia = _rig()
    adjunto = _subir(services, owner, historia, nombre_original="r" * 400)
    assert len(adjunto.nombre_original) == 255
