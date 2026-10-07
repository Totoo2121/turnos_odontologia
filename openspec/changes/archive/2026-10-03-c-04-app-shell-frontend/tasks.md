# Tasks — c-04-app-shell-frontend

> TDD estricto (skill `tdd`): cada tarea de comportamiento sigue Red→Green→Triangulate→Refactor.
> Seams acordados: `fetch` (boundary fetch) para sesión, render de rutas para guards/shell.
> Mocks SOLO en el boundary `fetch`; literales independientes en asserts (nunca recomputar como el código).
> Datos ficticios marcados en tests/placeholders. Sin commits (regla dura).

## 1. Red de seguridad + dependencia router

- [x] 1.1 Registrar baseline: ejecutar `vitest run` y `tsc --noEmit` en `frontend/`, anotar N tests verdes; si algo falla, STOP y reportar como fallo preexistente (no arreglar de contrabando)
- [x] 1.2 Agregar `react-router-dom` (v6+) a `frontend/package.json`, instalar y verificar `tsc --noEmit` + `vite build` verdes con el código actual intacto

## 2. Sesión web (store + api-client post + login)

- [x] 2.1 Extender `features/auth/auth-store.ts` (RED: test `login` válido guarda access + hidrata `user/roles` vía `/me` con `fetch` mockeado; segundo caso: 401 muestra error y no guarda sesión; GREEN mínimo; TRIANGULAR con email mayúsculas/error genérico) y verificar `vitest run features/auth` verde
- [x] 2.2 Agregar `post()` mínimo a `shared/api-client.ts` espejando `request()` (mismo 401→refresh→retry único, `credentials:'include'` solo en refresh) con RED (test 401→refresh→retry en POST) + TRIANGULATE (refresh rechazado limpia store, sin reintento extra) y verificar que los 4 tests C-03 existentes siguen verdes
- [x] 2.3 Implementar `logout()` best-effort (`POST /api/auth/logout` + limpieza siempre) e `hydrate()` inicial (`/me` válido → authenticated, 401 → unauthenticated limpio), con tests en el seam `fetch`, y verificar `vitest run` verde
- [x] 2.4 Crear `features/auth/LoginPage.tsx` + `app/AuthLayout.tsx` (form email/password, error genérico,redirige a `from` o ruta por defecto del rol) con test de render (login ok redirige; 401 muestra error y permanece) y verificar suite verde

## 3. Guards + shell + rutas + placeholders

- [x] 3.1 Crear `app/guards.tsx` (`ROLE_ROUTES` única fuente + `RequireAuth` + `RequireRole`) con tests de comportamiento rol×ruta (casos: anónimo→`/login` con `from`; `asistente`→`/admin` ve 403; matriz completa del spec §guards; cambio de roles reevalúa sin recarga) y verificar `vitest run app/guards` verde
- [x] 3.2 Crear `app/AppShell.tsx` (header usuario+logout, nav filtrada por `ROLE_ROUTES`, outlet) + páginas `Forbidden`/`NotFound`, con tests (recepción no ve admin en nav; logout desde header termina en `/login`; ruta desconocida con sesión renderiza NotFound dentro del shell) y verificar suite verde
- [x] 3.3 Crear `app/router.tsx` (`BrowserRouter`, lazy por ruta + `Suspense`, `/login` pública, 6 rutas privadas con sus guards, `/403`, `*`) + placeholders con contrato en cabecera (`Agenda`, `Pacientes`, `PacienteDetalle` muestra `:id`, `Caja`, `Reportes`, `Admin`) y verificar render por rol (recepción ve agenda; anónimo ve login) en `vitest run`
- [x] 3.4 Reemplazar `App.tsx`/`main.tsx` (providers + router, nota de rewrite SPA `/* → index.html` documentada) y verificar `tsc --noEmit` + navegación manual `dev` (login→agenda→logout→login) sin errores de consola

## 4. Librería shared/ui mínima

- [x] 4.1 Crear `shared/ui/Table.tsx` + `Modal.tsx` (props controladas, ternario no `&&`, Escape cierra modal) con tests de render controlado (open/cerrado; filas/emptyText) y verificar `vitest run shared/ui` verde
- [x] 4.2 Crear `shared/ui/Form.tsx` (Field+error por prop) + `Toast.tsx` (un mensaje + onDismiss) con tests (error visible con texto exacto; dismiss llama callback una vez) y verificar suite verde, sin nuevas dependencias de runtime en `package.json`

## 5. Integración y cierre

- [x] 5.1 Verificación integral: `vitest run` completo verde, `tsc --noEmit` + `vite build` verdes, viewport ≤480px colapsa nav sin scroll horizontal (check manual documentado), y escaneo de secretos/storage (solo access en `turnos.auth.v1`, sin refresh/MP/WA/JWT en bundle ni tests) limpio
