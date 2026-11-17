# Turnos Odontología

SaaS multi-tenant de turnos + clínica odontológica (Argentina).
Fundación del monorepo (C-01): API FastAPI + worker Celery + Postgres + Redis
vía Docker Compose, frontend React 18 + Vite, CI paralela.

> Todos los ejemplos usan datos **ficticios**. Nunca commitear datos reales
> de pacientes ni secretos.

## Requisitos

- Docker Compose (daemon corriendo)
- Python 3.11+
- Node LTS (20+)

## Arranque

```bash
copy .env.example .env
docker compose up --build
```

Verificar salud de la API:

```bash
curl http://localhost:8000/api/health
```

Respuesta esperada: `{"status":"ok"}`.

## Notificaciones WhatsApp (C-11)

Recordatorios T-48h/T-24h, confirmación por webhook, recall de ausentes y
controles periódicos. El canal oficial es la **WhatsApp Business Cloud API**
de Meta (`WA_PHONE_ID` + `WA_BSP_TOKEN`); el email SMTP es el fallback.

Variables de entorno nuevas (ver `.env.example`; nunca commitear secretos
reales):

| Variable | Default | Uso |
|----------|---------|-----|
| `WHATSAPP_WEBHOOK_SECRET` | vacío | Valida `X-Hub-Signature-256` del webhook. Vacío = acepta en dev, fail-closed en prod. |
| `SMTP_HOST` / `SMTP_PORT` | `localhost` / `587` | Relay SMTP del fallback por email. |
| `SMTP_USER` / `SMTP_PASSWORD` | vacío | Credenciales SMTP (dejar vacío en dev). |
| `SMTP_FROM` | `no-reply@turnos.invalid` | Remitente de los emails. |
| `CONFIRMATION_THRESHOLD_HS` | `24` | Horas antes del turno para avisar a recepción si sigue sin confirmar. |
| `RECALL_AUSENTE_DIAS` | `7` | Días tras una ausencia para enviar el recall. |
| `NOTIF_MAX_INTENTOS` | `3` | Reintentos ante errores transitorios del BSP/SMTP. |
| `NOTIF_BACKOFF_BASE_S` | `0.5` | Base del backoff exponencial entre reintentos. |

Webhook público (sin JWT, con rate-limit y firma):

```
POST /webhooks/whatsapp
```

Flujo de plantillas:

1. El seed idempotente carga las plantillas aprobadas por tenant
   (`recordatorio_t48h`, `recordatorio_t24h`, `confirmacion`,
   `recall_ausente`, `control`, `aviso_recepcion`, `politica_cancelacion`)
   para `whatsapp` y `email`:
   `cd backend; python -m app.infrastructure.seed_c11` (requiere `TENANT_ID`).
2. `PlantillaMensaje` versiona por `(tenant_id, clave, canal, idioma, version)`;
   solo la versión activa más alta se usa. Re-ejecutar el seed no pisa ediciones.
3. El worker encola `Recordatorio` por `(turno, canal, tipo)` (idempotente),
   envía la plantilla aprobada y audita `pendiente`/`enviado`/`fallido`/
   `confirmado`. Si WhatsApp falla tras los reintentos, cae a email y, si
   también falla, deja una alerta interna (`aviso_recepcion`) visible en
   `GET /api/recordatorios?tipo=aviso_recepcion`.

## Pacientes e Historia Clínica (C-12)

Pacientes tenant-scoped y una HCE única por paciente con evoluciones
**append-only** (RN-HC-01). La visibilidad clínica sigue RN-SE-02/03: solo
propietario, profesional tratante (con al menos un turno del paciente) o un
profesional con derivación explícita; recepción y asistente gestionan datos
administrativos pero no leen ni escriben evoluciones.

Rutas autenticadas (`Authorization: Bearer <access>`):

| Método | Ruta | Roles |
|--------|------|-------|
| `GET` | `/api/pacientes?limit=&offset=&q=` | staff |
| `POST` | `/api/pacientes` | staff |
| `GET` | `/api/pacientes/{id}` | staff |
| `PATCH` | `/api/pacientes/{id}` | staff |
| `DELETE` | `/api/pacientes/{id}` | propietario |
| `POST` | `/api/historias-clinicas` | propietario / odontologo tratante o derivado |
| `GET` | `/api/historias-clinicas/{id}` | propietario / tratante / derivado |
| `PATCH` | `/api/historias-clinicas/{id}` | propietario / odontologo tratante |
| `GET` | `/api/historias-clinicas/{id}/evoluciones` | propietario / tratante / derivado |
| `POST` | `/api/historias-clinicas/{id}/evoluciones` | propietario / odontologo tratante |
| `POST` | `/api/historias-clinicas/{id}/derivaciones` | propietario / odontologo tratante |

Reglas:

1. El DNI es opcional; si se informa, es único por tenant entre pacientes
   activos.
2. `consentimiento_datos=true` exige `consentimiento_at`; la DB lo refuerza
   con CHECK.
3. `POST /api/historias-clinicas` es idempotente: devuelve la historia
   existente en lugar de duplicarla.
4. Una evolución nunca se edita ni se borra: la DB tiene triggers
   `BEFORE UPDATE OR DELETE` que la rechazan. La corrección es una **nueva**
   evolución con `corrige_evolucion_id`.
5. El autor de la evolución sale del token (`sub`), nunca del body.
6. El borrado de paciente es lógico (`is_active=false`) y solo procede si no
   tiene turnos ni evoluciones.

## Odontograma, adjuntos y consentimientos (C-13)

Odontograma FDI **por eventos** (append-only), adjuntos privados siempre ligados
a la historia clínica (nunca a un turno, RN-HC-05) y consentimientos firmados
con hash SHA-256 verificable + PDF (RN-HC-04). Mismos roles clínicos de C-12
(propietario / odontólogo tratante o derivado); recepción y asistente no
escriben ni leen piezas, adjuntos ni consentimientos.

| Método | Ruta | Roles |
|--------|------|-------|
| `GET` | `/api/odontogramas/{historia_id}` | propietario / tratante / derivado |
| `GET` | `/api/odontogramas/{historia_id}/eventos` | propietario / tratante / derivado |
| `POST` | `/api/odontogramas/{historia_id}/eventos` | propietario / odontólogo tratante |
| `GET` | `/api/historias-clinicas/{historia_id}/adjuntos` | propietario / tratante / derivado |
| `POST` | `/api/historias-clinicas/{historia_id}/adjuntos` | propietario / odontólogo tratante |
| `GET` | `/api/adjuntos/{adjunto_id}/url` | propietario / tratante / derivado |
| `GET` | `/api/storage/{key}?token=` | token firmado (sin JWT) |
| `POST` | `/api/consentimientos` | propietario / odontólogo tratante |
| `GET` | `/api/consentimientos/{id}` | propietario / tratante / derivado |
| `GET` | `/api/consentimientos/{id}/pdf` | propietario / tratante / derivado |
| `GET` | `/api/pacientes/{id}/consentimientos` | propietario / tratante / derivado |

Reglas:

1. **FDI válida**: 11–48, unidad 1–8, decena 1–4. `caries`, `obturacion` y
   `sellador` exigen superficie (`oclusal|mesial|distal|vestibular|lingual|palatina|incisal`);
   `corona`, `endodoncia`, `extraccion` e `implante` la prohíben. Validado en
   servicio y en CHECKs de la DB.
2. **Append-only**: un evento nunca se edita ni se borra (triggers
   `BEFORE UPDATE/DELETE`). El estado actual es el último evento por
   `(pieza_fdi, superficie)` ordenado por `fecha, created_at, id`; el historial
   completo sigue disponible.
3. **Adjuntos**: `POST` es `multipart/form-data` (`tipo`, `archivo`, `origen`).
   Enviar `turno_id` devuelve 422: la evidencia pertenece a la historia
   (RN-HC-05). Se valida MIME permitido y tamaño máximo y se persiste el
   `sha256` del contenido.
4. **Descarga firmada**: `GET /api/adjuntos/{id}/url` (y el PDF de
   consentimiento) devuelven una URL HMAC-SHA256 con expiración por defecto de
   300 s, ligada a `storage_key` + tenant. La ruta `/api/storage/{key}` no usa
   JWT: el token es la capacidad y valida tenant + expiración.
5. **Consentimiento**: la firma es electrónica simple (no certificada). El
   `firma_hash` es el SHA-256 de un JSON canónico (claves ordenadas, UTF-8) con
   paciente, historia, tipo, texto/versión, firmante, fecha UTC, IP y
   dispositivo. Alterar cualquier campo invalida la verificación
   (`hash_valido=false`). `tipo=invasivo|cirugia` marca `plan_invasivo` salvo
   override explícito, y `ConsentimientoService.tiene_consentimiento_invasivo`
   es el contrato que C-14 usa para bloquear planes invasivos sin firma.
6. **Autoría**: autor del evento y `created_by` del consentimiento salen del
   token (`sub`), nunca del body.

Variables de entorno (ver `.env.example`):

| Variable | Default | Uso |
|----------|---------|-----|
| `STORAGE_BACKEND` | `local` | `memory` (tests) / `local` (dev/CI) |
| `STORAGE_LOCAL_ROOT` | `var/storage` | raíz privada del backend local |
| `STORAGE_SIGNED_URL_TTL_SEG` | `300` | vigencia de las URLs firmadas |
| `STORAGE_SIGNING_SECRET` | vacío | secreto HMAC (obligatorio en `APP_ENV=prod`) |
| `PUBLIC_BASE_URL` | vacío | base de las URLs firmadas (cae a `SLOT_PUBLIC_BASE_URL`) |
| `ADJUNTO_MAX_BYTES` | `10485760` | tamaño máximo por adjunto |
| `ADJUNTO_MIME_PERMITIDOS` | `image/jpeg,image/png,image/webp,application/pdf` | allowlist MIME |

`STORAGE_BACKEND=s3` queda como adaptador futuro detrás de `StoragePort`; no se
incluye SDK de cloud en este change.

## Presupuestos, planes y cuenta corriente (C-14)

Presupuestos en **ARS** sobre las piezas del odontograma, aceptación que genera
un **plan de tratamiento por etapas** y la **deuda** en la cuenta corriente del
paciente. Mismos roles clínicos de C-12/C-13 para presupuestos y planes
(propietario / odontólogo tratante o derivado); la cuenta corriente se lee con
el permiso de cobros (propietario, odontólogo y recepción).

| Método | Ruta | Roles |
|--------|------|-------|
| `POST` | `/api/presupuestos` | propietario / odontólogo tratante o derivado |
| `GET` | `/api/presupuestos?paciente_id=&estado=&limit=&offset=` | propietario / odontólogo tratante o derivado |
| `GET` | `/api/presupuestos/{id}` | propietario / odontólogo tratante o derivado |
| `PATCH` | `/api/presupuestos/{id}` | propietario / odontólogo tratante o derivado |
| `DELETE` | `/api/presupuestos/{id}` | propietario / odontólogo tratante o derivado |
| `POST` | `/api/presupuestos/{id}/items` | propietario / odontólogo tratante o derivado |
| `PATCH` | `/api/presupuestos/{id}/items/{item_id}` | propietario / odontólogo tratante o derivado |
| `DELETE` | `/api/presupuestos/{id}/items/{item_id}` | propietario / odontólogo tratante o derivado |
| `POST` | `/api/presupuestos/{id}/enviar` | propietario / odontólogo tratante o derivado |
| `POST` | `/api/presupuestos/{id}/aceptar` | propietario / odontólogo tratante o derivado |
| `POST` | `/api/presupuestos/{id}/rechazar` | propietario / odontólogo tratante o derivado |
| `GET` | `/api/planes-tratamiento?paciente_id=` | propietario / odontólogo tratante o derivado |
| `GET` | `/api/planes-tratamiento/{id}` | propietario / odontólogo tratante o derivado |
| `GET` | `/api/pacientes/{id}/cuenta-corriente` | propietario / odontólogo / recepción |

Reglas:

1. **Dinero exacto**: precios y totales son `Decimal` con `Numeric(12,2)` y
   redondeo half-up. El total lo calcula siempre el servidor
   (`importe = cantidad × precio_unitario`, `total = Σ importes`) y la moneda es
   fija `ARS`: mandar otra moneda devuelve 422.
2. **Snapshot del ítem**: al crear un ítem se copian precio, descripción,
   pieza/superficie, etapa y `requiere_consentimiento` desde la prestación. Un
   cambio posterior del catálogo no altera presupuestos ya creados.
3. **`POST /api/presupuestos` acepta `items` inline** para el alta atómica: si un
   ítem es inválido (FDI fuera de 11–48, superficie no permitida, cantidad ≤ 0)
   no se persiste nada.
4. **Estados**: `borrador → enviado → aceptado | rechazado`. Editar cabecera,
   ítems o borrar solo procede en `borrador` (409 en cualquier otro estado); las
   transiciones inválidas también devuelven 409. `validez_hasta` se completa con
   `hoy + PRESUPUESTO_VALIDEZ_DIAS` y un presupuesto vencido no se acepta.
5. **Etapas**: cada ítem declara `etapa` (1..N). El plan agrupa los ítems por
   etapa, `etapas = max(etapa)` y arranca con `etapa_actual = 1`; no hay tabla
   de etapas.
6. **Aceptación idempotente**: aceptar crea (o reutiliza) un único plan por
   presupuesto y registra un único débito en la cuenta corriente con
   `referencia="presupuesto:{id}"`. Repetir el `POST /aceptar` devuelve el mismo
   `plan_id` y `movimiento_id`, sin duplicar deuda.
7. **Gate de consentimiento invasivo**: si algún ítem tiene
   `requiere_consentimiento`, la aceptación exige un consentimiento invasivo
   firmado de la historia (C-13); sin firma devuelve 409
   `consentimiento_requerido`, el presupuesto sigue `enviado` y no se crea plan
   ni deuda.
8. **Solo débito en C-14**: C-14 registra únicamente la deuda del plan aceptado. El saldo
   es derivado (`Σ débitos − Σ créditos`); los pagos manuales y el cobro en
   mostrador se agregan en C-15 (ver sección siguiente). Los movimientos son
   **append-only** (la DB rechaza `UPDATE`/`DELETE`).

Variables de entorno (ver `.env.example`):

| Variable | Default | Uso |
|----------|---------|-----|
| `PRESUPUESTO_VALIDEZ_DIAS` | `30` | días de vigencia por defecto de un presupuesto nuevo (entero positivo) |

## Ficha clínica y caja de mostrador (C-15)

La UI clínica y la caja consumen los contratos de C-12/C-13/C-14. Esta entrega
es **frontend + endpoints aditivos de cobro**, sin migración nueva:
`alembic heads` sigue en `d14a1b2c3d4e5`.

Rutas de la SPA (mismos guards de rol del shell):

| Ruta | Contenido | Roles |
|------|-----------|-------|
| `/pacientes` | búsqueda `q`, tabla paginada y apertura de ficha | staff |
| `/pacientes/{id}` | bloque administrativo + pestañas HCE, odontograma, adjuntos, presupuestos y consentimientos | datos admin: staff; pestañas clínicas: propietario / odontólogo tratante o derivado |
| `/caja` | deuda, movimientos, cobro manual, recibo y cierre del día | propietario, recepción y odontólogo (solo lectura) |

Cobros manuales:

| Método | Ruta | Roles |
|--------|------|-------|
| `POST` | `/api/pacientes/{id}/cuenta-corriente/pagos` | propietario / recepción |
| `GET` | `/api/movimientos-cc/{id}/recibo` | propietario / odontólogo / recepción |
| `GET` | `/api/caja/cierre?fecha=` | propietario / odontólogo / recepción |

Reglas:

1. Medios `efectivo|transferencia|mp` y monto mayor a cero; el pago es un
   crédito **append-only** de la cuenta corriente.
2. `idempotency_key` (máx. 48) se persiste en
   `referencia="pago:{medio}:{clave}"`: repetir la misma clave devuelve el mismo
   movimiento y saldo, sin duplicar el crédito ni el recibo.
3. El recibo PDF es determinístico (paciente, monto, medio, fecha, referencia y
   saldo resultante) y responde 404 cross-tenant.
4. El cierre del día usa `AGENDA_TZ` y expone `cobrado_total`, `por_medio`,
   `cantidad_pagos`, `deuda_generada`, `diferencia_caja`, `turnos_atendidos`, el
   detalle de movimientos y los turnos del día.
5. La ficha reutiliza el gate 409 `consentimiento_requerido` de C-14: la
   aceptación del presupuesto se reintenta después de firmar el consentimiento
   invasivo.
6. La HCE sigue append-only: la UI solo ofrece "Corregir evolución" (una nueva
   evolución con `corrige_evolucion_id`), nunca editar ni borrar la original.
7. Sin migración nueva. Queda como deuda explícita de C-06 la reprogramación de
   turnos y el alta de sobreturnos; C-15 solo cierra el turno como `atendido` y
   agenda el control.

## Migraciones

```bash
cd backend
alembic upgrade head
alembic current
```

La revisión baseline no crea tablas de dominio (llegan en C-02).

## Tests

Backend (desde la raíz del repo):

```bash
python -m pytest
```

Calidad backend (desde `backend/`):

```bash
ruff check .
black --check .
mypy app
```

Frontend (desde `frontend/`):

```bash
npm ci
npx tsc --noEmit
npm test
npm run build
npm run dev
```

## Estructura

- `backend/app/{domain,application,infrastructure,api,worker}` + `app/shared/`
- `backend/alembic/` — migraciones versionadas (modo async)
- `frontend/src/{features,shared,pages}` — shell + api-client con refresh JWT
- `docker-compose.yml` — `api` + `worker` + `postgres:15` + `redis`

## Skill propia del proyecto

La skill `odontologia-reglas-negocio` aplica RN-AG al planificar, implementar y revisar cambios de agenda. Codex la descubre en `.agents/skills/odontologia-reglas-negocio/SKILL.md`; `.opencode/skills/odontologia-reglas-negocio/SKILL.md` es su copia para OpenCode. La creó y revisó el equipo con la skill del sistema `skill-creator` de Codex. Ambas copias deben mantenerse sincronizadas.

## Configuración del Servidor MCP (PostgreSQL)

El MCP configurado es `@microsoft/postgres-mcp` (stdio). En Codex se registra globalmente en `%USERPROFILE%\.codex\config.toml` (Linux/macOS: `~/.codex/config.toml`), sin URL ni credenciales:

```powershell
codex mcp add postgres -- npx -y @microsoft/postgres-mcp run
codex mcp list
```

Reiniciar Codex después de agregarlo. La conexión a la base se guarda en un perfil separado y la contraseña en el Administrador de credenciales de Windows, no en el repositorio ni en la configuración del cliente.

### Perfil de solo lectura para la DB local

1. Levantar PostgreSQL de desarrollo: `docker compose up -d postgres` (configurar `.env` local desde `.env.example`; nunca subir `.env`).
2. Abrir `docker compose exec postgres psql -U turnos -d turnos` y crear un usuario de lectura. Dentro de `psql` ejecutar:

   ```sql
   CREATE ROLE turnos_mcp_ro LOGIN;
   GRANT CONNECT ON DATABASE turnos TO turnos_mcp_ro;
   GRANT USAGE ON SCHEMA public TO turnos_mcp_ro;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO turnos_mcp_ro;
   GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO turnos_mcp_ro;
   ALTER DEFAULT PRIVILEGES FOR ROLE turnos IN SCHEMA public
     GRANT SELECT ON TABLES TO turnos_mcp_ro;
   \password turnos_mcp_ro
   ```

   `\password` solicita la contraseña sin mostrarla. Usar una clave local de desarrollo, no copiarla al repo. Salir con `\q`.
3. Crear perfil MCP con acceso de lectura y guardarla en el keyring cuando lo solicite:

   ```powershell
   npx -y @microsoft/postgres-mcp connection add turnos-dev-ro "host=127.0.0.1 port=5432 user=turnos_mcp_ro dbname=turnos" --access-mode ro
   npx -y @microsoft/postgres-mcp connection set-password turnos-dev-ro
   npx -y @microsoft/postgres-mcp connection list
   ```

4. En una sesión nueva de Codex, comprobar `postgres_mcp_list_connection_profiles`, conectar con `postgres_mcp_connect` y ejecutar una consulta de metadatos con `postgres_mcp_query`. Por ejemplo, para inspeccionar las exclusiones de agenda:

   ```sql
   SELECT conname, contype, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'public.turno'::regclass AND contype = 'x'
   ORDER BY conname;
   ```

`postgres_mcp_query` es de solo lectura; `access_mode=ro` y los permisos SQL del rol restringen también las herramientas de escritura. Las políticas RLS/ FORCE RLS siguen aplicando. Usar solo DB local/de prueba con datos sintéticos; no conectar producción ni consultar datos de pacientes para preparar cambios.

### Diagnóstico

- MCP no aparece en Codex: revisar `codex mcp list` y reiniciar el cliente.
- No se conecta a PostgreSQL: verificar `docker compose ps postgres`, el puerto `5432` y `npx -y @microsoft/postgres-mcp connection list`.
- Error de permisos: confirmar grants al rol `turnos_mcp_ro`; mantenerlo sin privilegios de escritura.
- La consulta devuelve cero filas de negocio: RLS requiere contexto de tenant. Para esta integración consultar metadatos de esquema, no desactivar RLS.

La evidencia de una consulta MCP real sin datos de pacientes está en [`docs/skills-mcp/evidencias/mcp-postgres-constraints.json`](docs/skills-mcp/evidencias/mcp-postgres-constraints.json). La guía oficial de instalación, perfiles y herramientas: https://github.com/microsoft/postgres-mcp/blob/main/USAGE.md.
