# Spec Delta — platform-foundation

## Purpose

Provee el entorno mínimo ejecutable y reproducible del SaaS (API + worker + Postgres + Redis, configuración por entorno, salud observable y CI verde) sobre el que se construyen todos los changes futuros.

## ADDED Requirements

### Requirement: Health endpoint observable
El sistema SHALL exponer `GET /api/health` que responde 200 con `{"status":"ok"}` cuando la API está viva, incluyendo estado de DB cuando esté configurada.

#### Scenario: API viva responde ok
- **WHEN** un cliente hace `GET /api/health` con la API corriendo
- **THEN** responde HTTP 200 con cuerpo `{"status":"ok"}` y `content-type: application/json`

#### Scenario: Health no requiere autenticación
- **WHEN** un cliente anónimo hace `GET /api/health` sin token
- **THEN** responde 200 (nunca 401/403)

### Requirement: Configuración por entorno con fail-fast
El sistema SHALL leer toda configuración desde variables de entorno vía settings tipados y SHALL fallar al arrancar si falta un secreto requerido.

#### Scenario: Arranque sin secreto requerido falla explícito
- **WHEN** la API arranca sin `JWT_SECRET` (o sin `DATABASE_URL`) definido
- **THEN** el proceso falla al arrancar con error que nombra la variable faltante

#### Scenario: Defaults solo para no-sensibles
- **WHEN** se inspecciona `.env.example` y el código de settings
- **THEN** las 9 vars (`DATABASE_URL`, `JWT_SECRET`, `WA_BSP_TOKEN`, `WA_PHONE_ID`, `MP_ACCESS_TOKEN`, `SLOT_PUBLIC_BASE_URL`, `REMINDER_T48H_HS`, `REMINDER_T24H_HS`, `DEFAULT_CANCEL_ANTICIP_HS`) están documentadas y ningún secreto tiene default hardcodeado

### Requirement: Entorno reproducible con Compose
El sistema SHALL proveer `docker-compose.yml` que levanta `api` + `worker` + `postgres:15+` + `redis` con healthchecks de modo que un checkout limpio arranca con dos comandos.

#### Scenario: Levantada limpia
- **WHEN** un dev ejecuta `docker compose up --build` en un checkout limpio con `.env` válido
- **THEN** los 4 servicios quedan `healthy/running` y `GET /api/health` responde 200

#### Scenario: Datos persisten ante reinicio
- **WHEN** se ejecuta `docker compose down` y luego `up` (sin `-v`)
- **THEN** los datos de Postgres se conservan (volumen nombrado)

### Requirement: Migraciones versionadas desde el día 1
El sistema SHALL tener Alembic inicializado en modo async con al menos una revisión baseline aplicable sobre una DB vacía.

#### Scenario: Upgrade sobre DB vacía
- **WHEN** se ejecuta `alembic upgrade head` contra un Postgres 15+ vacío
- **THEN** termina con código 0 y `alembic current` muestra una revisión (sin crear tablas de dominio)

### Requirement: Frontend arranca y api-client renueva sesión
El frontend SHALL compilar y servir la app base, y su api-client SHALL reintentar una vez con refresh ante un 401.

#### Scenario: Build de frontend verde
- **WHEN** se ejecuta `tsc --noEmit` y el build de producción en `frontend/`
- **THEN** ambos terminan con código 0 sin errores de tipos

#### Scenario: 401 dispara refresh y retry único
- **WHEN** una request autenticada recibe 401 con refresh válido disponible
- **THEN** el api-client pide nuevo access token y reintenta la request original una sola vez antes de fallar

### Requirement: CI paralela bloquea regresiones de fundación
El sistema SHALL tener workflow CI con jobs paralelos backend (pytest) y frontend (tsc + build) que fallan el PR si cualquiera falla.

#### Scenario: PR con backend roto no pasa CI
- **WHEN** un PR rompe un test de `backend/tests/`
- **THEN** el job backend reporta fallo y el workflow completo es rojo

#### Scenario: PR con error de tipos no pasa CI
- **WHEN** un PR introduce un error de TypeScript en `frontend/`
- **THEN** el job frontend reporta fallo y el workflow completo es rojo

### Requirement: Ningún secreto en código ni datos reales en repo
El sistema SHALL no contener secretos en código ni datos de pacientes reales en repo/ejemplos; todo ejemplo usa datos sintéticos marcados ficticios.

#### Scenario: Escaneo de secretos limpio
- **WHEN** se inspecciona el árbol versionado (`backend/`, `frontend/`, compose, workflows, docs de este change)
- **THEN** no hay tokens, claves ni URLs de DB reales, solo placeholders y referencias a env vars

#### Scenario: Ejemplos clínicos sintéticos
- **WHEN** se revisan seeds/ejemplos incluidos en C-01 (si los hay)
- **THEN** todo nombre/DNI/teléfono/HCE está marcado como ficticio o no existen datos de paciente
