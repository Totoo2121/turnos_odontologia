# Proposal — c-03-auth-rbac

## Why

Todo endpoint protegido del SaaS (agenda, clínica, cobros, reportes — C-05 en adelante) necesita saber *quién* llama, *de qué tenant* y *qué puede hacer*. Hoy C-02 deja usuarios sin credencial verificable (`password_hash` NULL + marcador `!UNSET-C03*`) y sin ningún mecanismo de sesión: sin este change, ningún change posterior puede exponer un endpoint protegido.

## What Changes

- `POST /api/auth/login` — verifica email + password por tenant, emite access JWT corto + refresh rotado; rate-limit 5 intentos / 60 s por par IP+email.
- `POST /api/auth/refresh` — rota el refresh (emite par nuevo, revoca el anterior); reutilización de un refresh ya rotado se trata como robo y revoca la familia.
- `POST /api/auth/logout` — revoca el access vigente (blacklist por `jti` hasta su expiración).
- `GET /api/auth/me` — identidad del portador (sub, tenant, roles, email).
- Claims JWT: `sub`, `tenant_id`, `roles`, `email`, `jti`, `type` (`access|refresh|portal`), `iat`, `exp`.
- `PermissionContext` en backend: `require_role()` + guards por recurso según matriz de KB 03 (RN-SE-02 tratantes/propietario/derivación; RN-SE-03 recepción/asistente sin evoluciones clínicas).
- Portal paciente: token firmado de un solo turno, expirable, para `GET /p/{token}` (detalle de endpoints del portal en C-08; aquí solo emisión/validación del token + tabla `portal_token`).
- Turnero `GET /reservar/{slug}` y webhooks (MP, WhatsApp) se **declaran** públicos con rate-limit + captcha/firma — implementación en C-08/C-10/C-11, sin código en este change.
- Migración Alembic 002 (encadenada a 001): tablas `revoked_token`, `portal_token`; `usuario.password_hash` pasa a `NOT NULL` y el seed `!UNSET-C03*` rota a hash real.
- Tests de comportamiento en el seam HTTP + matriz RBAC 5 roles × recursos + aislamiento `tenant_id`.

## Capabilities

### New Capabilities

- `identity-auth`: autenticación JWT (login/refresh/logout/me, claims, rotación, blacklist, rate-limit), autorización RBAC por matriz rol×recurso (`PermissionContext`, RN-SE-02/03) y tokens firmados de portal paciente. Frontera durable: todo lo que responda "¿quién sos, de qué tenant, y podés?" vive aquí; C-04 (guards frontend), C-08 (portal/turnero) y C-12 (visibilidad HCE) la consumen sin redefinirla.

### Modified Capabilities

- Ninguna. `core-multitenant` no cambia requirements (el endurecimiento de `password_hash` a `NOT NULL` es detalle de implementación de una columna que el spec vigente no menciona; el aislamiento por tenant se consume, no se redefine). `platform-foundation` no cambia (el ajuste del api-client al mecanismo de refresh elegido se hace dentro del contrato 401→refresh→retry ya especificado).

## Impact

- Backend: nuevo módulo `app/api/auth.py` (+ `application/auth_service.py`, `infrastructure/security.py`, `api/deps.py`), middleware/dependencias de auth en `main.py`, migración 002, seed de credencial admin demo, nuevas dependencias (`pyjwt`, `argon2-cffi`, `slowapi` o equivalente).
- Frontend: ajuste acotado de `shared/api-client.ts` + `storage.ts` al mecanismo de refresh decidido (contrato 401→refresh→retry inalterado).
- Sistemas: ningún cambio en compose/CI; Redis ya disponible como opción de blacklist (decisión en design).
- Breaking: login con marcador `!UNSET-C03*` deja de existir (nunca autenticó nada); sin migración de sesiones porque no hay sesiones previas.
