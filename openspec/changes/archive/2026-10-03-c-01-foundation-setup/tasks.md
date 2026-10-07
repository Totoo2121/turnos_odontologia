# Tasks — c-01-foundation-setup

## 1. Backend base (FastAPI async + settings + health)

- [x] 1.1 Crear layout `backend/app/{domain,application,infrastructure,api,worker}` + `backend/app/shared/` + `backend/tests/` con `__init__.py` y verificar con árbol de directorios esperado presente
- [x] 1.2 Agregar `Settings` Pydantic v2 con las 9 env vars (secretos requeridos sin default) y verificar que arrancar sin `JWT_SECRET` falla nombrando la variable (test de settings en `backend/tests/test_settings.py`)
- [x] 1.3 Implementar `GET /api/health` async (200 `{"status":"ok"}`, anónimo, JSON) + logger estructurado + handler base de excepciones y verificar con test de health vía TestClient/httpx en `backend/tests/test_health.py`
- [x] 1.4 Agregar sesión async SQLAlchemy 2.0 + asyncpg (engine + `get_db` dependency, pool modesto, convención de nombres lowercase) sin modelos de dominio y verificar con test de creación de engine/sesión contra Postgres de test

## 2. Migraciones + entorno reproducible (Alembic + Compose + env)

- [x] 2.1 Inicializar Alembic 1.13+ en modo async (`env.py` async, `script.py.mako`, `alembic.ini` apuntando a settings) + revisión baseline vacía y verificar con `alembic upgrade head` y `alembic current` sobre Postgres vacío (código 0 + revisión visible)
- [x] 2.2 Crear `.env.example` (raíz y/o por sub-proyecto) con las 9 vars documentadas y placeholders para secretos y verificar que `grep` no halla tokens/URLs reales y que las 9 claves existen
- [x] 2.3 Crear `docker-compose.yml` (`api` + `worker` misma imagen con CMD distinto + `postgres:15-alpine` con volumen nombrado y `pg_isready` + `redis` con `redis-cli ping`) y verificar con `docker compose up --build` (4 servicios healthy) y `GET /api/health` 200
- [x] 2.4 Agregar scaffold Celery + Redis (`backend/app/worker/`, app celery, sin tareas reales ni beat) y verificar que el servicio `worker` arranca y queda a la espera sin crash-loop en `compose ps/logs`

## 3. Frontend base (Vite + React 18 + TS + api-client)

- [x] 3.1 Scaffold Vite + React 18 + TypeScript estricto + Zustand con estructura `src/{features,shared,pages}` y verificar con `npm ci`, `tsc --noEmit` (código 0) y dev server sirviendo la shell
- [x] 3.2 Implementar `shared/api-client` (baseURL por env, interceptor 401 → refresh → 1 retry, storage versionado `turnos.auth.v1`, imports directos sin barrels) y verificar con tests de api-client (mock solo en borde HTTP: 401 con refresh válido reintenta 1 vez; refresh inválido limpia storage)
- [x] 3.3 Agregar build de producción (`npm run build` genera `dist/`) y verificar que el artefacto se sirve estáticamente sin errores de consola

## 4. CI + docs + verificación integral

- [x] 4.1 Crear `.github/workflows/ci.yml` (jobs paralelos: backend `ruff`/`black`+`mypy`+`pytest` con Postgres service; frontend `tsc --noEmit`+build) y verificar que un push/PR muestra ambos jobs en verde (o `act` local si no hay runner)
- [x] 4.2 Escribir `README` de arranque (`compose up`, `alembic upgrade head`, `pytest`, `npm run dev/build`, datos ficticios solamente) y verificar que cada comando documentado corre tal cual está escrito desde un checkout limpio
- [x] 4.3 Verificación integral de fundación: compose limpio + health 200 + `alembic current` con revisión + `pytest` verde + `tsc`/`build` verdes y verificar con checklist ejecutado de punta a punta sin errores
