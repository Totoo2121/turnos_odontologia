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
