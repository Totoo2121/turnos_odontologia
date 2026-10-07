# Tasks — c-03-auth-rbac

## 1. Safety net y dependencias

- [x] 1.1 Ejecutar suite C-02 (`pytest backend/tests/test_c02_*`) y registrar baseline verde antes de tocar código
- [x] 1.2 Agregar `pyjwt`, `argon2-cffi`, `slowapi` a `backend/requirements.txt` y verificar `pip install` + import en CI local

## 2. Seguridad base: hashing + JWT + settings

- [x] 2.1 Implementar `infrastructure/security.py` (hash/verify argon2id D1, emisión/verificación HS256 access/refresh/portal) con tests unitarios de round-trip, firma adulterada rechazada y marcador `!UNSET-C03*` jamás válido, y verificar `pytest backend/tests/test_c03_security.py` verde
- [x] 2.2 Extender `shared/settings.py` (`JWT_ACCESS_MINUTES=15`, `JWT_REFRESH_DAYS=7`, `PORTAL_SECRET`, `ADMIN_INITIAL_PASSWORD`, deny-list de placeholders D1/D8) con tests de fail-fast y fallback con warning, y verificar `pytest backend/tests/test_c03_settings.py` verde

## 3. Migración 002 + modelos

- [x] 3.1 Escribir modelos `RevokedToken` (global, sin RLS) y `PortalToken` (tenant + RLS) y verificar import sin ciclos con `python -c "import app.domain.models"`
- [x] 3.2 Escribir Migración 002 a mano (tablas + RLS/FORCE RLS de `portal_token` + `password_hash SET NOT NULL` con migración del marcador) encadenada a 001 y verificar `alembic upgrade head` + `downgrade -1` + `upgrade` en Postgres real
- [x] 3.3 Rotar seed C-02 a hash real vía `ADMIN_INITIAL_PASSWORD` (idempotente, datos ficticios) y verificar doble ejecución sin duplicar + login del admin demo exitoso

## 4. Auth HTTP: login / refresh / logout / me

- [x] 4.1 Implementar `application/auth_service.py` + `POST /api/auth/login` (cookie HttpOnly D2, rate-limit 5/60s IP+email D5, error 401 genérico) con tests de login ok/inexistente/rate-limit, y verificar `pytest backend/tests/test_c03_login.py` verde
- [x] 4.2 Implementar `POST /api/auth/refresh` (rotación + detección de reuso con revocación de familia) y `POST /api/auth/logout` (blacklist por `jti`) con tests de rotación, reuso revocado y logout invalida, y verificar `pytest backend/tests/test_c03_session.py` verde
- [x] 4.3 Implementar `GET /api/auth/me` + `PUBLIC_PATHS` allowlist (health sin JWT, declaración turnero/portal/webhooks D9) con tests de identidad y rutas públicas, y verificar `pytest backend/tests/test_c03_me_public.py` verde

## 5. RBAC: PermissionContext + matriz + tenant binding

- [x] 5.1 Implementar `api/deps.py` (`get_current_principal` con binding token→`UnitOfWork`/`SET LOCAL` D4, `require_role/require_any/require_owner_or_treating` D10, errores 401/403/404 uniformes) con tests de firma adulterada, `tenant_id` spoofeado y cross-tenant 404, y verificar `pytest backend/tests/test_c03_tenant_binding.py` verde
- [x] 5.2 Implementar matriz rol×recurso KB 03 (RN-SE-02 fail-closed hasta C-12, RN-SE-03 403 en evoluciones, 5 roles incl. paciente-portal) con tests de comportamiento por rol×recurso, y verificar `pytest backend/tests/test_c03_rbac.py` verde

## 6. Portal token emisión/validación

- [x] 6.1 Implementar emisión/validación de portal JWT (`type=portal`, `PORTAL_SECRET`, expiración D7, revocación en `portal_token`) con tests de token válido/expirado/revocado/ajeno, y verificar `pytest backend/tests/test_c03_portal.py` verde

## 7. Frontend: api-client a cookie de refresh

- [x] 7.1 Ajustar `api-client.ts` (`tryRefresh` con `credentials:include` sin body) + `storage.ts` (ya no persiste refresh, migra `turnos.auth.v1`) con tests de 401→refresh→retry único y refresh rechazado limpia sesión, y verificar `npm test` + `tsc --noEmit` + build verdes

## 8. Integración y gates finales

- [x] 8.1 Verificar suite completa sin regresión (`pytest backend/tests/` incl. C-01/C-02), `mypy`, `ruff/black`, y `openspec validate c-03-auth-rbac` (forma `validate <name>`, sin `--change`) verde
