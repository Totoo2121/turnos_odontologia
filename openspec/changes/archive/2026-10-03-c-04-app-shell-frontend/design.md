# Design — c-04-app-shell-frontend

## Context

Ver `proposal.md` (Why). Estado actual: Vite + React 18 + TS estricto + Zustand (C-01), `shared/api-client.ts` cookie-based con retry único ante 401 + `shared/storage.ts` versionado access-only (C-03 D2), `features/auth/auth-store.ts` mínimo (`accessToken + logout`). No hay router (solo `HomePage`), no hay guards, no hay `shared/ui`. Consumidores: C-07 (agenda), C-15 (clínica/caja), C-16 (reportes). Restricción: cero cambios backend; endpoints `/api/auth/*` se consumen tal cual.

## Goals / Non-Goals

**Goals:**

- Router + guards + sesión listos como fundación consumible por C-07/C-15/C-16 sin re-trabajo.
- Reutilizar (no rediseñar) el refresh cookie-based de C-03 y extender el store existente.
- Contrato de placeholders y de `shared/ui` que las features futuras respeten.

**Non-Goals:**

- Contenido de agenda/clínica/caja/reportes/admin (sus changes); validaciones de negocio; PWA/offline; i18n; theming; tests E2E (solo unit/integration en el seam fetch + render).

## Decisions

### D1 — `react-router-dom` v6 (BrowserRouter + route objects + `React.lazy` por ruta)

**Por qué:** API declarativa conocida, `loader`-free para el MVP (los datos los pide cada feature con el api-client), code-splitting trivial con `lazy()` + `Suspense`, sin DSL de tipos de search-params que el MVP no necesita.
**Alternativa descartada:** TanStack Router — superior en search-params tipados y loaders, pero suma concepto (route-trees generados) y peso para un MVP de 6 rutas estáticas; reevaluar si C-07 necesita estado de URL complejo (filtros de agenda compartibles).
**Performance (vercel-react-best-practices):** `lazy()` por módulo de ruta; imports directos (nunca barrels); `Suspense` por ruta para streaming del chunk; `startTransition` en cambios de ruta no urgentes (búsqueda futura); `content-visibility` reservado para listas largas de C-07, no aquí.

### D2 — Extender `features/auth/auth-store.ts` (no duplicar)

Store Zustand con `{ accessToken, user: {id,email,roles,tenantId} | null, status: 'idle|loading|authenticated|unauthenticated', login(email,password), logout(), hydrate() }`.
`login` usa `fetch` directo contra `/api/auth/login` (el api-client solo tiene `get`; se agrega `post` mínimo al cliente en este change) → guarda access → `hydrate()` con `GET /api/auth/me`. `logout` llama `/api/auth/logout` best-effort y limpia siempre. El access vive en memoria del store + `storage.ts` (ya access-only); el refresh jamás toca JS (cookie HttpOnly `Path=/api/auth`, `credentials:'include'` solo en refresh/logout/login).
**Alternativa descartada:** contexto React + `useReducer` — duplica lo que Zustand ya resuelve y complica el acceso fuera de componentes (guards/utilidades).

### D3 — Guards como componentes (`RequireAuth`, `RequireRole`) + tabla `ROLE_ROUTES`

```tsx
// src/app/guards.tsx — RequireAuth envuelve RequireRole; redirect con <Navigate state={{from}} replace />
ROLE_ROUTES: Record<RouteKey, Role[]> // única fuente para guards Y nav (no divergen)
```

`RequireRole` reevalúa ante cada cambio del store (suscripción, sin polling). `403` y `NotFound` como páginas propias. Los tests tratan guards como comportamiento: matriz rol×ruta → render/redirect (tdd).

### D4 — Estructura de archivos (respeta KB 08 §Estructura)

```
src/app/router.tsx        # route objects + lazy + Suspense
src/app/guards.tsx        # RequireAuth/RequireRole + ROLE_ROUTES
src/app/AppShell.tsx      # header/nav/outlet
src/app/AuthLayout.tsx    # layout login
src/features/auth/auth-store.ts  # extendido (D2)
src/features/auth/LoginPage.tsx
src/shared/ui/{Table,Modal,Form,Toast}.tsx  # props controladas, CSS plano
src/pages/{Agenda,Pacientes,PacienteDetalle,Caja,Reportes,Admin,Forbidden,NotFound}Placeholder.tsx
```

Placeholders exportan contrato documentado (path + params + roles) en comentario de cabecera para C-07/C-15/C-16.

### D5 — `shared/ui` API mínima (componible, controlada)

- `Table({columns:{key,header,render?}[], rows:{id,...}[], emptyText})` — sin sort/paginación (llegan con features).
- `Modal({open, onClose, title, children})` — ternario `open ? … : null` (nunca `&&`), foco en el diálogo al abrir, Escape cierra.
- `Form/Field({label, error, children})` — presenta error por prop; validación real en features.
- `Toast({message, kind, onDismiss})` — un mensaje por vez; cola simple en features si la necesitan.
- Sin dependencias CSS: CSS plano por componente junto al `.tsx`. Tokens (no sensibles) en `localStorage` versionado solo para prefs futuras; nada de sesión salvo access (C-03 D2).

### D6 — Sin PWA en el MVP

Manifiesto + service worker + estrategia de caché son costo sin requisito comprometido (KB 01: "PWA evaluable" ≠ comprometida; CHANGES C-04: "solo si no cuesta"). Decisión: no se incluye; se reevalúa post-MVP si hay demanda offline.

## Risks / Trade-offs

- [Riesgo] `BrowserRouter` exige fallback SPA en el servidor estático → **Mitigación:** documentar rewrite `/* → index.html` en el deploy (nota en router + README de frontend); dev/preview de Vite ya lo resuelven.
- [Riesgo] Agrear `post` al api-client puede tentar a reescribir C-03 → **Mitigación:** método `post` espeja `request()` (headers/refresh/retry idénticos), sin cambiar `tryRefresh`; tests C-03 existentes deben seguir verdes (safety net).
- [Riesgo] Rol×ruta hardcodeada diverge de futuros roles backend → **Mitigación:** `ROLE_ROUTES` + guards leen `roles` de `/me`; cambio de matriz = delta spec de esta capability + un solo archivo.
- [Trade-off] Placeholders sin datos vs. mocks ricos: se elige vacío explícito para no inventar contratos de dominio que C-05/C-12 romperían.
- [Trade-off] Sin E2E (Playwright) en este change: el flujo login/logout se prueba en el seam `fetch` + render; E2E cruzado queda para el cierre MVP si se justifica.

## Migration Plan

Sin migración (frontend puro, sin backend/BD). Rollback: revert del commit. Orden de encendido: merge tras CI verde (`tsc + build + vitest`); las rutas placeholder son inertes hasta que sus changes las reemplacen.

## Open Questions

Ninguna que cambie specs, enfoque o tasks. Reevaluación diferida y segura: TanStack Router si C-07 demuestra necesidad de search-params tipados (no cambia esta spec, solo la implementación del router).
