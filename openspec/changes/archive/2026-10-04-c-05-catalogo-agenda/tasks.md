# Tasks

## 1. Modelos de dominio + Migración 003

- [x] 1.1 Crear `backend/app/domain/agenda/models.py` con `Profesional`, `Sillon`, `Prestacion`, `ProfesionalPrestacion`, `Bloqueo` (AuditMixin, tenant_id FK, CHECKs `duracion_min>0`, `fin>inicio`) y verificar `pytest backend/tests/test_agenda_models.py -k "constraint or tablename"` pasa
- [x] 1.2 Crear migración `c05a1b2c3d4e5_c05_agenda_catalog.py` (5 tablas + RLS + FORCE RLS + índices `(tenant_id, nombre)`, `(tenant_id, profesional_id)`, `(tenant_id, sillon_id, inicio)`) y verificar `alembic upgrade head` + `alembic downgrade -1` + `upgrade` en DB efímera sin errores
- [x] 1.3 Añadir repositorios tipados `backend/app/domain/agenda/repositories.py` sobre `BaseRepository[T]` con soft-delete y filtro `tenant_id` forzado, y verificar test de repositorio CRUD + soft-delete pasa

## 2. Schemas y CRUD API

- [x] 2.1 Añadir schemas Pydantic v2 estrictos (`PrestacionCreate/Update`, `ProfesionalCreate/Update` con ≥1 prestación, `SillonCreate/Update`, `BloqueoCreate/Update` con ≥1 objetivo y `fin>inicio`, regla seña→monto) y verificar tests de validación 422 para `duracion<=0`, bloqueo sin objetivo y seña sin monto pasan
- [x] 2.2 Implementar routers `GET/POST/PATCH/DELETE /api/profesionales`, `/api/sillones`, `/api/prestaciones`, `/api/bloqueos` con paginación y 404 ante id ajeno, y verificar tests de ciclo CRUD por recurso pasan
- [x] 2.3 Documentar los 4 recursos en OpenAPI (descripciones + códigos 201/400/401/403/404/422 con ejemplos ficticios) y verificar `GET /api/openapi.json` incluye los 4 paths

## 3. Generador de huecos (RN-AG-04)

- [x] 3.1 Implementar `generate_slots()` puro (paso `duracion+buffer`, semántica `[inicio,fin)`, descuenta turnos + bloqueos) en capa application y verificar tests unitarios puros (día con turno 10:00–10:30 + bloqueo 12:00–13:00; grilla 45'+10 → 09:00/09:55/10:50) pasan sin DB
- [x] 3.2 Exponer consulta interna `GET /api/agenda/huecos?profesional_id&prestacion_id&desde&hasta` (solo staff, valida ventana y existencia en tenant) y verificar test de integración con seed mínimo devuelve solo huecos válidos

## 4. RBAC, aislamiento y reglas duras

- [x] 4.1 Cablear `require_role("propietario")` en escrituras y lectura staff en los 4 routers + derivar `tenant_id` del JWT (nunca de query/body), y verificar tests: recepción escribe → 403, lee → 200; acceso cruzado por id → 404
- [x] 4.2 Verificar RLS + FORCE RLS a nivel DB (policies en las 5 tablas, `SET LOCAL app.tenant_id` pinneado en sesión) con test de aislamiento que inserta en tenant A y lee desde tenant B → 0 filas
- [x] 4.3 Dejar contrato de inmutabilidad documentado + test de no-regresión: editar `duracion_min` no toca turnos existentes (contra stub de turno congelado que C-06 reemplazará por snapshot real) y verificar el test pasa

## 5. Seed idempotente con datos ficticios

- [x] 5.1 Implementar `seed_catalogo()` (5 prestaciones, "Box 1", profesional demo habilitado, feriados AR como bloqueos, upsert por claves naturales, todo ficticio) y verificar doble ejecución no duplica (conteos 5/1/1) y `pytest -k seed_catalogo` pasa
- [x] 5.2 Registrar política de feriados como ejemplo recargable en el docstring/README del seed y verificar la doc indica que no es fuente oficial y cómo recargarla

## 6. Integración y cierre

- [x] 6.1 Ejecutar suite completa `pytest backend/tests` + `alembic upgrade head` desde cero y verificar 0 fallos y los 4 recursos responden (smoke propietario 200/201, recepción escritura 403)
- [x] 6.2 Actualizar `CHANGES.md` (marcar C-05 en progreso) y verificar `openspec validate --change c-05-catalogo-agenda` no reporta errores de artefactos
