# Tasks

## 1. Catálogo, modelos y migración

- [x] 1.1 Agregar `requiere_consentimiento` (bool, default `false`) a `Prestacion` en `backend/app/domain/agenda/models.py`, a `PrestacionCreate/Update/Read` en `backend/app/api/catalog_schemas.py` y al store de catálogo; verificar con tests de alta sin flag (`false`), alta/edición con `true` y lectura del valor.
- [x] 1.2 Crear `Presupuesto`, `PresupuestoItem`, `PlanTratamiento`, `CuentaCorriente` y `MovimientoCC` en `backend/app/domain/clinica/models.py` y registrarlos en `app/domain/__init__.py`; verificar con un test que las tablas, columnas, checks y unicidades existen y que `app.shared.db.metadata` las expone.
- [x] 1.3 Crear la migración `d14a1b2c3d4e5` (down_revision `c13a1b2c3d4e5`) con la columna `prestacion.requiere_consentimiento`, las 5 tablas, índices, checks (estado/moneda/montos/etapa/FDI/superficie), `uq_plan_tenant_presupuesto`, `uq_cc_tenant_paciente`, `uq_movimiento_cc_tenant_referencia`, RLS/FORCE RLS y policies; verificar con `alembic upgrade head --sql` y un test de migración que inspecciona tablas, columnas, checks, unicidades y policies.
- [x] 1.4 Agregar `movimiento_cc_append_only()` y `presupuesto_item_guard()` con sus triggers `BEFORE UPDATE OR DELETE`, más el rollback en `downgrade`; verificar con un test que el SQL de la migración contiene ambas funciones y triggers, y que el downgrade los elimina junto con tablas y columna.
- [x] 1.5 Agregar `PRESUPUESTO_VALIDEZ_DIAS` (default 30, positivo) a `backend/app/shared/settings.py`; verificar con tests de settings que el default es 30 y que un valor inválido falla al construir la configuración.

## 2. Presupuestos e ítems

- [x] 2.1 Implementar `PresupuestoStore` y `PresupuestoItemStore` (`Protocol`) con dobles in-memory y stores SQLAlchemy en `backend/app/application/presupuestos.py`, filtrando siempre por tenant; verificar con tests de alta/lectura/listado, aislamiento por tenant y borrado en cascada de ítems.
- [x] 2.2 Exponer en `application/clinica.py` los helpers `validar_fdi`, `validar_superficie` y `SUPERFICIES` reutilizando las reglas de C-13, y usarlos en la validación de ítems; verificar con tests de FDI/superficie válida e inválida y de superficie sin pieza (422).
- [x] 2.3 Implementar el alta de ítem con precio snapshot: precio explícito, heredado de `prestacion.precio`, error 422 si no hay precio, descripción desde `prestacion.nombre` y `requiere_consentimiento` copiado del catálogo; verificar con tests de los tres caminos y de que un cambio posterior del catálogo no altera el ítem.
- [x] 2.4 Implementar el cálculo de dinero con `Decimal`/`ROUND_HALF_UP`: `importe = cantidad × precio_unitario`, `total = Σ importes` y moneda fija `ARS`; verificar con tests de total exacto, cantidad/precio inválidos (422), moneda distinta (422) y recálculo al agregar/editar/quitar ítems.
- [x] 2.5 Implementar la máquina de estados `borrador→enviado→aceptado|rechazado` con timestamps, edición y borrado solo en `borrador`; verificar con tests de envío, aceptación, rechazo, transición inválida (409), edición tras envío (409) y borrado de aceptado (409).
- [x] 2.6 Implementar `validez_hasta` con default `hoy + PRESUPUESTO_VALIDEZ_DIAS` y el rechazo de aceptación vencida; verificar con tests de fecha por defecto, aceptación dentro de vigencia y aceptación vencida (409 sin plan ni deuda).
- [x] 2.7 Implementar la autoría desde `principal.sub` y el rechazo de `sub` no UUID; verificar con tests de autor tomado del token, autor del body ignorado y token inválido (422).

## 3. Cuenta corriente

- [x] 3.1 Implementar `CuentaCorrienteStore` y `MovimientoCCStore` (`Protocol`) con dobles in-memory y stores SQLAlchemy en `backend/app/application/cuenta_corriente.py`, con unicidad por paciente y por referencia; verificar con tests de `obtener_o_crear` idempotente, aislamiento por tenant y conflicto de referencia.
- [x] 3.2 Implementar `CuentaCorrienteService.registrar_debito` y la lectura de saldo derivado (`Σ débitos − Σ créditos`), sin endpoint de pagos en este alcance; verificar con tests de saldo 0 sin movimientos, saldo tras un débito, débito duplicado por referencia que no suma dos veces y saldo de otro paciente intacto.
- [x] 3.3 Implementar el contrato inmutable de movimientos (sin update/delete en stores ni API) y su mapeo a los triggers de la migración; verificar con tests de que el store in-memory rechaza mutaciones y de que no existe ruta de escritura de créditos.
- [x] 3.4 Aplicar la autorización de lectura de cuenta con `authorize(roles, "cobros", "R")` y alcance por tenant; verificar con tests de propietario/odontólogo/recepción (200), asistente (403) y paciente de otro tenant (404).

## 4. Aceptación y plan de tratamiento

- [x] 4.1 Implementar `PlanTratamientoStore` (`Protocol`) con doble in-memory y store SQLAlchemy, incluida la unicidad `(tenant_id, presupuesto_id)`; verificar con tests de alta, relectura por presupuesto y conflicto de duplicado.
- [x] 4.2 Implementar `PresupuestoService.aceptar` en una sola transacción: validar `enviado`, vigencia, ≥1 ítem, total recalculado y `etapas=max(etapa)` con `etapa_actual=1`; verificar con tests de plan con etapas 1/2/2, presupuesto sin ítems (422), presupuesto vencido (409) y total del plan igual al del presupuesto.
- [x] 4.3 Hacer la aceptación idempotente: reutilizar plan existente, crear cuenta si falta y registrar un único débito con `referencia="presupuesto:{id}"`; verificar con tests de doble aceptación (un plan, un débito, mismo `plan_id`) y de reintento concurrente simulado que resuelve por unicidad.
- [x] 4.4 Implementar el gate invasivo: si algún ítem tiene `requiere_consentimiento`, verificar `ConsentimientoService.tiene_consentimiento_invasivo`, resolver el consentimiento más reciente y guardar `plan.consentimiento_id`; verificar con tests de plan invasivo con firma (genera plan/deuda), sin firma (409, presupuesto sigue `enviado`, sin plan ni débito) y plan no invasivo (no exige firma).
- [x] 4.5 Implementar la lectura de plan con ítems agrupados por etapa y cabecera `etapas`/`etapa_actual`; verificar con tests de agrupación, orden por etapa y 404 cross-tenant.

## 5. API

- [x] 5.1 Crear los schemas Pydantic de presupuesto, ítem, plan y cuenta corriente con `Decimal`, `extra="forbid"` y validaciones de entrada; verificar con tests de payload válido, campo extra (422) y moneda distinta de `ARS` (422).
- [x] 5.2 Exponer `POST/GET /presupuestos`, `GET/PATCH/DELETE /presupuestos/{id}` y `POST/PATCH/DELETE /presupuestos/{id}/items[/{item_id}]` en `backend/app/api/presupuestos.py` con `CLINICAL_GUARD`, `may_modify_evolution` y `AccesoClinicoService`; verificar con tests de 201/200, 403 para recepción y profesional ajeno, y 404 cross-tenant.
- [x] 5.3 Exponer `POST /presupuestos/{id}/enviar|aceptar|rechazar` y `GET /planes-tratamiento[/{id}]`; verificar con tests de transiciones (200), transición inválida (409), aceptación idempotente y respuesta con `plan_id`/`movimiento_id`.
- [x] 5.4 Exponer `GET /pacientes/{paciente_id}/cuenta-corriente` con saldo y movimientos; verificar con tests de recepción (200), asistente (403), paciente de otro tenant (404) y contrato de respuesta (`moneda`, `saldo`, `movimientos`).
- [x] 5.5 Registrar el router en `backend/app/main.py` y verificar con un test de OpenAPI que todas las rutas nuevas existen y que las de presupuesto exigen autenticación.

## 6. Integración y cierre

- [x] 6.1 Escribir un test E2E del Flujo 3 sin Postgres ni red: HCE → odontograma → presupuesto → plan invasivo sin consentimiento (409) → consentimiento firmado → aceptar → plan por etapas → débito → saldo; verificar que recepción y profesional ajeno quedan fuera y que la deuda es exacta.
- [x] 6.2 Documentar en `README.md` las rutas nuevas, `PRESUPUESTO_VALIDEZ_DIAS` y el alcance de solo débito, y agregar la variable a `.env.example`; verificar que los comandos y rutas documentados coinciden con OpenAPI.
- [x] 6.3 Correr la suite completa (`python -m pytest -q`), `ruff check` y `alembic heads`; verificar que el head es `d14a1b2c3d4e5`, que no hay regresiones sobre la línea base de C-13 y actualizar `CHANGES.md` al cerrar.

## Workflow follow-up

- Sincronizar las specs principales y archivar el change cuando la implementación y la revisión estén completas.
