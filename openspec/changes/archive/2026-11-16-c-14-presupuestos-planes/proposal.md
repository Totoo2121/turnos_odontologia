# Proposal

## Why

C-13 dejó el odontograma y los consentimientos firmados listos, pero el odontólogo todavía no puede cerrar el circuito comercial del tratamiento: no existe presupuesto sobre las piezas diagnosticadas, la aceptación no genera plan por etapas ni deuda exigible, y no hay cuenta corriente donde C-16 pueda cobrar. Sin C-14, US-032 queda incompleta y la rama clínica no converge con caja ni reportes.

## What Changes

- Nueva capacidad `presupuestos-planes`: presupuestos en ARS sobre piezas del odontograma, aceptación que genera plan por etapas y deuda en cuenta corriente.
- `Presupuesto` por paciente e historia clínica con `estado (borrador|enviado|aceptado|rechazado)`, `validez_hasta`, total y moneda fija `ARS` (RN-AD-01).
- `PresupuestoItem` con prestación, pieza FDI opcional, superficie opcional, descripción y precio unitario **snapshot** al crear la línea (editable solo en borrador); `etapa` declarada por ítem agrupa el plan de tratamiento.
- Endpoints CRUD `/presupuestos` (con ítems anidados), `POST /presupuestos/{id}/enviar|aceptar|rechazar`, `GET /planes-tratamiento` y `GET /pacientes/{id}/cuenta-corriente`.
- Aceptar exige estado `enviado`, presupuesto vigente y al menos un ítem; genera **de forma idempotente** un `PlanTratamiento` (etapas, total, consentimiento) y un movimiento débito por el total exacto en la cuenta corriente del paciente (RN-AD-02).
- Plan con al menos un ítem que requiere consentimiento exige un consentimiento invasivo firmado de C-13; sin firma responde 409 y no genera plan ni deuda (RN-HC-04).
- Cuenta corriente **solo deuda con saldo de lectura**: C-14 escribe únicamente débitos y expone el saldo derivado; registrar pagos/créditos y el cobro en mostrador queda para C-16.
- `MovimientoCC` append-only (sin edición ni borrado) para preservar la trazabilidad financiera.
- `prestacion.requiere_consentimiento` (default `false`) para que el catálogo declare qué prestaciones son invasivas; el ítem lo copia como snapshot.
- Migración 010: `presupuesto`, `presupuesto_item`, `plan_tratamiento`, `cuenta_corriente`, `movimiento_cc`, columna `requiere_consentimiento` en `prestacion`, RLS + FORCE RLS y triggers de inmutabilidad.

## Capabilities

### New Capabilities
- `presupuestos-planes`: presupuesto clínico en ARS con ítems por prestación/pieza, transiciones de estado, aceptación idempotente que genera plan por etapas y deuda exacta en cuenta corriente, y gate de consentimiento para planes invasivos.

### Modified Capabilities
- `agenda-catalog`: la prestación declara si requiere consentimiento informado, para que los presupuestos puedan marcar ítems invasivos sin inferirlos por nombre.

## Impact

- Backend: dominio `clinica` suma `Presupuesto`, `PresupuestoItem`, `PlanTratamiento`, `CuentaCorriente` y `MovimientoCC`; servicios de aplicación con stores `Protocol` + implementaciones memoria/SQLAlchemy; router `/api` para presupuestos, planes y cuenta corriente, reutilizando `AccesoClinicoService` (C-12) y `ConsentimientoService` (C-13).
- Catálogo: `Prestacion` gana `requiere_consentimiento` en modelo, schemas y store (aditivo, default `false`).
- DB: migración 010 (`d14a1b2c3d4e5`, down_revision `c13a1b2c3d4e5`) con 5 tablas nuevas, 1 columna nueva, índices, checks de estado/moneda/montos/etapas, unicidades de idempotencia, RLS/FORCE RLS y triggers append-only/guarda de ítems.
- API: alta y edición de presupuestos en borrador, transiciones, lectura de plan y saldo con movimientos.
- Tests: total/importes en ARS con redondeo exacto, snapshot de precios, transiciones inválidas, aceptación idempotente (un plan y un débito), plan por etapas, gate invasivo, saldo de solo lectura, 404 cross-tenant y 403 por rol.
- Depende de C-13. No incluye pagos, créditos, recibos, cierre de caja ni reportes (C-16), ni UI (C-15).
