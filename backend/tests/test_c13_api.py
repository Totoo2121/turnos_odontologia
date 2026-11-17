"""C-13 task 6.x: clinical HTTP surface over the real router (memory rig)."""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

import pytest
from fastapi.testclient import TestClient

from tests.support_c13 import (
    TENANT_B,
    build_client,
    build_stores,
    principal,
    seed_paciente_historia,
)

RX = b"rx-ficticia-c13-bytes"
TEXTO = "Consentimiento informado ficticio para pruebas automatizadas."


def _rig(who=None, *, max_bytes: int = 1024 * 1024):  # type: ignore[no-untyped-def]
    stores = build_stores(max_bytes=max_bytes)
    owner = who or principal()
    paciente, historia = seed_paciente_historia(stores, who=owner)
    client = build_client(stores, owner, max_bytes=max_bytes)
    return client, stores, owner, paciente, historia


def _evento(client: TestClient, historia_id, **body):  # type: ignore[no-untyped-def]
    payload = {"pieza_fdi": 16, "estado": "sano"}
    payload.update(body)
    return client.post(f"/api/odontogramas/{historia_id}/eventos", json=payload)


def _upload(client: TestClient, historia_id, **extra):  # type: ignore[no-untyped-def]
    data = {"tipo": "rx"}
    data.update(extra.pop("data", {}))
    files = {
        "archivo": (
            extra.pop("filename", "rx-ficticia.jpg"),
            RX,
            extra.pop("content_type", "image/jpeg"),
        )
    }
    return client.post(
        f"/api/historias-clinicas/{historia_id}/adjuntos",
        data=data,
        files=files,
        **extra,
    )


def _consent(client: TestClient, historia_id, **overrides):  # type: ignore[no-untyped-def]
    payload = {
        "historia_clinica_id": str(historia_id),
        "tipo": "tratamiento",
        "texto": TEXTO,
        "texto_version": "v1-2026-11",
        "firmante_nombre": "Paciente Ficticio C-13",
        "firmante_dni": "91000001",
    }
    payload.update(overrides)
    return client.post("/api/consentimientos", json=payload)


# --- Odontograma -----------------------------------------------------------


def test_get_odontograma_creates_and_returns_current_state() -> None:
    """WHEN the odontogram is fetched THEN 200 with an empty current state."""
    client, _stores, _owner, _paciente, historia = _rig()
    response = client.get(f"/api/odontogramas/{historia.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["historia_clinica_id"] == str(historia.id)
    assert body["estado_actual"] == []


def test_post_event_then_current_state_reflects_it() -> None:
    """WHEN an event is posted THEN 201 and the current state updates."""
    client, _stores, _owner, _paciente, historia = _rig()
    created = _evento(
        client, historia.id, pieza_fdi=16, estado="caries", superficie="oclusal"
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["pieza_fdi"] == 16
    assert body["superficie"] == "oclusal"
    assert body["autor_usuario_id"] == str(uuid.UUID(_owner.sub))

    current = client.get(f"/api/odontogramas/{historia.id}").json()
    assert [
        (row["pieza_fdi"], row["superficie"], row["estado"])
        for row in current["estado_actual"]
    ] == [(16, "oclusal", "caries")]

    history = client.get(f"/api/odontogramas/{historia.id}/eventos")
    assert history.status_code == 200
    assert [row["id"] for row in history.json()] == [body["id"]]


def test_author_in_body_is_ignored() -> None:
    """WHEN the body tries to set the author THEN the token author wins."""
    client, _stores, owner, _paciente, historia = _rig()
    impostor = str(uuid.uuid4())
    response = _evento(
        client,
        historia.id,
        autor_usuario_id=impostor,
        autor_profesional_id=impostor,
    )
    assert response.status_code == 201, response.text
    assert response.json()["autor_usuario_id"] == str(uuid.UUID(owner.sub))
    assert response.json()["autor_usuario_id"] != impostor


@pytest.mark.parametrize(
    "body",
    [
        {"pieza_fdi": 16, "estado": "caries"},
        {"pieza_fdi": 16, "estado": "corona", "superficie": "oclusal"},
        {"pieza_fdi": 10, "estado": "sano"},
        {"pieza_fdi": 16, "estado": "inventado"},
    ],
)
def test_invalid_event_bodies_are_422(body: dict[str, object]) -> None:
    """WHEN the FDI/surface/state contract breaks THEN 422."""
    client, _stores, _owner, _paciente, historia = _rig()
    response = _evento(client, historia.id, **body)
    assert response.status_code == 422, response.text


def test_odontograma_unknown_history_is_404() -> None:
    """WHEN the history does not exist THEN 404."""
    client, _stores, _owner, _paciente, _historia = _rig()
    assert client.get(f"/api/odontogramas/{uuid.uuid4()}").status_code == 404


def test_reception_is_forbidden_on_clinical_routes() -> None:
    """WHEN recepcion calls the clinical API THEN 403 (role guard)."""
    stores = build_stores()
    owner = principal()
    _paciente, historia = seed_paciente_historia(stores, who=owner)
    client = build_client(stores, principal(roles=("recepcion",)))
    assert client.get(f"/api/odontogramas/{historia.id}").status_code == 403
    assert _evento(client, historia.id).status_code == 403
    assert _upload(client, historia.id).status_code == 403


# --- Adjuntos --------------------------------------------------------------


def test_upload_list_and_download_through_signed_url() -> None:
    """WHEN an RX is uploaded THEN it is listed and downloadable by token."""
    client, _stores, _owner, _paciente, historia = _rig()
    uploaded = _upload(client, historia.id)
    assert uploaded.status_code == 201, uploaded.text
    adjunto = uploaded.json()
    assert adjunto["tipo"] == "rx"
    assert adjunto["size_bytes"] == len(RX)
    assert "turno_id" not in adjunto

    listed = client.get(f"/api/historias-clinicas/{historia.id}/adjuntos")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [adjunto["id"]]

    signed = client.get(f"/api/adjuntos/{adjunto['id']}/url")
    assert signed.status_code == 200, signed.text
    url = signed.json()["url"]
    parsed = urlparse(url)
    download = client.get(f"{parsed.path}?{parsed.query}")
    assert download.status_code == 200, download.text
    assert download.content == RX
    assert download.headers["cache-control"] == "private, no-store"


def test_upload_with_turno_id_is_rejected() -> None:
    """WHEN the client sends turno_id THEN 422 (RN-HC-05)."""
    client, stores, _owner, _paciente, historia = _rig()
    response = _upload(client, historia.id, data={"turno_id": str(uuid.uuid4())})
    assert response.status_code == 422, response.text
    assert stores.storage.objects == {}


def test_upload_disallowed_mime_is_422() -> None:
    """WHEN the file MIME is outside the allowlist THEN 422."""
    client, _stores, _owner, _paciente, historia = _rig()
    response = _upload(
        client,
        historia.id,
        filename="payload.exe",
        content_type="application/x-msdownload",
    )
    assert response.status_code == 422, response.text


def test_upload_over_limit_is_422() -> None:
    """WHEN the upload exceeds ADJUNTO_MAX_BYTES THEN 422."""
    client, _stores, _owner, _paciente, historia = _rig(max_bytes=8)
    response = _upload(client, historia.id)
    assert response.status_code == 422, response.text


def test_tampered_storage_token_is_403() -> None:
    """WHEN the signed token is altered THEN 403 and no bytes leak."""
    client, _stores, _owner, _paciente, historia = _rig()
    adjunto = _upload(client, historia.id).json()
    url = client.get(f"/api/adjuntos/{adjunto['id']}/url").json()["url"]
    parsed = urlparse(url)
    response = client.get(f"{parsed.path}?token=basura.invalida")
    assert response.status_code == 403


def test_adjunto_of_another_tenant_is_not_visible() -> None:
    """WHEN tenant B asks for tenant A attachment URL THEN 404."""
    client_a, stores, _owner, _paciente, historia = _rig()
    adjunto = _upload(client_a, historia.id).json()
    intruso = build_client(stores, principal(tenant_id=TENANT_B))
    response = intruso.get(f"/api/adjuntos/{adjunto['id']}/url")
    assert response.status_code == 404


# --- Consentimientos -------------------------------------------------------


def test_consent_flow_hash_pdf_and_listing() -> None:
    """WHEN a consent is created THEN hash verifies, PDF redirects and lists."""
    client, _stores, owner, paciente, historia = _rig()
    created = _consent(client, historia.id, tipo="cirugia")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["plan_invasivo"] is True
    assert body["hash_valido"] is True
    assert body["ip"] == "testclient"
    assert len(body["firma_hash"]) == 64
    assert body["created_by_usuario_id"] == str(uuid.UUID(owner.sub))

    fetched = client.get(f"/api/consentimientos/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["hash_valido"] is True

    pdf = client.get(f"/api/consentimientos/{body['id']}/pdf", follow_redirects=False)
    assert pdf.status_code == 302
    location = urlparse(pdf.headers["location"])
    download = client.get(f"{location.path}?{location.query}")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-1.4")

    listed = client.get(f"/api/pacientes/{paciente.id}/consentimientos")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]


def test_consent_invalid_payload_is_422() -> None:
    """WHEN the consent body omits required fields THEN 422."""
    client, _stores, _owner, _paciente, historia = _rig()
    response = _consent(client, historia.id, texto="")
    assert response.status_code == 422


def test_consent_unknown_history_is_404() -> None:
    """WHEN the consent points at an unknown history THEN 404."""
    client, _stores, _owner, _paciente, _historia = _rig()
    response = _consent(client, uuid.uuid4())
    assert response.status_code == 404


def test_consent_of_another_tenant_is_404() -> None:
    """WHEN tenant B reads tenant A consent THEN 404."""
    client_a, stores, _owner, _paciente, historia = _rig()
    consent = _consent(client_a, historia.id).json()
    intruso = build_client(stores, principal(tenant_id=TENANT_B))
    assert intruso.get(f"/api/consentimientos/{consent['id']}").status_code == 404


# --- Contrato OpenAPI ------------------------------------------------------


def test_clinical_routes_are_documented_in_openapi() -> None:
    """WHEN the app schema is generated THEN every C-13 route is published."""
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    expected = {
        "/api/odontogramas/{historia_id}": {"get"},
        "/api/odontogramas/{historia_id}/eventos": {"get", "post"},
        "/api/historias-clinicas/{historia_id}/adjuntos": {"get", "post"},
        "/api/adjuntos/{adjunto_id}/url": {"get"},
        "/api/storage/{key}": {"get"},
        "/api/consentimientos": {"post"},
        "/api/consentimientos/{consentimiento_id}": {"get"},
        "/api/consentimientos/{consentimiento_id}/pdf": {"get"},
        "/api/pacientes/{paciente_id}/consentimientos": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths, f"missing OpenAPI path: {path}"
        assert methods <= set(paths[path]), f"missing methods for {path}"
