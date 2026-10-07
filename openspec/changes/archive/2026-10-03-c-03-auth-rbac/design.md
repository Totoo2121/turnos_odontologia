# Design — c-03-auth-rbac

## Context

Ver `proposal.md` (Why) y `specs/identity-auth/spec.md` (contrato de comportamiento). Estado actual: C-02 dejó `usuario(password_hash NULL, marcador !UNSET-C03*)`, `Rol` global (4 filas), `BaseRepository[T]` + `UnitOfWork` con `SET LOCAL app.tenant_id` y RLS + FORCE RLS en tablas de tenant; C-01 dejó `api-client.ts` con refresh por JSON body y storage versionado `turnos.auth.v1` (`localStorage`), settings fail-fast con `JWT_SECRET`, y `AppError` + handlers JSON. Restricciones duras: sin secretos en código, sin DDL ad-hoc (migración 002), RLS en toda tabla de tenant, datos sintéticos ficticios, sin commit.

## Goals / Non-Goals

**Goals:**

- Cerrar el hueco de C-02: credencial verificable, sesiones JWT con rotación y RBAC exigible por rol×recurso, con aislamiento tenant que no dependa solo del `WHERE` de app.
- Resolver las 7 decisiones abiertas de este change de forma que apply no tenga que adivinar (cada una marcada para revisión humana abajo).
- Dejar seams consumibles por C-04 (guards frontend), C-08 (portal/turnero) y C-12 (visibilidad HCE) sin re-trabajo de auth.

**Non-Goals:**

- Sin UI de login (C-04), sin flujo de reserva del turnero (C-08), sin verificación de firma MP/BSP ni captcha (C-08/C-10/C-11), sin auditoría append-only de eventos (C-17), sin multi-sucursal (E2).
- Sin recuperación de password / registro público / OAuth: fuera del MVP declarado.

## Decisions

### D1. Hash argon2id (`argon2-cffi`), columna a NOT NULL, seed rotado — [CONFIRM]

**Decisión:** `argon2-cffi` con perfil OWASP (`time_cost=3, memory_cost=64MB, parallelism=4`), hash en formato PHC en `usuario.password_hash`; Migración 002 incluye `ALTER COLUMN SET NOT NULL` + migración de datos que reemplaza el marcador `!UNSET-C03*` del admin seed por hash real; el password inicial del seed sale de env `ADMIN_INITIAL_PASSWORD` (placeholder solo en `.env.example`, nunca en código).
**Alternativas:** bcrypt (descartada: trunca a 72 bytes, parámetros menos flexibles; ecosistemáticamente argon2id es el default OWASP actual) · scrypt (descartada: menor soporte de libs testeadas en el stack) · elegir en apply (descartada: el scheme condiciona formato almacenado y tests).
**Por qué:** memory-hard resiste GPU/ASIC; PHC auto-describe parámetros para futura re-calibración sin migración de formato.

### D2. Refresh en cookie HttpOnly; access en memoria/localStorage; api-client se ajusta aquí — [CONFIRM]

**Decisión:** la contradicción C-01 (ambos tokens en `localStorage`) vs CHANGES C-03 (refresh en HttpOnly) se resuelve a favor de la cookie: `POST /login` y `POST /refresh` emiten `Set-Cookie: refresh_token=…; HttpOnly; Secure; SameSite=Lax; Path=/api/auth`; el access sigue en `turnos.auth.v1` (contrato 401→refresh→retry de C-01 inalterado); `tryRefresh()` pasa a `POST` con `credentials: "include"` sin body, y `storage.ts` deja de persistir refresh. Login/logout limpian la cookie (`Max-Age=0`).
**Alternativas:** mantener refresh en localStorage (descartada: XSS roba sesión larga; el access corto ya limita esa ventana) · access también en cookie (descartada: rompe el api-client de C-01 y exige CSRF tokens en cada request; YAGNI).
**Supuesto que condiciona:** frontend y API son mismo-site en MVP (proxy Vite en dev, mismo dominio en prod); si se separan dominios, revisar a `SameSite=None; Secure` en change futuro. CSRF sobre `/refresh`: mitigado por `SameSite=Lax` (bloquea POST cross-site) + el endpoint solo rota sesión, no muta dominio; sin double-submit token en MVP.

### D3. Blacklist en DB (`revoked_token`) como fuente de verdad; sin Redis para corrección — [APPROVED-BY-DESIGN]

**Decisión:** `revoked_token(jti PK, type, expires_at, reason, created_at)` global (ver D6); cada request protegido hace un lookup por PK (`jti`) antes de autorizar; limpieza periódica de expirados vía worker existente (sin beat nuevo: purga oportunista en refresh + tarea Celery cuando C-11 programe beat).
**Alternativas:** denylist solo en Redis (descartada: introduce dependencia de corrección — si Redis se vacía, tokens revocados reviven; CHANGES.md además prescribe la tabla) · Redis como caché delante de DB (descartada por ahora: un `SELECT` por PK indexada cuesta <1 ms frente al resto del request; re-evaluar con métricas, no por intuición).
**Costo de revocación:** O(1) por request + purga acotada; aceptado frente a ventanas de expiración largas sin revocación.

### D4. `tenant_id` del token vincula `UnitOfWork`; spoof imposible sin `JWT_SECRET` — [APPROVED-BY-DESIGN]

**Decisión:** dependencia `get_current_principal`: verifica firma HS256 con `JWT_SECRET` → valida `type/exp/jti` (blacklist) → construye `Principal(sub, tenant_id, roles, email)` → abre `UnitOfWork(tenant_id del token)` que ejecuta el `SET LOCAL` heredado de C-02; `tenant_id` jamás se lee de body/query/path. Firma inválida o `tenant_id` adulterado ⇒ 401 antes de tocar DB.
**Alternativas:** tenant por subdomain/header (descartada: duplica fuente de verdad y permite desincronía token↔header).
**Coherencia:** reutiliza D1/D8 de C-02 sin modificarlos; RLS sigue fail-closed si el GUC falta.

### D5. Rate-limit login con `slowapi` in-process, clave IP+email — [CONFIRM]

**Decisión:** `slowapi` (nueva dependencia) como decorator en `POST /login`: `5/minute`, clave `client_ip + email_normalizado`, respuesta 429 con `Retry-After`; mismo límite base en `/refresh` y `/p/{token}` (valores por settings). Rate-limit de proxy/CDN en deploy es complementario, nunca la única capa (los tests lo verifican a nivel app).
**Alternativas:** middleware propio con Redis (descartada: Redis pasa a ser dependencia de corrección del login; YAGNI con una sola réplica en MVP) · solo rate-limit en proxy (descartada: no testeable en CI ni portable a dev).
**Riesgo asumido:** con múltiples réplicas el bucket es por instancia (5×N teórico); aceptado en MVP, documentado para endurecer con backend compartido si se escala horizontalmente.

### D6. RLS: `portal_token` tenant-scopeada; `revoked_token` global sin RLS (excepción explícita) — [CONFIRM]

**Decisión:** `portal_token(id, tenant_id FK, turno_id, jti UNIQUE, expires_at, revoked_at NULL, …)` CON `tenant_id` + RLS + FORCE RLS (patrón C-02: el flujo verifica firma ⇒ extrae tenant ⇒ `SET LOCAL` ⇒ fetch scopeado). `revoked_token` SIN `tenant_id` y sin RLS —segunda excepción explícita a la regla dura tras `rol`— porque el check ocurre sobre `jti` no adivinable antes de conocer el tenant (chicken-egg: exigir tenant previo rompería logout/rotación con token expirado) y la fila no contiene PII (solo `jti`, tipo, expiración, motivo).
**Alternativas:** `revoked_token` con `tenant_id` nullable + RLS (descartada: el lookup pre-auth no tiene GUC y fallaría closed siempre) · todo en una sola tabla (descartada: mezcla ciclos de vida y políticas distintas).

### D7. Portal = JWT firmado (`type=portal`) + fila revocable en `portal_token` — [CONFIRM]

**Decisión:** híbrido: JWT HS256 con `JWT_SECRET` separado de entorno (`PORTAL_SECRET`, distinto de `JWT_SECRET` para que una fuga no cruce dominios), claims `turno_id + tenant_id + jti + exp`; fila espejo en `portal_token` para revocación (cancelación/reprogramación del turno la invalida) y single-turno enforcement. Expiración: `min(turno.inicio + 24 h, 90 días)` calculada al emitir; re-emisión en cada reprogramación.
**Alternativas:** JWT stateless puro (descartada: imposible revocar al cancelar el turno) · opaco aleatorio solo-DB (descartado: cada `GET /p/{token}` pagaría join + el token firmado ya resuelve integridad sin DB).
**No-código en este change:** los endpoints `GET/POST /p/{token}` de gestión del portal se implementan en C-08; aquí emisión + validación + tabla.

### D8. Lifetimes y secretos nuevos — [CONFIRM]

**Decisión:** `ACCESS_MINUTES=15`, `REFRESH_DAYS=7` (rotado en cada uso, familia invalidada ante reuso — ver spec), portal según D7; settings nuevos `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`, `PORTAL_SECRET`, `ADMIN_INITIAL_PASSWORD` (fail-fast solo `JWT_SECRET` + `DATABASE_URL` como hoy; `PORTAL_SECRET` cae a `JWT_SECRET` con warning deprecable si falta — evita romper dev, sin default hardcodeado).
**Alternativas:** access 60 min (descartada: amplía ventana de robo del único token en JS) · refresh sin rotación (descartada: contradice CHANGES y el threat model).

### D9. Rutas públicas: allowlist declarativa ahora, guards reales en sus changes — [APPROVED-BY-DESIGN]

**Decisión:** confirma CHANGES (declarar, no implementar): este change agrega `PUBLIC_PATHS = {GET /api/health, GET /reservar/{slug}, GET /p/{token}, POST /webhooks/*}` como constante consumida por la dependencia de auth (skip de JWT) + rate-limit base en esos paths; captcha, firma MP/BSP y lógica de negocio llegan en C-08/C-10/C-11.
**Alternativas:** guards mínimos ahora (descartada: duplica ownership con sus changes y adelanta decisiones de captcha/firma fuera de su threat model).

### D10. Forma del `PermissionContext` — [APPROVED-BY-DESIGN]

**Decisión:** `PermissionContext` como dependencias FastAPI componibles (`require_role("recepcion")`, `require_any(...)`, `require_owner_or_treating(...)`) construidas sobre `get_current_principal`; la parte "tratante o derivación" de RN-SE-02 se resuelve contra `paciente.profesional_tratante / derivaciones` (tablas de C-12: hasta entonces el guard deniega salvo propietario — fail-closed documentado, se abre en C-12 sin cambiar firma). Errores uniformes vía `AppError` (401 sin identidad, 403 sin permiso, 404 cross-tenant).
**Alternativas:** middleware RBAC global con tabla de rutas (descartada: acopla matriz a paths y oscurece qué endpoint exige qué; dependencias explícitas son auditables por endpoint).

## Risks / Trade-offs

- [Riesgo] `PORTAL_SECRET` con fallback a `JWT_SECRET` debilita la separación de dominios si nadie lo configura → Mitigación: warning en arranque + task de CI que falla si `PORTAL_SECRET` falta en prod (env `APP_ENV=prod`).
- [Riesgo] `ADMIN_INITIAL_PASSWORD` placeholder en `.env.example` copiado a prod → Mitigación: seed rehúsa passwords de la lista denegada (`changeme*`, `admin`, `password*`); documentado en tasks.
- [Riesgo] Denegación fail-closed de RN-SE-02 hasta C-12 (odontólogo no-propietario sin derivaciones visibles) → Mitigación: es el comportamiento seguro por defecto; C-12 lo abre con tests de visibilidad.
- [Riesgo] argon2id sube ~100 ms CPU por login → Mitigación: dentro del presupuesto del rate-limit 5/60 s; evita timing-oracle con comparación constante y error genérico.
- [Trade-off] Un lookup `revoked_token` por request suma una query → aceptado (<1 ms por PK, fail-closed ante DB caída igual que el resto del request).
- [Trade-off] Cookie `SameSite=Lax` exige mismo-site frontend↔API → aceptado en MVP (proxy dev + mismo dominio prod); cambio futuro versionado si se separan.

## Migration Plan

1. `alembic revision` manual 002 (`down_revision` = 001 de C-02): crea `revoked_token` (global, sin RLS) + `portal_token` (tenant + RLS/FORCE RLS + políticas espejo de C-02) + `ALTER usuario.password_hash SET NOT NULL` con migración de datos del marcador → hash del seed.
2. Verificación: `upgrade head` en DB vacía y sobre 001 con datos; `downgrade -1` + `upgrade` (reversibilidad); seed re-ejecutable sin duplicar y con login funcional del admin demo.
3. Rollback: `downgrade -1` elimina 002 y restaura NULLable (el marcador no se restaura: re-seed si hace falta); sin rollback de datos de sesión porque no existían sesiones previas.
4. Validación: suite `test_c03_*` verde + `test_c02_*` sin regresión, `mypy`, `ruff/black`, `tsc --noEmit` + build frontend.

## Open Questions

Ninguna que cambie specs, enfoque o tasks. Seguimiento no bloqueante: backend compartido de rate-limit al escalar horizontalmente (ver D5); data-fetching definitivo del frontend lo decide C-04 sobre el api-client ajustado aquí.
