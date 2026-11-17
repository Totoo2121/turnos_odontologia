# Proposal

## Why

C-14 dejó el backend de presupuestos, planes y cuenta corriente, pero no existe
todavía la pantalla donde odontología arma un presupuesto sobre el odontograma ni
donde recepción ve la deuda y cobra. Además, el cobro de saldo y el cierre de caja
no existen en backend, y los endpoints de ciclo de vida de turnos que C-06 declaró
entregados nunca se montaron en la app: hoy OpenAPI solo expone
`GET /api/turnos/agenda`. Sin C-15 los Flujos 3 y 4 no se pueden operar ni
demostrar, aunque el dominio clínico y financiero ya esté persistido.

## What Changes

**Backend mínimo (sin migración nueva)**

- Cuenta corriente: registrar **pagos/créditos** idempotentes con medio
  (`efectivo|transferencia|mp`), generar **recibo PDF** y exponer un **cierre de
  caja diario** agregado por medio. El medio y la clave de idempotencia viajan en
  `movimiento_cc.referencia` (`pago:{medio}:{clave}`), porque el alcance no agrega
  columnas; los movimientos siguen siendo append-only.
- Turnos: montar `POST /api/turnos`, `PATCH /api/turnos/{id}/estado` y
  `POST /api/turnos/{id}/cancelar` con `fin` calculado en servidor, validación de
  bloqueo, anti-solapamiento (constraints GIST existentes), rol y tenant.
- Se corrige el api-client de agenda para enviar `Authorization` (hoy el cambio de
  estado se hace con `fetch` suelto) y se reutiliza para las nuevas rutas.

**Frontend**

- `features/clinica`: listado y búsqueda de pacientes, y ficha de paciente con bloque
  administrativo y pestañas clínicas — anamnesis/HCE, evoluciones append-only,
  odontograma FDI interactivo por pieza/superficie, adjuntos RX/fotos, presupuestos
  (armado, envío, aceptación/rechazo, gate de consentimiento) y consentimientos
  firmados. Incluye cerrar el turno como `atendido` y mostrar la fecha sugerida de
  control/recall, que recepción puede agendar.
- `features/caja`: deuda y movimientos del paciente, cobro de saldo en
  efectivo/transferencia/MP con recibo, y cierre de caja del día contra turnos
  atendidos.
- `shared/api-client`: soporte de `PATCH`/`DELETE`/multipart y propagación del
  `detail` de error para que las features muestren mensajes de dominio.
- Guards y rutas existentes se respetan; recepción y asistente no leen ni editan
  datos clínicos, y el odontólogo no cobra (solo lectura de caja).

**Sin cambios incompatibles**: no se rediseñan rutas, guards, auth ni el contrato
de la cuenta corriente; solo se agregan operaciones y pantallas.

## Capabilities

### New Capabilities

- `clinica-ui`: espacio clínico del paciente en la web (HCE, evoluciones,
  odontograma, adjuntos, presupuestos, consentimientos) con visibilidad por rol,
  cierre de turno y agendado de control.
- `caja-mostrador`: operación de caja de recepción (deuda, cobro de saldo,
  recibo y cierre diario) sobre la cuenta corriente y los turnos atendidos.

### Modified Capabilities

- `presupuestos-planes`: la cuenta corriente deja de ser solo-débito y pasa a
  admitir pagos/créditos append-only y recibo; el cierre diario se especifica en
  `caja-mostrador` y se ajustan los roles de cobro.
- `turnos-agenda`: se agrega el contrato HTTP de creación, cambio de estado y
  cancelación que el spec solo describía a nivel de modelo/DB.
- `frontend-app-shell`: `/pacientes/:id` y `/caja` dejan de ser placeholders y
  pasan a features reales; el api-client incorpora los verbos y el manejo de
  errores que necesitan las features.

## Impact

- **Backend**: `app/application/cuenta_corriente.py`, `app/api/presupuestos.py`,
  nuevo `app/application/turnos.py` + `app/api/turnos.py`, wiring en
  `app/main.py`, `app/infrastructure/pdf.py` (recibo).
- **Frontend**: `src/shared/api-client.ts`, `src/features/clinica/*`,
  `src/features/caja/*`, `src/features/agenda/agenda-api.ts`,
  `src/app/router.tsx`, y `PacientesPlaceholder.tsx`,
  `PacienteDetallePlaceholder.tsx` y `CajaPlaceholder.tsx` reemplazados.
- **API**: nuevas rutas de pagos, recibo, cierre de caja y ciclo de vida de
  turnos; sin migración nueva (se reutilizan `movimiento_cc` y `turno`).
- **Dependencias**: ninguna dependencia de runtime nueva en frontend (React,
  router y Zustand ya presentes); backend usa el `SimplePdfWriter` de C-13.
- **Tests**: backend (TDD con stores in-memory) + frontend (Vitest/RTL) con datos
  ficticios; E2E Flujo 3 y Flujo 4 sin Postgres ni red.
- **Roles**: recepción cobra y ve caja; odontólogo/propietario operan clínica;
  asistente no accede a cobros ni a datos clínicos.
