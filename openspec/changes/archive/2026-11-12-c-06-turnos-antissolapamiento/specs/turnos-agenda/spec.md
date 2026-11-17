# Spec Delta

## Purpose

Define el ciclo de vida de turnos con anti-solapamiento garantizado a nivel de base de datos, sobreturnos y reprogramación/cancelación, aplicando las reglas RN-AG-01..08 y RN-G-03 del skill `odontologia-reglas-negocio`.

## ADDED Requirements

### Requirement: Anti-solapamiento por profesional
El sistema MUST rechazar la creación o reprogramación de un turno cuyo rango `[inicio, fin)` se solape con otro turno del mismo profesional, garantizado por un constraint de exclusión Postgres (RN-AG-01).

#### Scenario: Solape profesional rechazado a nivel DB
- **WHEN** se insertan dos turnos del mismo profesional con rangos solapados
- **THEN** la base de datos rechaza la segunda inserción por el constraint de exclusión

### Requirement: Anti-solapamiento por sillón
El sistema MUST rechazar la creación o reprogramación de un turno cuyo rango se solape con otro turno en el mismo sillón, aunque sean de distintos profesionales (RN-AG-02).

#### Scenario: Solape de sillón rechazado a nivel DB
- **WHEN** se insertan dos turnos en el mismo sillón con rangos solapados
- **THEN** la base de datos rechaza la segunda inserción por el constraint de exclusión

### Requirement: Cálculo de fin
El sistema MUST calcular `fin = inicio + duracion_prestacion + buffer` al crear el turno; cambiar la duración de una prestación no altera turnos ya creados (RN-AG-03).

#### Scenario: Fin calculado al crear
- **WHEN** se crea un turno para una prestación de 30 minutos con buffer 0
- **THEN** `fin = inicio + 30 minutos`

### Requirement: Bloqueo rechaza turno
El sistema MUST rechazar la creación o reprogramación de un turno dentro de un bloqueo (profesional o sillón), devolviendo el motivo del bloqueo (RN-AG-05).

#### Scenario: Turno dentro de bloqueo
- **WHEN** se intenta crear un turno dentro del rango de un bloqueo
- **THEN** la API responde 409 con el motivo del bloqueo

### Requirement: Sobreturno autorizado
El sistema MUST permitir sobreturno solo si `prestacion.permite_sobreturno = true` y el solicitante tiene rol recepción o superior; el turnero online nunca ofrece sobreturnos (RN-AG-06, RN-G-03).

#### Scenario: Sobreturno sin permiso denegado
- **WHEN** un usuario sin rol recepción o superior intenta crear un sobreturno
- **THEN** la API responde 403

### Requirement: Reprogramación traslada seña
El sistema MUST validar RN-AG-01/02/05 en el destino al reprogramar y trasladar la seña al nuevo turno (RN-AG-07).

#### Scenario: Reprogramación traslada seña
- **WHEN** se reprograma un turno con seña pagada a un nuevo horario válido
- **THEN** la seña queda vinculada al nuevo turno

### Requirement: Cancelación con antelación
El sistema MUST respetar la antelación mínima por prestación (`anticipacion_min_cancel_hs`) al cancelar (RN-AG-08).

#### Scenario: Cancelación tardía
- **WHEN** se cancela un turno con menos antelación que la mínima configurada
- **THEN** el sistema aplica la política de seña configurada

### Requirement: Carrera concurrente
El sistema MUST responder 409 ante dos solicitudes simultáneas por el mismo hueco (RN-AG-01/02 a nivel DB).

#### Scenario: Carrera por hueco
- **WHEN** dos requests concurrentes intentan reservar el mismo hueco
- **THEN** uno tiene éxito y el otro recibe 409

### Requirement: Verificación con PostgreSQL MCP
Los constraints de exclusión y solapamientos MUST verificarse mediante el servidor PostgreSQL MCP (inspección de esquema, constraints, queries de solape).

#### Scenario: Inspección de constraints
- **WHEN** se ejecuta la verificación de migración
- **THEN** el PostgreSQL MCP confirma la existencia de los constraints de exclusión en la tabla `turno`