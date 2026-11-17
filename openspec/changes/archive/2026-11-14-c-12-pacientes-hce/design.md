# Design

## Context

Ver `proposal.md` - Why. El backend ya usa el patrón de los changes recientes: modelos SQLAlchemy en `app/domain/<área>/models.py`, servicios de aplicación con `Protocol` de store + implementación in-memory para tests y SQLAlchemy para la API autenticada, routers en `app/api/`, y migraciones Alembic numeradas con RLS + FORCE RLS en cada tabla tenant.

Restricciones relevantes:
- `turno.paciente_id` y `lista_espera.paciente_id` ya existen como UUID nullable **sin FK** (C-06/C-09); C-12 no puede romper turnos históricos creados antes de que existiera `paciente`.
- `Principal` trae `sub` (usuario), `tenant_id` y `roles`; no trae `profesional_id`. El vínculo es `profesional.usuario_id = principal.sub`.
- La visibilidad clínica (RN-SE-02) no se resuelve solo con roles: un `odontologo` que no atendió al paciente no debe ver su HCE.
- El proyecto exige append-only para evoluciones (RN-HC-01) y migraciones Alembic para todo DDL.
- La migración vigente es `c11a1b2c3d4e5`; C-12 usa `c12a1b2c3d4e5`.

## Goals / Non-Goals

**Goals:**
- Pacientes tenant-scoped con DNI opcional único por tenant y consentimiento fechado.
- Historia clínica 1:1 por paciente/tenant, con anamnesis editable.
- Evoluciones append-only garantizadas en base de datos, no solo por la API.
- Autorización clínica derivada de turnos del paciente y de derivaciones explícitas.
- Todo testeable sin Postgres (stores in-memory) y con SQL estático para la migración.

**Non-Goals:**
- Odontograma, adjuntos RX/fotos, presupuestos, planes y consentimientos firmados (C-13/C-14).
- Firma digital o validación regulatoria de la HCE (SU-04 queda como supuesto).
- Backfill de `turno.paciente_id` históricos ni FK desde `turno` (evita romper datos previos).
- Búsqueda full-text de pacientes o merge de duplicados.

## Decisions

**D1 - Dominio `pacientes` separado de `agenda`.**
`Paciente`, `HistoriaClinica`, `Evolucion` y `DerivacionHCE` viven en `backend/app/domain/pacientes/models.py` y se registran en `app/domain/__init__.py`. Evita mezclar identidad clínica con catálogo/agenda y sigue el patrón de C-11 (`domain/notificaciones`).

**D2 - DNI opcional con unicidad parcial en DB.**
`dni` nullable + índice único parcial `(tenant_id, dni) WHERE dni IS NOT NULL`. Alternativa considerada: `dni NOT NULL` con valor ficticio, rechazada porque menores o extranjeros pueden no tenerlo. El servicio valida primero para dar 409 legible; la DB es la garantía ante carreras.

**D3 - Consentimiento con CHECK de coherencia.**
`consentimiento_datos BOOLEAN NOT NULL DEFAULT false` + `consentimiento_at TIMESTAMPTZ NULL` con CHECK `(consentimiento_at IS NULL OR consentimiento_datos)`. Evita el estado "consentimiento sin fecha".

**D4 - Historia 1:1 y creación idempotente.**
`UNIQUE (tenant_id, paciente_id)` en `historia_clinica`. El servicio expone `obtener_o_crear(paciente_id)`: si existe, la devuelve; si no, la crea vacía. Un segundo POST nunca duplica (409/200 idempotente, se devuelve la existente).

**D5 - Append-only en la base, no solo en la app.**
Además de no exponer `PATCH`/`DELETE` de evoluciones, la migración crea `evolucion_append_only()` y triggers `BEFORE UPDATE OR DELETE` que hacen `RAISE EXCEPTION`. Razón: un `UPDATE` directo por SQL, script o bug de ORM debe fallar. La corrección se modela con `corrige_evolucion_id` (self-FK `ON DELETE RESTRICT`) y una nueva fila.

**D6 - Autoría de la evolución explícita.**
`Evolucion` guarda `autor_usuario_id` (FK `usuario`, NOT NULL) y `autor_profesional_id` (FK `profesional`, nullable). El servicio toma `autor_usuario_id` de `principal.sub` (nunca del body) y, si el usuario tiene profesional asociado, lo completa. `created_at` usa reloj de DB.

**D7 - Visibilidad clínica resuelta por servicio, no por rol.**
`AccesoClinicoService.puede_acceder(principal, paciente_id)` devuelve verdadero si:
1. el rol es `propietario`, o
2. existe `profesional` con `usuario_id = principal.sub` y al menos un `turno` del paciente con ese `profesional_id`, o
3. existe `derivacion_hce` del paciente hacia ese profesional.
Recepción/asistente se rechazan antes, por rol. Un `odontologo` no tratante recibe 403. Alternativa considerada: guard por rol `odontologo` solamente, rechazada porque viola RN-SE-02.

**D8 - Derivación como tabla explícita.**
`derivacion_hce` (tenant, paciente, `desde_profesional_id?`, `hacia_profesional_id`, motivo?, `created_by`, created_at) registra la derivación. Solo propietario o tratante puede crearla. Es la única vía para que un profesional ajeno acceda sin turnos. Alternativa: campo booleano en la historia, rechazada por no ser auditable ni revocable por destinatario.

**D9 - Paciente borrado solo por propietario y solo sin historial.**
DELETE lógico (`is_active=false`) con `AuditMixin`. Se rechaza con 409 si el paciente tiene turnos o evoluciones. Alternativa: borrado físico en cascada, rechazada porque destruiría historia clínica (viola el espíritu append-only y RN-SE-04).

**D10 - Sin FK desde `turno.paciente_id`.**
No se agrega FK en la migración 008: los turnos existentes pueden apuntar a UUIDs creados por C-06/C-08 antes de que existiera `paciente`. El vínculo se valida en la API de C-12 al asociar; un backfill queda para C-13/C-14 si hace falta.

**D11 - Stores memory + DB con el mismo `Protocol`.**
`PacienteStore`, `HistoriaStore` y `AccesoClinicoStore` permiten tests sin DB. `Db*Store` recibe la `AsyncSession` ya pineada con `SET LOCAL app.tenant_id` y filtra por tenant además de RLS (defensa en profundidad), igual que C-05/C-11.

**D12 - Errores uniformes.**
`AppError` con 404 (paciente/historia inexistente o de otro tenant), 403 (sin acceso clínico), 409 (DNI duplicado, historia duplicada, borrado con historial) y 422 (validación de body). El detalle nunca revela si el recurso existe en otro tenant.

## Risks / Trade-offs

- [Trigger append-only bloquea también correcciones legítimas por SQL] → la corrección se hace por INSERT con `corrige_evolucion_id`; documentado en el mensaje de error.
- [Resolver tratante consultando turnos puede ser costoso en pacientes con mucho historial] → índice `(tenant_id, paciente_id, profesional_id)` en `turno` (ya existe `(tenant_id, paciente_id)` por RLS/consultas) y cache por request vía store.
- [`principal.sub` puede no ser UUID en tokens de prueba] → el servicio trata el parseo fallido como "sin profesional" y solo propietario/derivación acceden.
- [DELETE lógico deja DNIs ocupados por el índice parcial] → el índice único se define sobre filas `is_active = true` (`WHERE is_active AND dni IS NOT NULL`) para permitir reutilizar el DNI tras un borrado lógico.
- [Migración sin FK desde `turno` deja integridad referencial laxa] → deuda explícita; el servicio rechaza asociar turnos a pacientes de otro tenant.
- [Trigger y RLS deben convivir] → los triggers se crean `FOR EACH ROW` sin `SECURITY DEFINER`; las policies RLS siguen aplicando.

## Migration Plan

1. `alembic upgrade head` aplica la revisión `c12a1b2c3d4e5` (008): crea `paciente`, `historia_clinica`, `evolucion`, `derivacion_hce`, índices, checks, policies RLS/FORCE y triggers append-only.
2. Rollback: `downgrade` elimina triggers, función, policies, índices y tablas en orden inverso; no toca `turno` ni `lista_espera`.
3. Sin backfill: los pacientes se crean desde la API; los turnos históricos conservan su `paciente_id` UUID sin FK.

## Open Questions

- Ninguna que cambie specs, approach o tasks. La validación legal de HCE/consentimiento (SU-04) queda fuera y se registra como supuesto en el proposal.
