# Design

## Context

Ver `proposal.md` - Why. C-14 se apoya en el patrón ya establecido por C-12/C-13: modelos SQLAlchemy en `app/domain/<área>/models.py` registrados en `app/domain/__init__.py`, servicios de aplicación con stores `Protocol` + implementaciones memoria (tests) y SQLAlchemy (API), routers en `app/api/`, `AccesoClinicoService` para visibilidad clínica y migraciones Alembic con RLS + FORCE RLS.

Restricciones relevantes:
- La migración vigente es `c13a1b2c3d4e5` (009); C-14 usa `d14a1b2c3d4e5` (010).
- `Prestacion.precio` es `Numeric(12,2)` nullable y **no** existe un flag de invasividad en el catálogo.
- `ConsentimientoService.tiene_consentimiento_invasivo(tenant_id, paciente_id)` de C-13 ya expone el gate de RN-HC-04.
- `AccesoClinicoService.puede_acceder(principal, paciente_id)` resuelve propietario / tratante por turno / derivación.
- `rbac.MATRIX` ya modela el recurso `cobros` (lectura para propietario, odontólogo y recepción).
- Los registros existentes usan `float` para dinero en algunos stores; C-14 usa `Decimal` de punta a punta para no perder centavos.
- Reglas duras: RLS + FORCE RLS en toda tabla de tenant, DDL solo por migración, y trazabilidad append-only en registros financieros.

## Goals / Non-Goals

**Goals:**
- Presupuesto con ítems por prestación + pieza FDI, precio snapshot y total exacto en ARS.
- Máquina de estados explícita con edición limitada al borrador.
- Aceptación idempotente que produce un plan por etapas y un único débito por el total exacto.
- Gate de consentimiento invasivo reutilizando C-13.
- Cuenta corriente con saldo derivado de solo lectura y movimientos inmutables.
- Todo testeable sin Postgres ni red con stores in-memory.

**Non-Goals:**
- Registrar pagos, créditos, recibos, arqueo o cierre de caja (C-16).
- Avanzar/completar etapas del plan o marcarlo `completado` desde la API (se expone el estado inicial; la progresión es de C-15/C-16).
- Enviar el presupuesto por WhatsApp/email (C-11) o generar su PDF.
- Obras sociales, nomencladores, copagos, impuestos, descuentos o presupuestos en otra moneda.
- Vincular el presupuesto a un turno o aplicar señas de C-10.
- UI de presupuestos/planes (C-15).

## Decisions

**D1 - Dominio y separación de servicios.**
`Presupuesto`, `PresupuestoItem`, `PlanTratamiento`, `CuentaCorriente` y `MovimientoCC` viven en `backend/app/domain/clinica/models.py` y se registran en `app/domain/__init__.py`. La capa de aplicación se separa en `application/presupuestos.py` (presupuesto + plan + aceptación) y `application/cuenta_corriente.py` (cuenta + movimientos + saldo). `PresupuestoService` recibe `CuentaCorrienteService` y `ConsentimientoService` por composición, de modo que C-16 reutilice la cuenta sin acoplarse a presupuestos. Alternativa considerada: un dominio `administracion` nuevo; se descartó para no abrir un paquete por dos tablas y porque el plan es un artefacto clínico.

**D2 - Modelo de datos (migración 010).**
- `presupuesto`: `id`, `tenant_id`, `paciente_id`, `historia_clinica_id`, `creado_por_usuario_id`, `estado varchar(12)`, `moneda varchar(3) default 'ARS'`, `total numeric(12,2)`, `validez_hasta date`, `enviado_at?`, `aceptado_at?`, `rechazado_at?`, `observaciones?`, `created_at`, `updated_at`.
  - `CHECK estado IN ('borrador','enviado','aceptado','rechazado')`, `CHECK moneda = 'ARS'`, `CHECK total >= 0`.
  - Índice `(tenant_id, paciente_id, estado)`.
- `presupuesto_item`: `id`, `tenant_id`, `presupuesto_id` (FK CASCADE), `prestacion_id` (FK RESTRICT), `pieza_fdi smallint?`, `superficie varchar(16)?`, `descripcion varchar(200)`, `cantidad smallint default 1`, `precio_unitario numeric(12,2)`, `importe numeric(12,2)`, `etapa smallint default 1`, `requiere_consentimiento boolean default false`, `created_at`.
  - `CHECK cantidad > 0`, `CHECK precio_unitario >= 0`, `CHECK importe >= 0`, `CHECK etapa BETWEEN 1 AND 20`.
  - `CHECK` FDI reutilizando la regla de C-13 (`pieza_fdi BETWEEN 11 AND 48 AND pieza_fdi % 10 BETWEEN 1 AND 8 AND pieza_fdi / 10 BETWEEN 1 AND 4`), solo cuando no es NULL.
  - `CHECK superficie IN (...)` cuando no es NULL y `CHECK (superficie IS NULL OR pieza_fdi IS NOT NULL)`.
  - Índice `(tenant_id, presupuesto_id, etapa)`.
- `plan_tratamiento`: `id`, `tenant_id`, `presupuesto_id`, `paciente_id`, `consentimiento_id?` (FK RESTRICT), `estado varchar(12) default 'activo'`, `total numeric(12,2)`, `etapas smallint`, `etapa_actual smallint default 1`, `created_at`, `updated_at`.
  - `UNIQUE (tenant_id, presupuesto_id)` `uq_plan_tenant_presupuesto` (idempotencia).
  - `CHECK estado IN ('activo','completado','cancelado')`, `CHECK etapas >= 1`, `CHECK etapa_actual BETWEEN 1 AND etapas`, `CHECK total >= 0`.
- `cuenta_corriente`: `id`, `tenant_id`, `paciente_id`, `moneda default 'ARS'`, `created_at`, `updated_at`.
  - `UNIQUE (tenant_id, paciente_id)` `uq_cc_tenant_paciente` (idempotencia).
  - Sin columna `saldo`: el saldo se deriva de los movimientos (D9).
- `movimiento_cc`: `id`, `tenant_id`, `cuenta_id` (FK RESTRICT), `plan_tratamiento_id?` (FK RESTRICT), `tipo varchar(8)`, `monto numeric(12,2)`, `descripcion varchar(200)`, `referencia varchar(80)?`, `ocurrido_at timestamptz default now()`, `created_at`.
  - `CHECK tipo IN ('debito','credito')`, `CHECK monto > 0`.
  - `UNIQUE (tenant_id, referencia)` `uq_movimiento_cc_tenant_referencia`; en Postgres los NULL no colisionan, así que los movimientos sin referencia (C-16) no se limitan.
  - Índice `(tenant_id, cuenta_id, ocurrido_at)`.
- `prestacion.requiere_consentimiento boolean NOT NULL DEFAULT false` (aditivo).

**D3 - Dinero exacto en ARS.**
El servidor fija `moneda='ARS'` y rechaza con 422 cualquier moneda enviada distinta (el schema usa `extra="forbid"`). Los importes se representan con `Decimal` y se persisten en `Numeric(12,2)`; cada operación se cuantiza con `Decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. `importe = cantidad × precio_unitario` y `total = Σ importes`; el total nunca se acepta del cliente. Los schemas Pydantic usan `Decimal` (JSON como string decimal) para evitar `float` en la frontera. Alternativa considerada: `float` como en `Pago`; rechazada porque C-14 compara centavos exactos (deuda exigible).

**D4 - Snapshot de precio y descripción.**
Al crear un ítem, `precio_unitario` sale del body si viene; si no, de `prestacion.precio`. Si ambos son NULL → 422 `precio_requerido`. `descripcion` sale del body o de `prestacion.nombre`. El ítem no vuelve a consultar el catálogo al leer ni al aceptar, de modo que un cambio posterior de precio/nombre no altera una oferta ya emitida. Editar el ítem en `borrador` recalcula `importe` y el total del presupuesto; en otros estados responde 409.

**D5 - Vínculo con el odontograma por pieza FDI.**
`pieza_fdi` y `superficie` son opcionales (una consulta o limpieza no se ata a una pieza). Cuando vienen, se validan con la misma nomenclatura FDI y el mismo catálogo de superficies que C-13; se exponen helpers reutilizables (`validar_fdi`, `validar_superficie`, `SUPERFICIES`) desde `application/clinica.py`. **No** hay FK a `evento_pieza`: el odontograma es append-only y una pieza tiene varios eventos; el presupuesto referencia la pieza FDI, no un evento puntual (patrón Bilog de RN-HC-03). No se exige que la pieza tenga eventos previos: se puede presupuestar un tratamiento antes de registrarlo.

**D6 - Máquina de estados y edición.**
Transiciones permitidas: `borrador→enviado`, `enviado→aceptado`, `enviado→rechazado`. Cualquier otra (incluido `borrador→aceptado`, `rechazado→*`, `aceptado→*`) responde 409 `transicion_invalida` sin efectos laterales. Reglas:
- Crear presupuesto e ítems: solo roles clínicos con acceso y solo si el presupuesto está `borrador`.
- `PATCH /presupuestos/{id}` (validez, observaciones) y CRUD de ítems: solo `borrador`.
- `DELETE /presupuestos/{id}`: solo `borrador`; los ítems caen por CASCADE.
- `enviar`: exige ≥ 1 ítem y total ≥ 0; fija `enviado_at`.
- `aceptar`/`rechazar`: exigen `enviado`; fijan su timestamp. `aceptar` además valida vigencia, ítems y consentimiento (D7/D10).
La DB refuerza el catálogo de estados con CHECK y protege los ítems con un trigger (D13); la secuencia temporal se valida en el servicio.

**D7 - Aceptación transaccional e idempotente.**
`PresupuestoService.aceptar` ejecuta, en una sola transacción del request:
1. Carga el presupuesto del tenant y verifica `estado='enviado'`.
2. Verifica `validez_hasta >= hoy` (fecha local del tenant) → 409 `presupuesto_vencido`.
3. Verifica ≥ 1 ítem y recalcula el total desde los ítems (nunca desde el cliente).
4. Si algún ítem tiene `requiere_consentimiento`, resuelve el consentimiento invasivo (D10) → 409 si falta.
5. `PlanStore.add` con `UNIQUE (tenant_id, presupuesto_id)`: si ya existe, lo reutiliza (reintento idempotente); si no, crea `PlanTratamiento` con `etapas=max(etapa)`, `etapa_actual=1`, `total` y `consentimiento_id`.
6. `CuentaCorrienteService.obtener_o_crear(tenant, paciente)`.
7. `MovimientoCCStore.add` débito con `monto=total`, `referencia=f"presupuesto:{presupuesto.id}"`; ante colisión de `uq_movimiento_cc_tenant_referencia`, relee el movimiento existente.
8. Marca `presupuesto.estado='aceptado'` y `aceptado_at` solo si aún no estaba aceptado; si ya lo estaba, devuelve plan y saldo sin volver a escribir.
Una carrera entre dos aceptaciones se resuelve por las dos unicidades (plan y referencia): el perdedor captura la violación, relee y devuelve el ganador. El test E2E verifica "un plan, un débito".

**D8 - Plan por etapas sin tabla extra.**
La etapa vive en cada `presupuesto_item` (decisión del usuario). `PlanTratamiento` no duplica líneas: lee los ítems del presupuesto aceptado agrupados por `etapa`, y guarda `etapas`/`etapa_actual` como cabecera. Ventajas: 5 tablas exactas, sin drift entre plan e ítems, y el total del plan es el mismo del presupuesto aceptado. Alternativa considerada: `plan_etapa` con monto y estado por etapa; rechazada por duplicar información y exceder el esquema del roadmap. La progresión de etapas (marcar 2 como actual) queda para C-15/C-16; C-14 solo expone `etapa_actual=1`.

**D9 - Cuenta corriente con saldo derivado y solo débitos.**
`CuentaCorriente` es un ancla única por paciente/tenant. El saldo se calcula como `SUM(debito) - SUM(credito)` en la lectura (`GET /pacientes/{id}/cuenta-corriente`), sin columna cacheada, para que no exista drift entre saldo y movimientos. `MovimientoCC.tipo` admite `credito` desde el esquema para C-16, pero C-14 **no expone** endpoint de pagos/créditos: solo inserta débitos al aceptar. Alternativa considerada: columna `saldo` actualizada en cada movimiento; rechazada por el riesgo de desincronización y porque el volumen por paciente es bajo.

**D10 - Gate de consentimiento invasivo.**
`prestacion.requiere_consentimiento` (nuevo, default `false`) se copia al ítem como `requiere_consentimiento` al crearlo, de modo que un cambio posterior del catálogo no altera presupuestos ya armados. Si **algún** ítem lo requiere, la aceptación llama `ConsentimientoService.tiene_consentimiento_invasivo(tenant, paciente)` (C-13) y, si existe, resuelve el consentimiento más reciente con `ConsentimientoStore.list_by_paciente` para guardar `plan.consentimiento_id`. Sin consentimiento → 409 `consentimiento_requerido`, sin plan ni débito, y el presupuesto queda `enviado`. No se valida fecha de firma ni revocación: C-13 no las modela (deuda declarada); el gate verifica presencia de firma invasiva.

**D11 - Autoría, roles y acceso.**
`creado_por_usuario_id` se toma de `principal.sub` (nunca del body); si no es UUID → 422. Rutas de presupuestos y planes usan `CLINICAL_GUARD = require_any("propietario","odontologo")`, `may_modify_evolution` para escritura y `AccesoClinicoService.puede_acceder` por paciente; un profesional ajeno recibe 403 y un recurso de otro tenant 404. La cuenta corriente se lee con `authorize(roles, "cobros", "R")` (propietario, odontólogo, recepción) y alcance de tenant; el asistente recibe 403. Recepción nunca crea/edita/acepta presupuestos (RN-SE-03), aunque sí consulta la deuda para C-16.

**D12 - Contrato HTTP.**
- `POST /presupuestos` → 201, presupuesto con ítems.
- `GET /presupuestos?paciente_id=&estado=&limit=&offset=` y `GET /presupuestos/{id}`.
- `PATCH /presupuestos/{id}` (solo borrador), `DELETE /presupuestos/{id}` (solo borrador).
- `POST /presupuestos/{id}/items`, `PATCH /presupuestos/{id}/items/{item_id}`, `DELETE /presupuestos/{id}/items/{item_id}` (solo borrador).
- `POST /presupuestos/{id}/enviar|aceptar|rechazar` → presupuesto actualizado; `aceptar` incluye `plan_id` y `movimiento_id` en la respuesta.
- `GET /planes-tratamiento?paciente_id=` y `GET /planes-tratamiento/{id}` con ítems agrupados por etapa.
- `GET /pacientes/{paciente_id}/cuenta-corriente` → `{moneda, saldo, movimientos[]}`.
Errores uniformes: 404 inexistente/otro tenant, 403 sin rol o sin acceso clínico, 409 transición/vencimiento/consentimiento/edición, 422 validación de entrada (FDI, superficie, dinero, etapa, moneda, precio faltante).

**D13 - RLS, FORCE RLS y triggers.**
Las 5 tablas nuevas llevan `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` con policy `tenant_id = current_setting('app.tenant_id')::uuid` en `USING` y `WITH CHECK` (mismo patrón que 008/009). Además:
- `movimiento_cc_append_only()` + triggers `BEFORE UPDATE OR DELETE` con `RAISE EXCEPTION` (trazabilidad financiera).
- `presupuesto_item_guard()` + trigger `BEFORE UPDATE OR DELETE` que consulta el estado del presupuesto padre y falla si no es `borrador`.
- `downgrade` elimina triggers, funciones, policies, índices, tablas y la columna `prestacion.requiere_consentimiento`.

**D14 - Migración y backfill.**
`d14a1b2c3d4e5` cuelga de `c13a1b2c3d4e5`. La columna nueva se agrega con `server_default='false'` y luego se mantiene el default (compatible con filas existentes; no requiere backfill). Las 5 tablas nacen vacías: los presupuestos se crean por API y no hay datos históricos que migrar. Rollback: drop de tablas en orden inverso (movimiento → cuenta → plan → item → presupuesto), triggers/funciones/policies e índices, y drop de la columna al final.

**D15 - Tests sin Postgres.**
Stores in-memory por tenant con las mismas unicidades que la DB (plan por presupuesto, cuenta por paciente, referencia de movimiento) para poder probar idempotencia y aislamiento. La migración se valida por inspección del SQL (`alembic upgrade --sql`) y un test que verifica tablas, columnas, checks, unicidades y policies. El E2E cubre Flujo 3: HCE → odontograma → presupuesto → invasivo sin/con consentimiento → aceptación → plan → débito → saldo.

## Risks / Trade-offs

- [Saldo calculado por SUM en cada lectura] → índice `(tenant_id, cuenta_id, ocurrido_at)`; el volumen por paciente es bajo y evita drift.
- [Carrera de aceptación] → dos unicidades (plan por presupuesto y referencia de movimiento) resuelven la carrera; el test concurrente lo cubre.
- [Precio snapshot queda viejo frente al catálogo] → es intencional: el presupuesto es una oferta emitida; se re-cotiza creando otro presupuesto.
- [Invasividad depende de marcar la prestación] → default `false` y C-15 expone el flag; el seed y la configuración inicial deben marcar cirugías/implantes. Sin marcar, un plan invasivo no se bloquea (riesgo operativo documentado).
- [Gate de consentimiento solo verifica existencia] → C-13 no modela vencimiento/revocación; se registra como deuda y el plan guarda el `consentimiento_id` para auditoría.
- [C-14 no registra pagos] → el saldo solo crece hasta C-16; el contrato deja `credito` listo y la referencia única para los cobros.
- [Trigger de ítems consulta el padre] → costo despreciable por fila y protege contra ediciones SQL fuera de estado; el servicio sigue devolviendo 409 legible.
- [Dinero como Decimal en JSON] → se serializa como string decimal; C-15 debe formatear ARS. Evita errores de coma flotante.
- [Modificar `prestacion` agrega una columna a una tabla existente] → aditivo con default; no rompe C-05 ni turnos históricos.
- [Ítems sin unicidad por (prestación, pieza, etapa)] → se permite repetir una prestación en la misma pieza/etapa (p. ej. dos conductos); la validación de duplicados exactos queda al criterio clínico.

## Migration Plan

1. `alembic upgrade head` aplica `d14a1b2c3d4e5` (010): agrega `prestacion.requiere_consentimiento` y crea `presupuesto`, `presupuesto_item`, `plan_tratamiento`, `cuenta_corriente`, `movimiento_cc` con índices, checks, unicidades, RLS/FORCE y triggers.
2. Rollback: `downgrade` elimina los triggers y funciones, las policies, los índices y las 5 tablas en orden inverso, y por último la columna de `prestacion`; no toca `paciente`, `historia_clinica`, `odontograma`, `consentimiento`, `prestacion` (salvo la columna nueva), `pago` ni `turno`.
3. Sin backfill de datos: tablas nuevas vacías y columna nueva con default `false`. Marcar prestaciones invasivas es configuración operativa (seed/C-15).
4. Al cerrar, actualizar `CHANGES.md` (C-14 `[x]`) y ejecutar `python -m pytest -q`, `ruff check` y `alembic heads` (head esperado `d14a1b2c3d4e5`).

## Open Questions

- Ninguna que cambie specs, approach o tasks. La progresión de etapas, los pagos/créditos, el PDF del presupuesto y el envío por WhatsApp quedan explícitamente fuera de C-14 (C-15/C-16/C-11).
