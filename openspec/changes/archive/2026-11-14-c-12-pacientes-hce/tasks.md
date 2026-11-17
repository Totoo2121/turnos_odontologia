# Tasks

## 1. Modelo y migración

- [x] 1.1 Crear `Paciente`, `HistoriaClinica`, `Evolucion` y `DerivacionHCE` en `backend/app/domain/pacientes/models.py` (tenant, DNI opcional, consentimiento fechado, anamnesis, autoría y self-FK `corrige_evolucion_id`) y registrarlos en `backend/app/domain/__init__.py`; verificar con un test nuevo que las tablas, columnas, checks y unicidades existen y que `app.shared.db.metadata` las expone.
- [x] 1.2 Crear la migración `c12a1b2c3d4e5` (down_revision `c11a1b2c3d4e5`) con las 4 tablas, índices, `uq_historia_clinica_tenant_paciente`, índice único parcial de DNI activo, checks de consentimiento y RLS/FORCE RLS; verificar con `alembic upgrade head --sql` y un test de migración que inspecciona tablas, columnas, índices y policies.
- [x] 1.3 Agregar `evolucion_append_only()` y triggers `BEFORE UPDATE OR DELETE` sobre `evolucion`, y su rollback en `downgrade`; verificar con un test que el SQL de la migración contiene la función, ambos triggers y que el downgrade los elimina.

## 2. Pacientes

- [x] 2.1 Implementar `PacienteStore` (`Protocol`) + `MemoryPacienteStore` y `DbPacienteStore` en `backend/app/application/pacientes.py`, con búsqueda por id/DNI scoped por tenant; verificar con tests de aislamiento y de persistencia in-memory.
- [x] 2.2 Implementar `PacienteService` (alta/edición con DNI único, consentimiento fechado, borrado lógico solo sin turnos ni evoluciones) y sus errores 404/409; verificar con tests de DNI duplicado, consentimiento sin fecha y borrado con/sin historial.
- [x] 2.3 Exponer el CRUD `/api/pacientes` en `backend/app/api/pacientes.py` con guardas de rol (staff lee/escribe; borrado solo propietario) y registrar el router en `backend/app/main.py`; verificar con tests HTTP de matriz de roles, paginación y 404 cross-tenant.

## 3. Historia clínica y anamnesis

- [x] 3.1 Implementar `HistoriaStore` + `HistoriaClinicaService` con `obtener_o_crear(paciente_id)` idempotente y anamnesis editable (alergias, medicación, antecedentes), scoped por tenant; verificar con tests de primera apertura, segunda apertura sin duplicar y actualización de anamnesis.
- [x] 3.2 Exponer `GET/POST /api/historias-clinicas`, `GET /api/historias-clinicas/{id}` y `PATCH` de anamnesis, con acceso clínico (propietario/tratante/derivación) y 403 para recepción/asistente; verificar con tests HTTP de acceso permitido/denegado y de no duplicación.

## 4. Evoluciones append-only

- [x] 4.1 Implementar `EvolucionStore` + `EvolucionService.registrar(...)` que toma autor de `principal.sub` (nunca del body) y completa `autor_profesional_id` cuando existe, sin endpoints de update/delete; verificar con tests de alta con autor/fecha y de ausencia de rutas destructivas.
- [x] 4.2 Implementar correcciones por nueva evolución con `corrige_evolucion_id`, rechazando referencias de otra historia o tenant; verificar con tests de corrección trazable y de referencia inválida (404/409).
- [x] 4.3 Exponer `GET/POST /api/historias-clinicas/{id}/evoluciones` con acceso clínico y verificar el append-only a nivel DB con un test que ejecuta `UPDATE`/`DELETE` directos contra Postgres cuando hay DB viva y SKIP honesto cuando no la hay.
- [x] 4.4 Escribir la documentación de la API clínica (rutas, reglas de visibilidad RN-SE-02/03 y corrección append-only) en `README.md`; verificar que los nombres de rutas y roles documentados coinciden con los tests.

## 5. Acceso clínico y derivaciones

- [x] 5.1 Implementar `AccesoClinicoStore` (`Protocol`) + variantes memory/DB y `AccesoClinicoService.puede_acceder` (propietario, tratante por turnos, derivación); verificar con tests de tratante, profesional ajeno, propietario y derivación de otro paciente.
- [x] 5.2 Implementar `POST /api/historias-clinicas/{id}/derivaciones` (solo propietario/tratante) y su efecto en la visibilidad; verificar con tests de derivación registrada, derivación por rol no clínico (403) y acceso posterior del profesional derivado.

## 6. Integración

- [x] 6.1 Escribir el E2E del Flujo 3: paciente → historia → evolución → derivación → acceso del derivado, corriendo contra stores in-memory y el router real; verificar que no requiere Postgres ni red.
- [x] 6.2 Ejecutar la suite completa (`python -m pytest -q`) y ruff sobre los archivos nuevos; verificar cero regresiones y cero violaciones nuevas.

## Workflow follow-up

- Ejecutar `openspec validate c-12-pacientes-hce --strict` y corregir warnings antes de archivar.
- Archivar el change con `/opsx:archive c-12-pacientes-hce` y marcar `C-12` como `[x]` en `CHANGES.md`.
