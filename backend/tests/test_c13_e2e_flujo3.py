"""C-13 task 6.2: E2E Flujo 3 (HCE → odontograma → adjuntos → consentimiento).

Runs the real routers (pacientes + clinica) over the in-memory rig: no
Postgres, no network, only fictitious data.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://fictitious:fake@localhost:5432/fake_db"
)
os.environ.setdefault("JWT_SECRET", "fictitious-test-secret-not-real")

from tests.support_c13 import (
    TENANT_A,
    TENANT_B,
    build_full_client,
    build_stores,
    principal,
)

TEXTO_CIRUGIA = (
    "Consentimiento informado ficticio para extraccion quirurgica de prueba. "
    "Firma electronica simple verificable por hash."
)


def test_flujo3_clinico_completo_sin_postgres_ni_red() -> None:
    """WHEN the clinical flow runs THEN odontogram, RX and consent hold rules."""
    stores = build_stores()
    owner = principal()
    owner_client = build_full_client(stores, owner)

    paciente = owner_client.post(
        "/api/pacientes",
        json={
            "nombre": "Paciente Flujo 3 Ficticio",
            "telefono": "+5491100000001",
            "dni": "90000130",
            "consentimiento_datos": True,
            "consentimiento_at": "2026-11-15T10:00:00Z",
        },
    )
    assert paciente.status_code == 201, paciente.text
    paciente_id = paciente.json()["id"]

    tratante_usuario = uuid.uuid4()
    tratante_profesional = uuid.uuid4()
    stores.acceso.registrar_profesional(tratante_usuario, tratante_profesional)
    stores.acceso.registrar_turno(
        TENANT_A, uuid.UUID(paciente_id), tratante_profesional
    )
    tratante = principal(sub=tratante_usuario, roles=("odontologo",))
    clinico = build_full_client(stores, tratante)

    historia = clinico.post(
        "/api/historias-clinicas", json={"paciente_id": paciente_id}
    )
    assert historia.status_code == 201, historia.text
    historia_id = historia.json()["id"]

    anamnesis = clinico.patch(
        f"/api/historias-clinicas/{historia_id}",
        json={
            "alergias": "Ninguna (ficticia)",
            "medicacion": "Ibuprofeno 400 mg (ficticio)",
            "antecedentes": "Sin antecedentes (ficticio)",
        },
    )
    assert anamnesis.status_code == 200, anamnesis.text

    evolucion = clinico.post(
        f"/api/historias-clinicas/{historia_id}/evoluciones",
        json={"contenido": "Control ficticio: caries oclusal en 16."},
    )
    assert evolucion.status_code == 201, evolucion.text

    # Odontograma: caries oclusal en 16, luego obturacion (historial intacto).
    caries = clinico.post(
        f"/api/odontogramas/{historia_id}/eventos",
        json={
            "pieza_fdi": 16,
            "superficie": "oclusal",
            "estado": "caries",
            "observaciones": "Lesion ficticia de prueba",
        },
    )
    assert caries.status_code == 201, caries.text
    obturacion = clinico.post(
        f"/api/odontogramas/{historia_id}/eventos",
        json={"pieza_fdi": 16, "superficie": "oclusal", "estado": "obturacion"},
    )
    assert obturacion.status_code == 201, obturacion.text
    extraccion = clinico.post(
        f"/api/odontogramas/{historia_id}/eventos",
        json={"pieza_fdi": 38, "estado": "extraccion"},
    )
    assert extraccion.status_code == 201, extraccion.text

    estado = clinico.get(f"/api/odontogramas/{historia_id}")
    assert estado.status_code == 200, estado.text
    actual = {
        (row["pieza_fdi"], row["superficie"]): row["estado"]
        for row in estado.json()["estado_actual"]
    }
    assert actual == {(16, "oclusal"): "obturacion", (38, None): "extraccion"}

    historial = clinico.get(f"/api/odontogramas/{historia_id}/eventos")
    assert historial.status_code == 200
    assert [row["id"] for row in historial.json()] == [
        caries.json()["id"],
        obturacion.json()["id"],
        extraccion.json()["id"],
    ]

    # Adjuntos: RX ligada a la historia (nunca al turno), descarga firmada.
    rx_bytes = b"rx-periapical-ficticia-flujo-3"
    rx = clinico.post(
        f"/api/historias-clinicas/{historia_id}/adjuntos",
        data={"tipo": "rx", "origen": "flujo3"},
        files={"archivo": ("rx-ficticia.jpg", rx_bytes, "image/jpeg")},
    )
    assert rx.status_code == 201, rx.text
    assert rx.json()["origen"] == "flujo3"
    assert rx.json()["content_type"] == "image/jpeg"

    signed = clinico.get(f"/api/adjuntos/{rx.json()['id']}/url")
    assert signed.status_code == 200, signed.text
    parsed = urlparse(signed.json()["url"])
    descarga = clinico.get(f"{parsed.path}?{parsed.query}")
    assert descarga.status_code == 200
    assert descarga.content == rx_bytes

    # RN-HC-04: un plan invasivo exige consentimiento firmado (contrato C-14).
    assert (
        len(
            clinico.get(f"/api/pacientes/{paciente_id}/consentimientos").json()
        )
        == 0
    )

    consentimiento = clinico.post(
        "/api/consentimientos",
        json={
            "historia_clinica_id": historia_id,
            "tipo": "cirugia",
            "texto": TEXTO_CIRUGIA,
            "texto_version": "v1-2026-11",
            "firmante_nombre": "Paciente Flujo 3 Ficticio",
            "firmante_dni": "90000130",
        },
    )
    assert consentimiento.status_code == 201, consentimiento.text
    firmado = consentimiento.json()
    assert firmado["plan_invasivo"] is True
    assert firmado["hash_valido"] is True

    verificado = clinico.get(f"/api/consentimientos/{firmado['id']}")
    assert verificado.status_code == 200
    assert verificado.json()["hash_valido"] is True

    pdf = clinico.get(
        f"/api/consentimientos/{firmado['id']}/pdf", follow_redirects=False
    )
    assert pdf.status_code == 302
    location = urlparse(pdf.headers["location"])
    documento = clinico.get(f"{location.path}?{location.query}")
    assert documento.status_code == 200
    assert documento.content.startswith(b"%PDF-1.4")

    listado = clinico.get(f"/api/pacientes/{paciente_id}/consentimientos")
    assert [row["id"] for row in listado.json()] == [firmado["id"]]

    # RN-SE-02/03: ajeno y recepcion quedan afuera; otro tenant no ve nada.
    ajeno = build_full_client(stores, principal(roles=("odontologo",)))
    assert ajeno.get(f"/api/odontogramas/{historia_id}").status_code == 403
    recepcion = build_full_client(stores, principal(roles=("recepcion",)))
    assert (
        recepcion.post(
            f"/api/odontogramas/{historia_id}/eventos",
            json={"pieza_fdi": 16, "estado": "sano"},
        ).status_code
        == 403
    )
    intruso = build_full_client(stores, principal(tenant_id=TENANT_B))
    assert intruso.get(f"/api/odontogramas/{historia_id}").status_code == 404
    assert (
        intruso.get(f"/api/consentimientos/{firmado['id']}").status_code == 404
    )
