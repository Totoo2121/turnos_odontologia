# Proposal — c-04-app-shell-frontend

## Why

Todas las UI de FASE 2/4/5 (agenda C-07, clínica/caja C-15, reportes C-16) necesitan un shell común: layout + rutas + sesión + guards por rol. Sin este change cada feature reimplementaría autenticación y autorización frontend, con riesgo de divergencia respecto de la matriz RBAC de C-03. Este change cierra GATE 3 por el lado frontend y desbloquea C-07/C-15 en paralelo al backend.

## What Changes

- **Routing con `react-router-dom` (v6+)**: `BrowserRouter` + rutas declaradas en `frontend/src/app/router.tsx`; `React.lazy` por módulo de ruta (agenda/clínica/caja/reportes/admin) para no inflar el bundle inicial.
- **Sesión**: extiende el `auth-store` Zustand existente (C-01) con `user/roles/status + login/logout/refresh` contra `POST /api/auth/login|refresh|logout` y `GET /api/auth/me`; reutiliza el `api-client` cookie-based de C-03 (401→refresh→retry único, refresh solo en cookie HttpOnly) sin rediseñarlo.
- **Guards por rol** según matriz KB 03: `RequireAuth` + `RequireRole(allowed[])`; redirecciones `→ /login` (no autenticado) y `→ /403` (sin permiso); mapa rol→rutas visibles para el nav.
- **Layout shell**: `AppShell` (header + nav por rol + outlet) para rutas privadas; `AuthLayout` minimal para `/login`; página `403` + `NotFound`.
- **Rutas**: `/login` (pública), `/agenda`, `/pacientes` (+ `/pacientes/:id` alias clínica base), `/caja`, `/reportes`, `/admin` (privadas con guards), `/403`, `*` → NotFound. Contenido real en sus changes; aquí placeholders con contrato de props/parámetros congelado.
- **Biblioteca base `shared/ui`**: `Table`, `Modal`, `Form` (Field+validación mínima), `Toast` — API mínima y componible, sin framework CSS nuevo (CSS plano / estilos inline del scaffold; sin Tailwind/MUI para no sumar peso al MVP).
- **Responsive web** (mobile-first CSS, sin breakpoints JS salvo necesidad); **sin apps nativas; sin PWA** (evaluada y descartada para el MVP: suma manifiestos/service-worker sin beneficio comprometido).
- **Tests**: guards como comportamiento (rol×ruta → render/redirect), flujo login/logout en el seam `fetch`, render del shell por rol.

## Capabilities

### New Capabilities

- `frontend-app-shell`: shell web autenticado — routing, sesión contra C-03, guards por rol según matriz 03, layout + nav por rol, librería `shared/ui` mínima, páginas placeholder con contrato para agenda/pacientes-caja/reportes/admin, y login/logout web.

### Modified Capabilities

(none — `platform-foundation` y `identity-auth` no cambian de comportamiento; este change solo consume sus contratos: endpoints `/api/auth/*`, cookie refresh HttpOnly, interceptor 401→refresh→retry.)

## Impact

- **Solo `frontend/`**: `src/app/` (router, providers), `src/features/auth/` (store extendido, hooks, páginas login), `src/shared/ui/` (4 componentes), `src/pages/` (placeholders), `src/shared/router/` o `src/app/guards` (guards). Nueva dependencia `react-router-dom`; ninguna otra dependencia nueva.
- **Sin cambios de backend ni migraciones**; consume endpoints C-03 tal cual.
- **Contrato para changes futuros**: C-07/C-15/C-16 implementan el contenido de sus rutas respetando el contrato de placeholders (path + params + guards); cambios de guards requieren delta spec de esta capability.
