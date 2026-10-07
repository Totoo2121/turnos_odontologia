# Proposal — c-01-foundation-setup

## Why

Sin scaffolding versionado no hay base sobre la que construir los 17 changes restantes: hoy el repo solo tiene docs (`knowledge-base/`, `CHANGES.md`) y ningún código ejecutable. C-01 crea el monorepo mínimo verificable (API + worker + Postgres + Redis vía Compose, CI verde) para desbloquear C-02/C-03.

## What Changes

- Estructura de monorepo según `08_arquitectura_propuesta.md` §Estructura: `backend/app/{domain,application,infrastructure,api,worker}`, `frontend/src/{features,shared,pages}` (+ `backend/alembic/`, `backend/tests/`, `frontend/tests/` o equivalente).
- Backend FastAPI 0.110+ mínimo: `GET /api/health` → `{"status":"ok"}` (+ chequeo de conectividad DB cuando aplique), settings Pydantic v2 leídas solo de entorno, logger estructurado, handler de excepciones base, sesión async SQLAlchemy + asyncpg.
- Alembic 1.13+ inicializado con `env.py` async y primera revisión vacía/baseline (sin tablas de dominio — eso es C-02).
- Frontend Vite + React 18 + TypeScript + Zustand con `api-client` base: instancia axios/fetch con baseURL configurable, interceptor 401 → refresh JWT → retry único, storage versionado mínimo para tokens.
- `docker-compose.yml` raíz con servicios `api` + `worker` + `postgres:15+` + `redis` (healthchecks, volúmenes, red común).
- `.env.example` (raíz y/o por sub-proyecto) con las 9 vars de `08` §Env vars: `DATABASE_URL`, `JWT_SECRET`, `WA_BSP_TOKEN`, `WA_PHONE_ID`, `MP_ACCESS_TOKEN`, `SLOT_PUBLIC_BASE_URL`, `REMINDER_T48H_HS`, `REMINDER_T24H_HS`, `DEFAULT_CANCEL_ANTICIP_HS` — secretos sin defaults hardcodeados.
- GitHub Actions CI con jobs paralelos: backend (`pytest`) y frontend (`tsc --noEmit` + `build`).
- Tests de fundación: health check (200 + payload), carga/validación de settings (falla sin secretos requeridos), conectividad DB en compose.
- Documentación mínima de arranque (`README` con `compose up`, `alembic upgrade head`, `pytest`).

## Capabilities

### New Capabilities

- `platform-foundation`: infraestructura base ejecutable del monorepo — health endpoint, settings por entorno, composición Docker (api/worker/postgres/redis), scaffolding frontend + api-client con refresh, CI paralela y tests de fundación. Es la capacidad durable que todos los changes futuros presuponen (entorno reproducible + contrato de salud + configuración).

### Modified Capabilities

- Ninguna (repo sin specs previas; `openspec list --specs` vacío).

## Impact

- Afecta: raíz del repo (nuevos `backend/`, `frontend/`, `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`). Nada existente se rompe — no hay código previo.
- APIs: solo `GET /api/health` (no versionada aún; versionado real en C-03+).
- Dependencias nuevas: FastAPI 0.110+, Alembic 1.13+, SQLAlchemy 2.0 async, asyncpg, Pydantic v2 + settings, pytest/httpx; Vite + React 18 + TS + Zustand; Postgres 15+, Redis; Node LTS para CI.
- Sistemas: requiere Docker Compose para dev/test de integración; CI requiere secrets solo en runner (ninguno hardcodeado).
- Fuera de alcance explícito: modelos de dominio, auth/RBAC, RLS, endpoints de negocio, integraciones MP/WA reales (stubs de env vars solamente), odontograma/HCE, pagos, notificaciones.
