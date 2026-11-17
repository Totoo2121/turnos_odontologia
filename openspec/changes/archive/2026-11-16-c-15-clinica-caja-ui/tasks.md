# Tasks

## 1. Cuenta corriente: pagos, recibo y cierre

- [x] 1.1 Extender `MovimientoCCStore` con `get(tenant, id)` y `list_between(tenant, desde, hasta)` en los stores in-memory y SQLAlchemy de `application/cuenta_corriente.py`; verificar con tests de lectura por id, rango de fechas, aislamiento por tenant y lista vacía.
- [x] 1.2 Agregar `parse_referencia_pago`, constantes de medio (`efectivo|transferencia|mp`) y `CuentaCorrienteService.registrar_pago` sobre el ledger append-only; verificar con tests de pago válido, saldo a favor por sobrepago, monto ≤ 0 (422), medio inválido (422), misma clave de idempotencia (un solo crédito) y claves distintas (dos créditos).
- [x] 1.3 Implementar el recibo PDF determinístico del movimiento de pago con `SimplePdfWriter` y `GET /api/movimientos-cc/{id}/recibo`; verificar con tests de PDF 200 con monto/medio, 404 cross-tenant, 403 para asistente y lectura permitida a odontólogo.
- [x] 1.4 Implementar el cierre de caja del día como read model (`cobrado_total`, `por_medio`, `cantidad_pagos`, `deuda_generada`, `diferencia_caja`, `turnos_atendidos`, detalle) usando `AGENDA_TZ`; verificar con tests de dos pagos por medio distinto, día sin movimientos, deuda generada y turnos atendidos.
- [x] 1.5 Exponer `POST /api/pacientes/{id}/cuenta-corriente/pagos` y `GET /api/caja/cierre` con schemas `extra="forbid"`, roles de cobros y tenant del token; verificar con tests de 201/200, 403 odontólogo al cobrar, 403 asistente y OpenAPI con las rutas nuevas.

## 2. Ciclo de vida mínimo de turnos

- [x] 2.1 Crear `application/turnos.py` con records, `TurnoStore`/`TurnoCatalogStore`/`BloqueoStore` (Protocol), stores in-memory y SQLAlchemy `DbTurnoStore`, filtrando siempre por tenant; verificar con tests de alta/lectura, aislamiento por tenant y turno inexistente (404).
- [x] 2.2 Implementar `TurnoService.crear` con `fin = inicio + duracion + buffer`, validación de referencias del tenant, bloqueo (409 con motivo), solape por profesional/sillón (409) y mapeo de `IntegrityError` a 409; verificar con tests de fin calculado, cada rechazo y creación válida.
- [x] 2.3 Implementar `PATCH /api/turnos/{id}/estado` con la máquina de estados (`pendiente|confirmado|reservado-pendiente-pago → confirmado|atendido|ausente|cancelado`, terminales, mismo estado idempotente) y `POST /api/turnos/{id}/cancelar` con antelación mínima y `senia_perdida`; verificar con tests de cierre como atendido, transición inválida (409), cancelación en término/tardía y cancelación repetida.
- [x] 2.4 Registrar el router de turnos en `main.py` y aplicar los roles de agenda (`C` para crear; `U` para estado/cancelar) y 404 cross-tenant; verificar con tests de propietario/recepción/odontólogo permitidos, asistente 403, auth obligatoria y OpenAPI.

## 3. Frontend compartido: api-client y rutas reales

- [x] 3.1 Extender `shared/api-client.ts` con `patch`, `delete`, `upload` multipart, manejo de 204 y `detail` del backend en `ApiError`; verificar con tests de PATCH con refresh, upload sin content-type manual, 204 y error 409 legible.
- [x] 3.2 Corregir `features/agenda/agenda-api.ts` para que `cambiarEstado` use el api-client autenticado en lugar de `fetch` suelto; verificar con un test que la llamada envía `Authorization` y el body de estado.
- [x] 3.3 Reemplazar las rutas `/pacientes` y `/caja` en `app/router.tsx` por las nuevas páginas reales manteniendo guards y lazy loading, y dejar `/reportes` y `/admin` como placeholders; verificar con tests de router que cada ruta renderiza la página correcta y que asistente en `/caja` va a `/403`.

## 4. Frontend clínico

- [x] 4.1 Crear `features/clinica/clinica-api.ts` con clientes tipados de pacientes, HCE, evoluciones, odontograma, adjuntos, presupuestos, planes, consentimientos y turnos, más un helper de mensajes de error; verificar con tests de fetch mockeado y de `detail` propagado.
- [x] 4.2 Implementar `PacientesPage` con búsqueda `q`, tabla paginada, estados vacío/error y navegación a `/pacientes/:id`; verificar con tests de búsqueda, lista y apertura de ficha.
- [x] 4.3 Implementar `PacienteFichaPage` con bloque administrativo, pestañas clínicas por rol y aviso de 403 clínico; verificar con tests de odontólogo (ve pestañas), recepción y asistente (no las ven) y profesional ajeno (aviso sin datos).
- [x] 4.4 Implementar la pestaña de HCE/anamnesis con listado de evoluciones, alta append-only y corrección por `corrige_evolucion_id`; verificar con tests de lectura ordenada, alta y ausencia de acciones de edición/borrado.
- [x] 4.5 Implementar el odontograma FDI de 32 piezas con modal de evento y validación estado–superficie (misma tabla que C-13); verificar con tests de render de 32 piezas, alta `caries/oclusal`, bloqueo de `corona` con superficie y error 422 sin actualizar la grilla.
- [x] 4.6 Implementar la pestaña de adjuntos con subida multipart, lista y apertura por URL firmada; verificar con tests de subida válida, archivo rechazado (422) y solicitud de URL firmada sin exponer la clave.
- [x] 4.7 Implementar el editor y detalle de presupuestos (prestación, cantidad, pieza/superficie, etapa, total del servidor) con enviar/aceptar/rechazar y manejo del 409 `consentimiento_requerido`; verificar con tests de armado con dos ítems, aceptación con consentimiento, bloqueo sin firma y recepción sin acciones.
- [x] 4.8 Implementar la pestaña de consentimientos con firma (tipo, texto, versión, firmante, `plan_invasivo`), lista con `hash_valido` y descarga del PDF; verificar con tests de firma válida, firma incompleta y apertura del PDF.
- [x] 4.9 Implementar el cierre de turno como `atendido` y la fecha sugerida de control con agendado solo para roles con `agenda C`; verificar con tests de cierre, sugerencia visible para odontólogo, alta de control por recepción y conflicto 409 visible.

## 5. Frontend de caja

- [x] 5.1 Crear `features/caja/caja-api.ts` y `CajaPage` con búsqueda de paciente, saldo, movimientos y estados vacío/error; verificar con tests de paciente con deuda, paciente sin cuenta y guard de asistente.
- [x] 5.2 Implementar el formulario de cobro con monto, medio y clave de idempotencia, actualización del saldo desde la respuesta y descarga del recibo; verificar con tests de cobro en efectivo, transferencia/MP, monto inválido (422), reintento idempotente y odontólogo sin formulario.
- [x] 5.3 Implementar el cierre de caja del día con cobros por medio, deuda generada, diferencia y turnos atendidos, más la lista de turnos del día con estado de cobro MP; verificar con tests de cierre con datos, día vacío, turno `acreditado`/`sin-sena` y rol sin permiso.

## 6. Integración y cierre

- [x] 6.1 Escribir un E2E backend del Flujo 3 sin Postgres ni red: paciente → HCE → odontograma → presupuesto → 409 invasivo → consentimiento → aceptar → plan por etapas → deuda → cobro → saldo; verificar deuda exacta y visibilidad por rol.
- [x] 6.2 Escribir un E2E backend del Flujo 4: agenda del día con cobro MP → paciente con deuda → pago idempotente → recibo PDF → cierre del día con turnos atendidos; verificar totales y diferencias.
- [x] 6.3 Escribir un test de integración de frontend con API mockeada que recorra ficha (presupuesto + consentimiento) y caja (cobro + cierre) respetando la matriz de roles; verificar que recepción no ve acciones clínicas y que odontólogo no cobra.
- [x] 6.4 Actualizar `README.md` con las rutas de caja/turnos, el alcance de pagos manuales (incluido `mp`), la ausencia de migración y la deuda explícita de C-06 (reprogramar/sobreturno); verificar que las rutas documentadas coinciden con OpenAPI.
- [x] 6.5 Correr `python -m pytest -q`, `npm test` y `npm run build` en frontend, `ruff check` de los archivos tocados y `alembic heads`; verificar head `d14a1b2c3d4e5`, sin migración nueva y sin regresiones sobre la línea base de C-14.

## Workflow follow-up

- [x] Sincronizar las specs principales y archivar el change cuando la implementación y la revisión estén completas.
- [x] Actualizar `CHANGES.md` con C-15 en `[x]` y registrar la deuda de C-06 que queda pendiente.
