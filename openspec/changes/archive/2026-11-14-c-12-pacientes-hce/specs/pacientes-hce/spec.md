# Spec Delta

## Purpose

Gestiona la identidad del paciente dentro del tenant y su historia clínica única, con anamnesis y evoluciones append-only visibles solo para profesionales tratantes, el propietario o una derivación explícita.

## ADDED Requirements

### Requirement: Pacientes aislados por tenant

El sistema SHALL exponer el CRUD de pacientes solo sobre el tenant del usuario autenticado, sin aceptar `tenant_id` desde el cliente.

#### Scenario: Listado scoped por tenant

- **WHEN** un usuario del tenant A lista pacientes
- **THEN** recibe únicamente pacientes de A y nunca filas de otro tenant

#### Scenario: Acceso cruzado denegado

- **WHEN** un usuario intenta leer un paciente de otro tenant por id
- **THEN** el sistema responde 404 sin revelar su existencia

### Requirement: DNI único por tenant cuando está informado

El sistema SHALL permitir pacientes sin DNI y SHALL rechazar un DNI repetido dentro del mismo tenant.

#### Scenario: Alta sin DNI

- **WHEN** se crea un paciente sin DNI
- **THEN** el alta se acepta y el paciente queda utilizable

#### Scenario: DNI duplicado

- **WHEN** se intenta crear o actualizar un paciente con un DNI ya usado en el tenant
- **THEN** el sistema rechaza la operación sin crear ni modificar el registro

### Requirement: Consentimiento de datos registrado

El sistema SHALL registrar `consentimiento_datos` como booleano y su fecha de otorgamiento, y SHALL exigir fecha cuando el consentimiento es verdadero.

#### Scenario: Consentimiento otorgado

- **WHEN** se registra un paciente con consentimiento verdadero
- **THEN** el sistema guarda la fecha de consentimiento

#### Scenario: Consentimiento sin fecha rechazado

- **WHEN** se marca consentimiento verdadero sin fecha
- **THEN** el sistema rechaza la operación de escritura

### Requirement: Historia clínica única por paciente y tenant

El sistema SHALL mantener como máximo una historia clínica por paciente dentro del tenant y SHALL devolver la existente en lugar de crear otra.

#### Scenario: Primera apertura

- **WHEN** se solicita la historia clínica de un paciente que no tiene una
- **THEN** el sistema crea y devuelve una historia vacía con anamnesis editable

#### Scenario: Segunda apertura

- **WHEN** se solicita la historia clínica de un paciente que ya tiene una
- **THEN** el sistema devuelve la misma historia sin duplicarla

### Requirement: Anamnesis estructurada editable

La historia clínica SHALL exponer alergias, medicación y antecedentes como campos editables por los roles clínicos autorizados.

#### Scenario: Actualización de anamnesis

- **WHEN** un profesional autorizado actualiza alergias, medicación o antecedentes
- **THEN** la historia conserva los nuevos valores y la fecha de actualización

#### Scenario: Rol no clínico no edita anamnesis

- **WHEN** recepción o asistente intenta actualizar la anamnesis
- **THEN** el sistema responde 403

### Requirement: Evoluciones append-only

El sistema SHALL agregar evoluciones con autor y fecha y SHALL rechazar toda modificación o borrado posterior de una evolución existente.

#### Scenario: Alta de evolución

- **WHEN** un profesional autorizado registra una evolución
- **THEN** la evolución queda asociada a la historia con autor, fecha y contenido

#### Scenario: Edición destructiva rechazada

- **WHEN** se intenta actualizar o borrar una evolución existente
- **THEN** el sistema rechaza la operación y la evolución original permanece intacta

### Requirement: Corrección por nueva evolución

El sistema SHALL corregir una evolución mediante una nueva entrada que referencia la anterior, sin alterar la original.

#### Scenario: Corrección trazable

- **WHEN** un profesional registra una corrección indicando la evolución corregida
- **THEN** se crea una evolución nueva que referencia a la anterior y la original no cambia

#### Scenario: Referencia inválida rechazada

- **WHEN** la corrección referencia una evolución de otra historia o de otro tenant
- **THEN** el sistema rechaza el alta

### Requirement: Visibilidad clínica restringida

El sistema SHALL permitir leer la historia clínica y sus evoluciones solo al propietario, a los profesionales tratantes del paciente o a un profesional con derivación explícita registrada.

#### Scenario: Profesional tratante accede

- **WHEN** un profesional con al menos un turno del paciente abre la historia
- **THEN** el sistema le muestra la historia y las evoluciones

#### Scenario: Profesional ajeno denegado

- **WHEN** un profesional sin turnos del paciente y sin derivación abre la historia
- **THEN** el sistema responde 403

#### Scenario: Propietario accede siempre

- **WHEN** el propietario del tenant abre la historia de cualquier paciente
- **THEN** el sistema le muestra la historia y las evoluciones

### Requirement: Derivación explícita habilita acceso clínico

El sistema SHALL registrar derivaciones explícitas de un paciente hacia un profesional y SHALL usar esa derivación para habilitar su acceso clínico.

#### Scenario: Derivación registrada

- **WHEN** un profesional autorizado registra una derivación hacia otro profesional
- **THEN** el profesional derivado puede leer la historia y las evoluciones del paciente

#### Scenario: Derivación de otro paciente no habilita

- **WHEN** existe una derivación hacia un profesional pero para otro paciente
- **THEN** el acceso clínico al paciente consultado sigue denegado

### Requirement: Recepción y asistente sin acceso a evoluciones

El sistema SHALL denegar a recepción y asistente la lectura y escritura de evoluciones clínicas, aunque puedan gestionar datos administrativos del paciente.

#### Scenario: Recepción gestiona paciente

- **WHEN** recepción crea o actualiza los datos administrativos de un paciente
- **THEN** la operación se acepta

#### Scenario: Recepción intenta leer evoluciones

- **WHEN** recepción solicita las evoluciones de una historia clínica
- **THEN** el sistema responde 403

### Requirement: Borrado de paciente restringido

El sistema SHALL permitir borrar un paciente solo al propietario y SHALL rechazar el borrado cuando el paciente tenga turnos o evoluciones registradas.

#### Scenario: Borrado sin historial

- **WHEN** el propietario borra un paciente sin turnos ni evoluciones
- **THEN** el paciente deja de estar disponible

#### Scenario: Borrado con historial rechazado

- **WHEN** el propietario intenta borrar un paciente con turnos o evoluciones
- **THEN** el sistema rechaza la operación y conserva el historial
