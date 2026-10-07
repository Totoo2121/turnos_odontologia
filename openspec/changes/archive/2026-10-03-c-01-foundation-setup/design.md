# Design — c-01-foundation-setup

## Context

Ver `proposal.md` (Why) y `specs/platform-foundation/spec.md` (contrato). Estado actual: repo solo-docs (sin `backend/`, `frontend/`, compose ni CI). Restricciones: stack fijado (FastAPI 0.110+, React 18 + Vite + TS, Postgres 15+, Alembic 1.13+, JWT, worker Celery/Redis o APScheduler, Compose), prioridad mantenibilidad, reglas duras de `AGENTS.md` (sin secretos en código, sin datos reales, sin DDL ad-hoc, RLS desde C-02). Greenfield: no hay compatibilidad hacia atrás que cuidar.

## Goals / Non-Goals

**Goals:**
- Checkout → `compose up` → API + worker + Postgres + Redis corriendo, con `GET /api/health` 200 y `alembic upgrade head` verde.
- Fronteras de módulo (`domain/application/infrastructure/api/worker`, `features/shared/pages`) que C-02/C-03 puedan rellenar sin reestructurar.
- CI paralela que proteja la fundación desde el primer PR.
- Dejar preparados (no implementados) los seams de C-02: pooling, `tenant_id`, RLS, `BaseRepository`/`UnitOfWork` documentados como siguiente paso.

**Non-Goals:**
- Ningún modelo de dominio, auth/RBAC, RLS, endpoint de negocio, ni integración MP/WA real (solo env vars vacías).
- Sin estrategia de versionado de API pública, sin CD, sin observabilidad más allá de logger estructurado + health.
- Sin PWA/offline, sin i18n, sin design system (solo shell mínimo para probar build + api-client).

## Decisions

1. **Layout monorepo según `08` §Estructura, con `shared/` backend explícito.**
   `backend/app/{domain,application,infrastructure,api,worker}` + `backend/app/shared/` (settings, logging, db, exceptions) + `backend/alembic/` + `backend/tests/`; `frontend/src/{features,shared,pages}`. `shared/` no está literal en el diagrama de `08` pero CHANGES.md §C-01 lo exige — se adopta CHANGES como precisión.
   Alternativa: `src/` layout o `core/` en vez de `shared/` — descartada por desviarse del contrato que C-02+ espera.

2. **Async end-to-end (FastAPI async + SQLAlchemy 2.0 async + asyncpg).**
   Cumple compact rule `python-fastapi-development`; evita mezclar sync/async que luego cuesta migrar. `env.py` de Alembic en modo async desde el inicio.
   Alternativa: SQLAlchemy sync + `psycopg2` — descartada (bloquearía el event loop bajo concurrencia del turnero).

3. **Settings Pydantic v2 + `pydantic-settings`, fail-fast, sin defaults para secretos.**
   Un `Settings` tipado con las 9 env vars de `08`; `REMINDER_*`/`DEFAULT_CANCEL_ANTICIP_HS` con defaults numéricos, todo lo sensible `Field()` requerido. Error de arranque nombra la var faltante.
   Alternativa: `os.getenv` disperso — descartada (no valida tipos ni falla temprano).

4. **Alembic baseline vacía + convención lista para C-02.**
   Primera revisión sin tablas de dominio; `naming_convention` + identificadores lowercase + guía de índices-en-FK y `timestamptz`/`numeric`/`jsonb+GIN` documentada (compact `supabase-postgres-best-practices`). Pool asyncpg con tamaño modesto; transacciones cortas. RLS/`FORCE RLS` no se crean aún (no hay tablas tenant) pero el design de C-02 la exige — se deja checklist en tasks.
   Alternativa: crear tablas tenant ya — descartada (es scope de C-02, governance CRÍTICO).

5. **Compose con 4 servicios, misma imagen api/worker con CMD distinto.**
   `api` (uvicorn) + `worker` (misma imagen, comando worker) + `postgres:15+` (volumen nombrado + healthcheck `pg_isready`) + `redis` (healthcheck `redis-cli ping`). Red común, `.env` file, puertos publicados solo para api/db en dev.
   Alternativa: Dockerfiles separados — descartada (duplica build; YAGNI).

6. **Worker: Celery + Redis scaffold mínimo (sin tareas reales).**
   KB admite Celery o APScheduler; se elige Celery porque compose ya exige Redis y C-11/C-09 (recordatorios, lista de espera, webhooks MP idempotentes) necesitan broker real con reintentos. En C-01 solo el esqueleto (app celery, ping task de ejemplo eliminable, sin beat programado).
   Alternativa: APScheduler in-process — descartada (no sobrevive a réplicas ni da backoff/fallback que RN-NO exige después).

7. **Frontend: Vite + React 18 + TS estricto + Zustand + api-client con refresh de un retry.**
   `shared/api-client`: instancia con `baseURL` de env, interceptor 401 → refresh → retry único → si falla, limpia storage versionado (`turnos.auth.v1`) y redirige a login. Imports directos (sin barrel files), `lazy()` reservado para pesados futuros (odontograma), `startTransition` para UI no urgente, `Promise.all()` para fetches independientes (compact `vercel-react-best-practices`).
   Alternativa: React Query/SWR ya — descartada (YAGNI en fundación; C-04 decide data-fetching).

8. **CI: un workflow, dos jobs paralelos, sin CD.**
   `.github/workflows/ci.yml`: `backend` (pip/uv install → ruff/black → mypy → pytest con Postgres service) y `frontend` (npm ci → `tsc --noEmit` → build). Falla rápido, sin deploy.
   Alternativa: workflows separados o CD a staging — descartada (acopla y adelanta decisiones de deploy).

9. **Testing fundación con TDD-seams públicos.**
   Tests solo en bordes públicos (compact `tdd`): `GET /api/health` vía TestClient/httpx, settings (falta secreto → error; ejemplo carga ok con env sintético), `alembic upgrade head` + conectividad en compose. Sin mocks de código propio; DB real (Postgres service/compose). Cobertura >80% exigible cuando haya lógica (hoy el divisor es mínimo — se mide pero no se finge con tautologías).

## Risks / Trade-offs

- [Riesgo] Versiones flotantes (`FastAPI 0.110+`, `postgres:15+`) rompen reproducibilidad → Mitigación: pin mayor (`fastapi>=0.110,<1`, `postgres:15-alpine`, Node LTS) + lockfiles (`requirements.lock`/`package-lock.json`).
- [Riesgo] `openspec new change` exigió minúsculas (`c-01-…` vs alias `C-01`) → Mitigación: alias documentado; CHANGES.md conserva `C-01`, el change real es `c-01-foundation-setup`.
- [Riesgo] Celery añade peso si el MVP inicial es chico → Mitigación: scaffold sin tareas; si en apply el equipo prefiere APScheduler, el seam (módulo `worker/`) lo permite sin tocar api (registrar en Open Questions).
- [Riesgo] Health con chequeo DB puede marcar 200 con DB caída si se implementa mal → Mitigación: spec exige estado DB; tasks piden test con DB detenida → 503/degraded (definir en apply, sin cambiar spec).
- [Trade-off] Sin RLS aún (no hay tablas) — aceptado; C-02 la impone con `FORCE RLS` por tabla tenant (regla dura).

## Migration Plan

Greenfield, sin migración de datos ni rollback de schema. Pasos de verificación tras apply: `docker compose up --build` → 4 servicios healthy; `GET /api/health` 200; `alembic upgrade head` + `alembic current` con revisión; `pytest` verde; `tsc --noEmit` + build verdes; `gh` CI verde (o `act` local si hay runner). Rollback: borrar `backend/`, `frontend/`, compose y workflow (nada previo que restaurar).

## Open Questions

- ¿Fijar `uv` vs `pip+venv` como gestor Python estándar del equipo? (No cambia specs ni tasks; decidir en apply. Propuesta: `uv` por velocidad, fallback pip.)
- ¿Celery beat programado desde C-01 o solo worker a la espera hasta C-11? Propuesta: worker sin beat hasta C-09/C-11.
- Puertos dev exactos y nombre de red/volumen (detalle de apply, sin impacto en specs).
