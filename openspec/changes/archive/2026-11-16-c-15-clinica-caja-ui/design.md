# Design

## Context

Ver `proposal.md` — Why. El estado relevante del repo al planificar:

- **C-14 completo**: `application/presupuestos.py` y `application/cuenta_corriente.py`
  exponen cuentas con saldo derivado y movimientos append-only; solo existe
  `registrar_debito` y `GET /api/pacientes/{id}/cuenta-corriente`. No hay pagos,
  recibos ni cierre.
- **Cobros C-10**: `Pago` (tabla `pago`) está atado a un turno y representa la seña
  de Mercado Pago. `GET /api/turnos/agenda` (read model `AgendaCobroService`) ya
  devuelve turno + `cobro` (`pendiente|acreditado|vencido|rechazado|sin-sena`).
- **Gap C-06**: la migración 004 creó `turno`, los constraints GIST
  `excl_turno_profesional`/`excl_turno_sillon` y RLS, pero los endpoints
  `POST /turnos`, `PATCH /turnos/{id}/estado`, `cancelar`, `reprogramar` y
  `sobreturno` nunca se montaron: OpenAPI solo muestra `GET /api/turnos/agenda`.
  No hay `TurnoStore`/`TurnoRepository` ni tests de C-06/C-07.
- **RBAC** (`application/rbac.py`): `cobros` → propietario CRUD, recepción CRUD,
  odontólogo R, asistente nada; `agenda` → propietario CRUD, recepción CRUD,
  odontólogo RUD, asistente R.
- **Frontend**: shell C-04 con placeholders `/pacientes`, `/pacientes/:id`, `/caja`;
  `shared/api-client.ts` solo tiene `get/post`, no propaga `detail` y
  `agenda-api.cambiarEstado` usa `fetch` sin `Authorization`. `shared/ui` tiene
  `Table`, `Modal`, `Form/Field`, `Toast`; Vitest + RTL ya configurados.
- **Reglas duras**: sin migración ad-hoc, RLS + tenant explícito, datos ficticios,
  sin secretos en cliente, append-only clínico.

## Goals / Non-Goals

**Goals:**

- Operar Flujo 3 (HCE → odontograma → presupuesto → consentimiento → plan) y
  Flujo 4 (deuda → cobro → recibo → cierre) desde la web, con roles reales.
- Backend mínimo y auditable para pagos, recibo, cierre y ciclo de vida de turnos.
- Cambios de UI verificables con RTL y sin dependencias nuevas.
- Cero migraciones: el head Alembic sigue en `d14a1b2c3d4e5`.

**Non-Goals:**

- Completar C-06 (reprogramar, sobreturno, reprogramación con seña).
- Devoluciones automáticas, notas de crédito o conciliación bancaria.
- Reportes del dueño, ocupación/ausentismo (C-16), auditoría/exportación (C-17).
- Facturación ARCA, obras sociales o checkout MP nuevo (C-10 ya cubre la seña).
- Rediseñar la agenda C-07; solo se corrige su cliente HTTP.

## Decisions

### D1. Pagos como créditos de `movimiento_cc`, sin migración

Se agrega `CuentaCorrienteService.registrar_pago(...)` que crea un movimiento
`tipo="credito"` reutilizando el ledger existente. El **medio** y la **clave de
idempotencia** se codifican en `referencia` con el formato
`pago:{medio}:{clave}`, y la descripción legible queda en `descripcion`
(`Cobro en efectivo`, etc.). El saldo sigue siendo `Σ débitos − Σ créditos` y los
movimientos siguen append-only.

- **Por qué**: evita una migración 011 que chocaría con la numeración reservada de
  C-17 y mantiene el ledger como única fuente de verdad.
- **Alternativa descartada**: columna `medio` en `movimiento_cc` + migración 011.
  Es más limpia, pero adelanta una migración y obliga a renumerar C-17; queda como
  normalización posible en C-16 (columna + backfill desde `referencia`).
- **Trade-off**: `referencia` deja de ser opaca. Se mitiga con un parser único
  (`parse_referencia_pago`) y constantes de medio; el detalle del cierre agrupa por
  ese parser, no por texto libre.
- **Idempotencia**: la UI genera `idempotency_key` (UUID) al abrir el formulario y
  la reutiliza en reintentos; el backend construye la referencia y, si ya existe,
  devuelve el movimiento existente sin sumar dos veces. Sin clave, el backend
  genera una y no deduplica (cada cobro es distinto).
- **Sobrepago**: permitido; deja saldo a favor (negativo) y el recibo lo muestra.
  No se limita al saldo porque recepción puede cobrar un anticipo.

### D2. Recibo PDF determinístico

`GET /api/movimientos-cc/{id}/recibo` arma líneas con paciente, documento, monto,
medio, fecha, referencia y saldo resultante, y usa `SimplePdfWriter` (C-13). El
contenido no incluye hora de generación para que el PDF sea reproducible. Se
autoriza con `authorize(roles, "cobros", "R")` y se responde 404 cross-tenant.

- **Por qué**: reutiliza el writer sin dependencias y mantiene el mismo patrón de
  descarga que el consentimiento C-13.
- **Alternativa**: recibo HTML/imprimible en el navegador. Se descarta porque el
  Flujo 4 pide recibo descargable y el backend ya sabe emitir PDFs.

### D3. Cierre de caja como read model del día

`GET /api/caja/cierre?fecha=YYYY-MM-DD` devuelve:

- `cobrado_total` y `por_medio` (`efectivo|transferencia|mp`) sumando créditos del
  día cuyo `referencia` matchea `pago:{medio}:`;
- `cantidad_pagos`, `deuda_generada` (débitos del día) y
  `diferencia_caja = cobrado_total − deuda_generada`;
- `turnos_atendidos` (cantidad) y `turnos` del día con estado `atendido`;
- `movimientos` del día para el detalle.

Los límites del día usan `America/Argentina/Buenos_Aires` (`AGENDA_TZ` de C-10).

- **Por qué**: no hace falta una tabla de cierre ni un arqueo de caja inicial en
  este alcance; el ledger y la agenda ya tienen los datos.
- **Alternativa descartada**: tabla `cierre_caja` con snapshot. Se pospone a C-16,
  que es dueño de reportes y del cierre operativo completo.
- **Trade-off**: no se concilia turno↔pago individualmente. La UI muestra ambos
  universos (cobros y turnos atendidos) y la diferencia de caja, sin inventar un
  vínculo que el modelo no tiene.

### D4. Ciclo de vida de turnos mínimo, sobre el modelo existente

Nuevo `application/turnos.py` con `TurnoService`, puertos `TurnoStore`,
`TurnoCatalogStore` (prestación/profesional/sillón) y `BloqueoStore`; stores
in-memory y SQLAlchemy. `POST /api/turnos`:

- valida tenant de paciente/profesional/sillón/prestación;
- calcula `fin = inicio + duracion_min + buffer` en servidor (nunca confía en el
  cliente);
- pre-valida solape por profesional y sillón (`estado <> 'cancelado'`) y bloqueo,
  y mapea el `IntegrityError` de los constraints GIST a 409 (carrera);
- crea en estado `pendiente`, `origen="recepcion"` (o `"control"` si la UI agenda
  un control).

`PATCH /api/turnos/{id}/estado` aplica una máquina de estados explícita:
`pendiente|confirmado|reservado-pendiente-pago → confirmado|atendido|ausente|cancelado`;
`atendido|ausente|cancelado` son terminales; mismo estado = 200 idempotente;
otra transición = 409.

`POST /api/turnos/{id}/cancelar` marca `cancelado`, calcula
`cancelacion_tardia = ahora > inicio − anticipacion_min_cancel_hs` y devuelve
`{turno, cancelacion_tardia, senia_perdida}` con
`senia_perdida = cancelacion_tardia and prestacion.sena_obligatoria`. No toca la
tabla `pago` (devolución/conciliación queda fuera de alcance). Repetir la
cancelación devuelve 200 sin duplicar efectos.

- **Por qué**: es el mínimo que exige C-15 (cerrar como atendido + agendar
  control). Reprogramar/sobreturno se dejan como deuda explícita de C-06.
- **Roles**: crear exige `authorize("agenda","C")` (propietario, recepción);
  cambiar estado y cancelar exigen `authorize("agenda","U")` (propietario,
  recepción, odontólogo); asistente 403.
- **Consecuencia de la matriz**: el odontólogo no crea turnos, así que la ficha le
  muestra la fecha de control sugerida y recepción es quien agenda el control.

### D5. Ficha clínica con estado local y pestañas por rol

`features/clinica` reemplaza `/pacientes` y `/pacientes/:id`:

- **Listado** (`PacientesPage`): búsqueda por `q`, tabla paginada y acceso a ficha.
- **Ficha** (`PacienteFichaPage`): bloque administrativo siempre visible; pestañas
  HCE, odontograma, adjuntos, presupuestos y consentimientos solo para
  propietario/odontólogo. Recepción/asistente ven datos administrativos, turnos y
  cuenta (si su rol lo permite).
- **Estado**: React local por pestaña; sin store global clínico y sin persistir
  datos de salud en `localStorage` (solo el access token sigue en el store
  versionado de C-03). Al cambiar de paciente se descarta el estado clínico.
- **Odontograma**: grilla de 32 botones FDI agrupados por arcada, con `aria-label`
  por pieza y resumen del estado vigente; el alta de evento se hace en un `Modal`
  con estado + superficie condicional (misma tabla de reglas que C-13) y se envía
  al backend, que sigue siendo la autoridad.
- **Presupuestos**: editor con prestaciones del catálogo, cantidad, pieza/superficie,
  etapa y total devuelto por el servidor. Enviar/aceptar/rechazar según estado; un
  409 `consentimiento_requerido` se muestra y se recarga el presupuesto.
- **Consentimientos**: formulario de firma (tipo, texto, versión, firmante,
  `plan_invasivo`) + lista con `hash_valido` y enlace al PDF.
- **Cierre y control**: panel con el turno abierto del paciente; botón "Marcar
  atendido" para roles con `agenda U`; fecha sugerida `fin + intervalo_control_dias`
  y botón "Agendar control" solo para roles con `agenda C`, que navega al alta de
  turno con prestación/fecha precargadas.
- **Formato de dinero**: la UI solo formatea (`Intl.NumberFormat("es-AR")`); los
  montos que envía son strings decimales y los totales siempre vienen del backend.

### D6. Caja de mostrador con idempotencia en el cliente

`features/caja` reemplaza `/caja`:

- buscador de paciente (reutiliza `GET /api/pacientes?q=`), panel de saldo y
  movimientos, y formulario de cobro con monto, medio y clave de idempotencia;
- al confirmar, `POST /api/pacientes/{id}/cuenta-corriente/pagos` devuelve el
  movimiento y el saldo nuevo; la UI reemplaza el estado con esa respuesta (no
  recalcula plata en el cliente);
- el recibo se pide a `GET /api/movimientos-cc/{id}/recibo` y se abre como blob;
- el cierre del día se consulta a `GET /api/caja/cierre?fecha=` y muestra cobros
  por medio, deuda generada, diferencia y turnos atendidos;
- los turnos del día salen de `GET /api/turnos/agenda?fecha=` (estado de agenda +
  cobro MP) y permiten seleccionar el paciente para cobrar.
- **Odontólogo**: ve caja en modo lectura (saldo, movimientos, cierre) sin
  formulario de cobro, consistente con `cobros: R`. **Asistente**: sin ruta.

### D7. ApiClient con verbos, multipart y errores de dominio

Se generaliza `ApiClient.request` y se agregan `patch`, `delete`, `upload`:

- `upload` recibe `FormData` y **no** fija `content-type` (el browser pone el
  boundary); mantiene `Authorization` y el refresh único ante 401;
- se parsea el cuerpo JSON de error y se usa `detail` como `ApiError.message`
  (fallback al status);
- `delete` tolera 204 sin cuerpo;
- `agenda-api.cambiarEstado` pasa a `client.patch(...)` y deja de perder el token.

### D8. Contratos HTTP nuevos

| Método | Ruta | Rol | Respuesta |
|--------|------|-----|-----------|
| `POST` | `/api/pacientes/{id}/cuenta-corriente/pagos` | propietario, recepción | 201 `{movimiento, saldo}` |
| `GET` | `/api/movimientos-cc/{id}/recibo` | propietario, recepción, odontólogo | 200 `application/pdf` |
| `GET` | `/api/caja/cierre?fecha=` | propietario, recepción, odontólogo | 200 cierre |
| `POST` | `/api/turnos` | propietario, recepción | 201 turno |
| `PATCH` | `/api/turnos/{id}/estado` | propietario, recepción, odontólogo | 200 turno |
| `POST` | `/api/turnos/{id}/cancelar` | propietario, recepción, odontólogo | 200 `{turno, cancelacion_tardia, senia_perdida}` |

Todos los schemas usan `extra="forbid"`; fechas ISO-8601 con offset; 404
cross-tenant; 403 por rol; 409 por conflicto de estado/agenda; 422 por validación.

### D9. Persistencia y wiring

- `MovimientoCCStore` suma `get(tenant, id)` y `list_between(tenant, desde, hasta)`
  para recibo y cierre (memory y DB).
- `DbTurnoStore` opera `Turno` con `tenant_id` explícito y flush (mismo patrón
  C-12/C-13/C-14: `get_db` no commitea).
- `main.py` registra `turnos_router`; los servicios se construyen con
  `tenant_session` + `Principal` (D11/D14), igual que C-14.
- No se toca Alembic: `alembic heads` debe seguir en `d14a1b2c3d4e5`.

### D10. Estrategia de tests

- **Backend**: `tests/support_c15.py` con rig in-memory (pacientes, prestaciones,
  profesionales, sillones, bloqueos, turnos, cuentas, movimientos) y un cliente
  FastAPI con dependencias overrideadas. Cubre servicio, HTTP y E2E Flujo 3/4 sin
  Postgres ni red. Migración: test estático de que no hay revisión nueva y que los
  constraints 004 siguen referenciados.
- **Frontend**: Vitest + RTL + `vi.stubGlobal("fetch")`. Casos por comportamiento:
  api-client (PATCH/upload/errores/refresh), ficha por rol, validación de
  odontograma, flujo de presupuesto con 409, caja (cobro, idempotencia, recibo,
  cierre) y router con páginas reales.
- **Datos**: todos ficticios y marcados (`Paciente Ficticio C-15`, dominios
  `.invalid`), sin PII real.

## Risks / Trade-offs

- **`referencia` como soporte del medio** → parser único + constantes + test de
  cierre por medio; normalización con columna `medio` queda anotada para C-16.
- **Cierre sin vínculo turno↔pago** → el cierre muestra cobros, deuda generada,
  diferencia y turnos atendidos por separado; no se afirma conciliación uno a uno.
- **Deuda C-06 (reprogramar/sobreturno) sigue abierta** → se documenta en
  `CHANGES.md`/tasks y la UI no ofrece esas acciones para no prometer lo que no hay.
- **Odontograma "interactivo" acotado** → grilla FDI + modal por pieza/superficie,
  sin ilustración anatómica; cumple US-031 sin volver el change un proyecto de SVG.
- **Riesgo de PHI en el cliente** → estado clínico solo en memoria, sin
  `localStorage`; tests que verifican que no se persiste nada clínico.
- **Roles**: el odontólogo no crea turnos (matriz KB 03) → el control lo agenda
  recepción; la UI lo refleja para evitar 403 sorpresivos.
- **Sin migración**: si el volumen de movimientos crece, el cierre por parseo de
  referencia puede volverse caro → C-16 puede agregar índices/columna con backfill.

## Migration Plan

1. Deploy backend con rutas nuevas (no hay DDL; no requiere `alembic upgrade`).
2. Deploy frontend; `/pacientes`, `/pacientes/:id` y `/caja` pasan de placeholder a
   feature.
3. Rollback: revertir el deploy de código. No hay datos nuevos que migrar; los
   créditos registrados siguen siendo movimientos válidos del ledger.
4. Verificación: `alembic heads` = `d14a1b2c3d4e5`, suite backend y frontend verdes,
   OpenAPI con las seis rutas nuevas.

## Open Questions

- Ninguna bloqueante. El medio `mp` en caja registra un pago ya confirmado en
  Mercado Pago de forma manual; el checkout online sigue siendo C-10. Si C-16
  necesita conciliación por `mp_payment_id`, se resuelve allí con su propio diseño.
