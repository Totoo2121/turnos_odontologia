# Proposal

## Why

Hoy los turnos se agendan y notifican, pero el paciente no existe como entidad: `turno.paciente_id` es un UUID suelto y no hay historia clínica. Sin pacientes ni HCE no se puede atender con trazabilidad (US-030): no hay anamnesis, no hay evoluciones con autor/fecha y no se cumple RN-HC-01 (una historia por paciente/tenant, append-only) ni RN-SE-02/03 (visibilidad solo para tratantes/propietario y recepción sin permiso de escritura clínica). Es el prerrequisito de C-13 (odontograma) y C-14 (presupuestos).

## What Changes

- Nueva capacidad `pacientes-hce`: pacientes tenant-scoped con datos mínimos de contacto, consentimiento de datos y unicidad de DNI cuando existe.
- CRUD de `/pacientes` (staff) con borrado restringido al propietario; el paciente se referencia desde `turno.paciente_id` sin romper turnos históricos.
- Historia clínica única por paciente y tenant (`historia_clinica`), con anamnesis estructurada (alergias, medicación, antecedentes).
- Evoluciones **append-only** (`evolucion`): autor + fecha, sin UPDATE/DELETE (RN-HC-01). La corrección es una nueva evolución que referencia la anterior (`corrige_evolucion_id`).
- Visibilidad clínica restringida: propietario o profesional tratante del paciente (RN-SE-02); recepción y asistente no leen ni escriben evoluciones (RN-SE-03).
- Derivación explícita registrada (`derivacion_hce`) para habilitar el acceso de otro profesional sin ser tratante.
- Migración 008: `paciente`, `historia_clinica`, `evolucion`, `derivacion_hce`, con RLS + FORCE RLS y un trigger que rechaza UPDATE/DELETE sobre `evolucion`.

## Capabilities

### New Capabilities
- `pacientes-hce`: identidad del paciente, historia clínica única y evoluciones append-only con reglas de visibilidad clínica.

### Modified Capabilities

(ninguna: `turno.paciente_id` ya existe en `turnos-agenda`; C-12 solo lo valida contra la nueva tabla sin cambiar requisitos de agenda)

## Impact

- Backend: dominio `pacientes` (modelos), servicio de aplicación con store `Protocol` + implementación SQLAlchemy y memoria, router `/pacientes` y `/historias-clinicas`, guardas RBAC de visibilidad clínica.
- DB: migración 008 con 4 tablas nuevas, índices, unicidad `(tenant_id, dni)` parcial y `(tenant_id, paciente_id)` en historia, RLS/FORCE RLS y triggers append-only.
- API: `CRUD /pacientes`, `GET/POST /historias-clinicas`, `POST /historias-clinicas/{id}/evoluciones`, `POST /historias-clinicas/{id}/derivaciones`.
- Tests: unicidad de HCE, append-only (UPDATE/DELETE rechazados), visibilidad cruzada denegada salvo propietario/tratante/derivación, recepción sin acceso a evoluciones.
- Depende de C-03 (auth/RBAC) y de las tablas base de C-02; el enlace con turnos usa `turno.paciente_id` existente (C-06).
- Riesgo regulatorio (SU-04): el alcance legal de HCE/consentimiento queda declarado como supuesto; no se agrega firma digital en este change.
