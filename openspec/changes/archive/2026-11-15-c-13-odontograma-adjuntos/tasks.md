# Tasks

## 1. Modelo y migración

- [x] 1.1 Crear `Odontograma`, `EventoPieza`, `Adjunto` y `Consentimiento` en `backend/app/domain/clinica/models.py` (tenant, FK a `historia_clinica`/`paciente`, FDI/superficie/estado, storage keys y hash de firma) y registrarlos en `backend/app/domain/__init__.py`; verificar con un test nuevo que las tablas, columnas, checks y unicidades existen y que `app.shared.db.metadata` las expone.
- [x] 1.2 Crear la migración `c13a1b2c3d4e5` (down_revision `c12a1b2c3d4e5`) con las 4 tablas, índices, `uq_odontograma_tenant_historia`, checks de FDI/superficie/estado/tipo/hash, RLS/FORCE RLS y policies de aislamiento; verificar con `alembic upgrade head --sql` y un test de migración que inspecciona tablas, columnas, índices, checks y policies.
- [x] 1.3 Agregar `evento_pieza_append_only()` y triggers `BEFORE UPDATE OR DELETE` sobre `evento_pieza`, con su rollback en `downgrade`; verificar con un test que el SQL de la migración contiene la función, ambos triggers y que el downgrade los elimina.

## 2. Infraestructura de storage y PDF

- [x] 2.1 Agregar `python-multipart` a `backend/requirements.txt` y las variables `STORAGE_BACKEND`, `STORAGE_LOCAL_ROOT`, `STORAGE_SIGNED_URL_TTL_SEG`, `STORAGE_SIGNING_SECRET`, `ADJUNTO_MAX_BYTES` y `ADJUNTO_MIME_PERMITIDOS` a `app/shared/settings.py` (con fallback de firma y gate de prod análogo a `PORTAL_SECRET`); verificar con tests de settings que los defaults son seguros y que prod exige secreto explícito.
- [x] 2.2 Crear `backend/app/infrastructure/storage.py` con `StoragePort`, `InMemoryStorage` y `LocalFilesystemStorage` (clave opaca, anti path traversal, `put`/`get`/`signed_url`/`verify_token` con HMAC-SHA256 y expiración); verificar con tests de firma válida, firma adulterada, token expirado y clave fuera del root.
- [x] 2.3 Crear `backend/app/infrastructure/pdf.py` con `PdfWriter` y `SimplePdfWriter` (PDF 1.4 de una página, texto escapado y wrapping, salida determinística); verificar con tests que el PDF empieza con `%PDF-1.4`, contiene el hash y que el mismo payload produce los mismos bytes.

## 3. Odontograma

- [x] 3.1 Implementar `OdontogramaStore` y `EventoPiezaStore` (`Protocol`) con dobles in-memory y stores SQLAlchemy en `backend/app/application/clinica.py`, incluyendo `obtener_o_crear` idempotente con `ON CONFLICT DO NOTHING`; verificar con tests de aislamiento por tenant y de no duplicación.
- [x] 3.2 Implementar `OdontogramaService` con validación de FDI/superficie/estado, autoría desde `principal.sub`, fecha no futura y proyección del estado actual por `(pieza, superficie)` con `ORDER BY fecha DESC, created_at DESC, id DESC`; verificar con tests de estado actual, pieza inválida, superficie incoherente y autor tomado del token.
- [x] 3.3 Exponer `GET /odontogramas/{historia_id}`, `POST /odontogramas/{historia_id}/eventos` y `GET /odontogramas/{historia_id}/eventos` en `backend/app/api/clinica.py` con guardas clínicas de C-12; verificar con tests de propietario/tratante/derivado, 403 para ajeno/recepción y 404 cross-tenant.

## 4. Adjuntos

- [x] 4.1 Implementar `AdjuntoStore` y `AdjuntoService`: lectura de bytes acotada por `ADJUNTO_MAX_BYTES`, allowlist MIME, `sha256`, escritura en storage y persistencia ligada a `historia_clinica_id` (rechazo de `turno_id` con 422); verificar con tests de subida válida, MIME/tamaño inválido y adjunto siempre atado a historia.
- [x] 4.2 Exponer `GET /api/storage/{key}?token=` como descarga por capacidad (sin JWT, firma en tiempo constante + expiración) y agregar la entrada declarativa `("GET", "/api/storage/*")` a `PUBLIC_PATHS`; verificar con tests de descarga válida, token vencido/adulterado y acceso con token de otro tenant.
- [x] 4.3 Exponer `POST /historias-clinicas/{historia_id}/adjuntos`, `GET /historias-clinicas/{historia_id}/adjuntos` y `GET /adjuntos/{id}/url` en `backend/app/api/clinica.py`; verificar con tests de subida multipart, listado, URL firmada con TTL y 403/404 según acceso clínico.

## 5. Consentimientos

- [x] 5.1 Implementar `ConsentimientoStore` y `ConsentimientoService` con payload canónico único, `firma_hash` SHA-256, `firmado_at`/`ip`/`dispositivo`, generación de PDF y `verificar_hash`; verificar con tests de hash correcto, payload alterado (`hash_valido: false`) y determinismo del PDF.
- [x] 5.2 Exponer `POST /consentimientos`, `GET /consentimientos/{id}`, `GET /consentimientos/{id}/pdf` (302 a URL firmada) y `GET /pacientes/{paciente_id}/consentimientos` en `backend/app/api/clinica.py`; verificar con tests de creación, verificación, descarga y 404 cross-tenant.
- [x] 5.3 Implementar `tiene_consentimiento_invasivo(tenant_id, paciente_id)` y el mapeo `tipo` → `plan_invasivo`; verificar con tests de paciente con y sin consentimiento invasivo y de que un consentimiento de otro paciente no habilita.

## 6. Integración y cierre

- [x] 6.1 Registrar el router en `backend/app/main.py`, documentar las rutas y variables nuevas en `README.md` y `.env.example`; verificar con un test de OpenAPI que las rutas existen y con `ruff check` sobre los archivos nuevos.
- [x] 6.2 Escribir un test E2E del Flujo 3 (HCE → odontograma → adjunto → consentimiento invasivo → verificación) sin Postgres ni red; verificar que recepción/ajeno quedan fuera y que el consentimiento habilita el chequeo de C-14.
- [x] 6.3 Correr la suite completa (`python -m pytest -q`), `ruff check` y `alembic heads`, y actualizar `CHANGES.md`/tasks al cerrar; verificar que el head es `c13a1b2c3d4e5` y que no hay regresiones sobre la línea base de C-12.
