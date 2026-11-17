# Design

## Context

Ver `proposal.md` - Why. C-13 se apoya en el patrón ya establecido: modelos SQLAlchemy en `app/domain/<área>/models.py`, servicios de aplicación con `Protocol` de store + implementación in-memory para tests y SQLAlchemy para la API autenticada, routers en `app/api/`, `AccesoClinicoService` de C-12 para visibilidad clínica y migraciones Alembic numeradas con RLS + FORCE RLS.

Restricciones relevantes:
- La historia clínica ya existe (`historia_clinica`, 1:1 con paciente) y su acceso se resuelve con `AccesoClinicoService.puede_acceder` (propietario / tratante por turno / derivación).
- No existe infraestructura de storage ni de PDF en `backend/app`; tampoco `python-multipart` en `requirements.txt` (necesario para subir archivos).
- `Principal` trae `sub`, `tenant_id` y `roles`; no trae `profesional_id`. El vínculo es `profesional.usuario_id = principal.sub`.
- La migración vigente es `c12a1b2c3d4e5`; C-13 usa `c13a1b2c3d4e5` (009).
- Regla dura: toda tabla tenant lleva RLS + FORCE RLS; todo DDL va por migración Alembic.

## Goals / Non-Goals

**Goals:**
- Odontograma FDI 1:1 con la historia, con eventos inmutables y estado actual derivado.
- Adjuntos clínicos siempre ligados a la historia, con storage privado y URL firmada expirable.
- Consentimiento firmado con hash verificable, timestamp, IP y dispositivo, más PDF recuperable.
- Verificación de consentimiento invasivo reutilizable por C-14.
- Todo testeable sin Postgres y sin red mediante stores/storage in-memory.

**Non-Goals:**
- Presupuestos, planes de tratamiento, deuda y bloqueo efectivo de planes invasivos (C-14).
- Adaptador S3/GCS real: se define el puerto y se implementan `memory` + `local`; S3 queda documentado como extensión.
- Firma digital certificada (X.509) o validación legal de la firma electrónica (SU-04).
- Borrado, rotación o versionado de adjuntos; DICOM; OCR; plantillas de consentimiento versionadas por tenant.
- Frontend del odontograma (C-15).

## Decisions

**D1 - Dominio `clinica` separado de `pacientes`.**
`Odontograma`, `EventoPieza`, `Adjunto` y `Consentimiento` viven en `backend/app/domain/clinica/models.py` y se registran en `app/domain/__init__.py`. `pacientes` mantiene identidad + HCE; `clinica` agrupa los artefactos clínicos hijos y C-14 podrá sumar presupuestos/planes sin mezclar responsabilidades.

**D2 - Odontograma 1:1 con creación idempotente.**
`UNIQUE (tenant_id, historia_clinica_id)` + `obtener_o_crear(historia_id)`: si existe, se devuelve; si no, se crea vacío. Igual que la HCE de C-12, un segundo GET nunca duplica y una carrera se resuelve con `ON CONFLICT DO NOTHING` + relectura.

**D3 - FDI y superficies validadas en DB y en servicio.**
`pieza_fdi SMALLINT` con CHECK `pieza_fdi BETWEEN 11 AND 48 AND pieza_fdi % 10 BETWEEN 1 AND 8 AND pieza_fdi / 10 BETWEEN 1 AND 4` (dentición permanente, 32 piezas). `superficie` nullable con CHECK en `('oclusal','mesial','distal','vestibular','lingual','palatina','incisal')`.
Coherencia estado/superficie:
- `caries`, `obturacion`, `sellador` exigen superficie.
- `corona`, `endodoncia`, `extraccion`, `implante` prohíben superficie (aplican a la pieza completa).
- `sano` admite ambas.
La DB refuerza con dos CHECK (`evento_pieza_superficie_requerida` y `evento_pieza_superficie_prohibida`); el servicio devuelve 422 legible antes de tocar la DB.

**D4 - `evento_pieza` append-only, estado actual derivado.**
No se expone `PATCH`/`DELETE` y la migración crea `evento_pieza_append_only()` + triggers `BEFORE UPDATE OR DELETE` con `RAISE EXCEPTION`. La corrección es un evento nuevo. El estado actual se calcula por `(pieza_fdi, superficie)` tomando `ORDER BY fecha DESC, created_at DESC, id DESC`; `superficie NULL` agrupa los estados de pieza completa. Alternativa considerada: tabla `pieza` mutable con upsert, rechazada porque pierde trazabilidad y contradice el enfoque "por eventos" del scope.

**D5 - Autoría desde el token.**
`EventoPieza` guarda `autor_usuario_id` (FK `usuario`, NOT NULL) y `autor_profesional_id` (FK `profesional`, nullable). Ambos se resuelven desde `principal.sub`, nunca del body. Si `sub` no es UUID → 422. `fecha` es la fecha clínica (default ahora) y no puede ser futura; `created_at` usa reloj de DB.

**D6 - Adjunto siempre ligado a la historia (RN-HC-05).**
`Adjunto.historia_clinica_id` es NOT NULL y FK; **no existe** `turno_id` en la tabla ni en el contrato. El endpoint de subida cuelga de `/historias-clinicas/{id}/adjuntos`; si el body incluye `turno_id` se ignora el campo desconocido pero el recurso sigue siendo de historia (el modelo Pydantic usa `extra="forbid"` para devolver 422 explícito). Un turno que necesite la RX solo referencia el `historia_clinica_id`/`adjunto.id`.

**D7 - Storage como puerto + URL firmada HMAC.**
`infrastructure/storage.py` define `StoragePort` (`put`, `get`, `signed_url`, `verify_token`) con:
- `InMemoryStorage` (tests, sin disco).
- `LocalFilesystemStorage` (dev/CI): escribe bajo `STORAGE_LOCAL_ROOT` con clave opaca `{tenant_id}/{historia_id}/{uuid4}`, valida que la ruta resuelta quede dentro del root (anti path traversal) y firma URLs con `HMAC-SHA256(secret, f"{key}|{tenant_id}|{exp}")` en Base64 URL-safe.
La URL apunta a `GET /api/storage/{key}?token=...`. Ese endpoint no usa JWT: el token es la capacidad; verifica firma en tiempo constante, expiración y que la clave del token coincida con el path. TTL por `STORAGE_SIGNED_URL_TTL_SEG` (default 300 s). `STORAGE_BACKEND=s3` falla al construir el servicio con un error claro: adaptador futuro, no se agrega `boto3` en este change.

**D8 - Subida con límites y hash.**
`POST /historias-clinicas/{id}/adjuntos` es `multipart/form-data` (requiere `python-multipart`). Se leen los bytes una vez, se valida `len <= ADJUNTO_MAX_BYTES` (default 10 MiB) y MIME en `ADJUNTO_MIME_PERMITIDOS` (default `image/jpeg,image/png,image/webp,application/pdf`), se calcula `sha256` y recién entonces se escribe en storage. Si la escritura falla, no se persiste la fila. No hay endpoint de borrado: el adjunto es evidencia clínica.

**D9 - Consentimiento con payload canónico y hash.**
`Consentimiento` guarda `tipo` (`tratamiento|invasivo|cirugia|ortodoncia|datos`), `texto_version`, `texto`, `plan_invasivo`, `firmante_nombre`, `firmante_dni?`, `firmado_at`, `ip`, `dispositivo`, `firma_hash`, `pdf_storage_key`, `pdf_sha256`.
El hash es `SHA-256(canonical_json)` donde `canonical_json` es `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` codificado UTF-8 sobre: `tenant_id`, `paciente_id`, `historia_clinica_id`, `tipo`, `plan_invasivo`, `texto`, `texto_version`, `firmante_nombre`, `firmante_dni`, `firmado_at` (UTC ISO-8601 con microsegundos), `ip`, `dispositivo`. Una única función `_canonical_payload()` se usa al crear y al verificar para evitar drift; `GET /consentimientos/{id}` devuelve `hash_valido`.
`plan_invasivo` se deriva de `tipo` (`invasivo|cirugia` ⇒ true) salvo override explícito, para que C-14 no dependa de un booleano mal tipeado.

**D10 - PDF mínimo sin dependencias.**
`infrastructure/pdf.py` expone `PdfWriter` y `SimplePdfWriter`, que arma un PDF 1.4 de una página con Helvetica, texto escapado y wrapping simple, incluyendo firmante, tipo, fecha, paciente, hash y aviso de documento ficticio/sintético en tests. Es determinístico (sin fecha de creación embebida), de modo que el mismo payload produce los mismos bytes y `pdf_sha256` es estable. Alternativa: `reportlab`, rechazada para no sumar dependencia pesada en este change; el puerto permite cambiarla.

**D11 - Vigencia y verificación para planes invasivos.**
`ConsentimientoService.tiene_consentimiento_invasivo(tenant_id, paciente_id)` devuelve true si existe al menos un consentimiento con `plan_invasivo = true` para ese paciente. No hay expiración ni revocación en C-13: se documenta como deuda para C-14 (donde el plan concreto podrá exigir consentimiento posterior a la propuesta). `GET /pacientes/{id}/consentimientos` lista los consentimientos del paciente con acceso clínico.

**D12 - Errores uniformes.**
`AppError` con 404 (historia/odontograma/adjunto/consentimiento inexistente o de otro tenant), 403 (sin acceso clínico, URL firmada inválida/expirada), 409 (conflicto de unicidad del odontograma resuelto por relectura, no expuesto al cliente), 422 (FDI/superficie/estado/MIME/tamaño/autor inválidos, `turno_id` presente). Nunca se revela existencia en otro tenant.

**D13 - RLS + FORCE RLS en las cuatro tablas.**
La migración habilita y fuerza RLS con policy `tenant_id = current_setting('app.tenant_id')::uuid` `USING`/`WITH CHECK` en `odontograma`, `evento_pieza`, `adjunto` y `consentimiento`, replicando la migración 008. Los stores filtran además por tenant (defensa en profundidad).

**D14 - Reutilización de `AccesoClinicoService`.**
Odontograma, adjuntos y consentimientos no reimplementan visibilidad: reciben el `AccesoClinicoService` de C-12 y llaman `puede_acceder`/`profesional_actual`. Escritura clínica exige `may_modify_evolution` (propietario u odontólogo) más `puede_acceder`.

## Risks / Trade-offs

- [El log de eventos crece sin límite] → índice `(tenant_id, odontograma_id, pieza_fdi, superficie, fecha DESC)` y lectura del historial paginada por `limit/offset`.
- [Calcular estado actual en cada GET puede ser costoso] → la consulta agrupa por pieza/superficie con `DISTINCT ON` sobre el índice; para una boca son ≤ 32×6 filas.
- [`local` no sirve en múltiples réplicas] → documentado como dev/CI; producción requiere el adaptador S3 futuro detrás del mismo puerto.
- [Canonicalización JSON distinta entre crear y verificar] → una sola función y test de ida y vuelta con acentos y comillas.
- [IP detrás de proxy] → se usa `request.client.host`; `X-Forwarded-For` no se confía en este change (documentado).
- [URL firmada sin revocación] → TTL corto (300 s) y firma ligada a tenant+clave; revocación de adjuntos queda fuera de alcance.
- [Nueva dependencia `python-multipart`] → se agrega a `requirements.txt` con rango conservador.
- [Trigger append-only también bloquea correcciones por SQL] → la corrección es un evento nuevo; el mensaje de error lo explica.
- [Firma electrónica simple no equivale a firma digital] → supuesto SU-04 declarado; C-14 solo verifica presencia, no validez legal.

## Migration Plan

1. `alembic upgrade head` aplica `c13a1b2c3d4e5` (009): crea `odontograma`, `evento_pieza`, `adjunto`, `consentimiento`, índices, checks, policies RLS/FORCE y la función/triggers append-only de `evento_pieza`.
2. Rollback: `downgrade` elimina triggers, función, policies, índices y tablas en orden inverso; no toca `paciente`, `historia_clinica`, `evolucion` ni `derivacion_hce`.
3. Sin backfill: odontogramas y consentimientos se crean desde la API; los adjuntos existentes no existen todavía.

## Open Questions

- Ninguna que cambie specs, approach o tasks. La expiración/revocación de consentimientos y el adaptador S3 se registran como deuda explícita para C-14/producción.
