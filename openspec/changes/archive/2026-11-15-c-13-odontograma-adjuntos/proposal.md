# Proposal

## Why

C-12 dejó al paciente con historia clínica única y evoluciones append-only, pero el odontólogo todavía no puede diagnosticar ni documentar el tratamiento: no existe odontograma por pieza/superficie (RN-HC-02), no hay dónde guardar RX/fotos ligadas a la historia (RN-HC-05) y no hay consentimiento informado firmado que C-14 pueda exigir antes de un plan invasivo (RN-HC-04). Sin esta capa, US-031 queda incompleta y US-032 no tiene sobre qué presupuestar ni qué requisito verificar.

## What Changes

- Nueva capacidad `odontograma-adjuntos`: odontograma FDI por eventos, adjuntos clínicos y consentimientos firmados.
- `Odontograma` único por historia clínica (`UNIQUE (tenant_id, historia_clinica_id)`), con creación idempotente on-demand.
- `EventoPieza` **append-only**: pieza FDI + superficie + estado + fecha + autor (RN-HC-02). El estado actual de cada pieza/superficie se deriva del último evento, nunca se sobrescribe.
- Endpoints `GET /odontogramas/{historia_id}` (estado actual + historial), `POST /odontogramas/{historia_id}/eventos` y `GET /odontogramas/{historia_id}/eventos`.
- `Adjunto` ligado siempre a `historia_clinica_id` — nunca a un turno (RN-HC-05) — con tipo `rx|foto|documento`, `storage_key`, tamaño, MIME y SHA-256.
- Storage privado detrás de un puerto con URLs firmadas expirables (HMAC + TTL); backend `local` para dev/CI y `memory` para tests. S3 queda como adaptador futuro documentado, sin agregar dependencias en este change.
- `Consentimiento` con firma simple: hash SHA-256 de un payload canónico + timestamp + IP + dispositivo, más PDF generado y recuperable por URL firmada. Requerido para planes invasivos (RN-HC-04), con API de verificación que C-14 consumirá.
- Endpoints `POST /consentimientos`, `GET /consentimientos/{id}`, `GET /consentimientos/{id}/pdf` y `GET /pacientes/{id}/consentimientos`.
- Migración 009: `odontograma`, `evento_pieza`, `adjunto`, `consentimiento`, con RLS + FORCE RLS y trigger append-only sobre `evento_pieza`.

## Capabilities

### New Capabilities
- `odontograma-adjuntos`: odontograma FDI por eventos inmutables, adjuntos clínicos en storage privado con URLs firmadas y consentimientos firmados verificables por hash.

### Modified Capabilities

(ninguna: `pacientes-hce` ya expone historia clínica y visibilidad clínica; C-13 agrega recursos hijos sin cambiar sus requisitos)

## Impact

- Backend: dominio `clinica` (4 modelos), servicios de aplicación con stores `Protocol` + implementación SQLAlchemy y memoria, router `/api` para odontogramas, adjuntos y consentimientos, reutilizando `AccesoClinicoService` de C-12.
- Infraestructura: `infrastructure/storage.py` (puerto + `InMemoryStorage` + `LocalFilesystemStorage` con URLs firmadas) y `infrastructure/pdf.py` (escritor PDF mínimo sin dependencias), más variables de entorno nuevas.
- DB: migración 009 con 4 tablas, índices, checks FDI/superficie/estado, RLS/FORCE RLS y triggers append-only sobre `evento_pieza`.
- API: lectura de odontograma, alta de eventos, subida/listado/descarga firmada de adjuntos y alta/lectura/PDF de consentimientos.
- Tests: FDI válida/inválida, estado actual = último evento, append-only (UPDATE/DELETE rechazados), adjunto siempre ligado a historia, URL firmada expira y no cruza tenants, hash de consentimiento verificable, plan invasivo sin consentimiento detectable.
- Depende de C-12 (historia clínica y acceso clínico). No incluye presupuestos, planes de tratamiento ni deuda (C-14).
- Riesgo regulatorio (SU-04): la firma es electrónica simple (hash + timestamp + IP/dispositivo), no firma digital certificada; queda declarado como supuesto.
