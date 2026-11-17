# turnos-agenda Specification

## Purpose
Define el ciclo de vida de turnos con anti-solapamiento garantizado a nivel de base de datos, sobreturnos y reprogramación/cancelación, aplicando las reglas RN-AG-01..08 y RN-G-03 del skill `odontologia-reglas-negocio`.

## Requirements

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

### Requirement: API de creación de turno

El sistema SHALL exponer `POST /api/turnos` para propietario y recepción, calcular
`fin` en el servidor a partir de `prestacion.duracion_min + buffer`, validar que
profesional, sillón, prestación y paciente pertenezcan al tenant, y rechazar
solapamientos o bloqueos sin crear el turno.

#### Scenario: Turno creado con fin calculado

- **WHEN** recepción crea un turno de una prestación ficticia de 30 minutos con buffer 10
- **THEN** el turno se persiste en estado `pendiente` con `fin = inicio + 40 minutos`

#### Scenario: Solape rechazado

- **WHEN** el horario pedido se solapa con otro turno del profesional o del sillón
- **THEN** el sistema responde 409 y no crea el turno

#### Scenario: Bloqueo rechazado con motivo

- **WHEN** el horario pedido cae dentro de un bloqueo
- **THEN** el sistema responde 409 con el motivo del bloqueo y no crea el turno

#### Scenario: Referencia de otro tenant

- **WHEN** el pedido referencia un profesional, sillón, prestación o paciente de otro tenant
- **THEN** el sistema responde 422 o 404 y no crea el turno

#### Scenario: Rol sin permiso de creación

- **WHEN** un odontólogo o asistente intenta crear un turno
- **THEN** el sistema responde 403

### Requirement: API de cambio de estado del turno

El sistema SHALL exponer `PATCH /api/turnos/{id}/estado` para propietario,
recepción y odontólogo, permitiendo solo transiciones válidas, tratando `atendido`,
`ausente` y `cancelado` como estados finales y respondiendo 409 ante una transición
inválida.

#### Scenario: Cierre como atendido

- **WHEN** recepción o el odontólogo marca un turno `pendiente` o `confirmado` como `atendido`
- **THEN** el turno queda en `atendido` y refleja la fecha de actualización

#### Scenario: Transición inválida

- **WHEN** se intenta mover un turno `cancelado` a `atendido`
- **THEN** el sistema responde 409 y conserva el estado `cancelado`

#### Scenario: Repetición del mismo estado

- **WHEN** se envía el estado que el turno ya tiene
- **THEN** el sistema responde 200 con el turno sin cambios

#### Scenario: Turno de otro tenant

- **WHEN** se intenta cambiar el estado de un turno de otro tenant
- **THEN** el sistema responde 404 sin revelar su existencia

#### Scenario: Asistente sin permiso de cambio

- **WHEN** un asistente intenta cambiar el estado de un turno
- **THEN** el sistema responde 403

### Requirement: API de cancelación con política de seña

El sistema SHALL exponer `POST /api/turnos/{id}/cancelar`, liberar el hueco,
respetar la antelación mínima de la prestación e informar si la cancelación fue
tardía y si la seña se pierde según la política vigente.

#### Scenario: Cancelación en término

- **WHEN** recepción cancela un turno con antelación mayor o igual a la mínima de la prestación
- **THEN** el turno queda `cancelado` y la respuesta indica que la seña no se pierde

#### Scenario: Cancelación tardía

- **WHEN** se cancela un turno con menos antelación que la mínima
- **THEN** el turno queda `cancelado` y la respuesta indica cancelación tardía con la política de seña aplicada

#### Scenario: Cancelación repetida

- **WHEN** se vuelve a cancelar un turno ya cancelado
- **THEN** el sistema responde 200 con el mismo turno sin duplicar efectos

#### Scenario: Turno inexistente o ajeno

- **WHEN** se intenta cancelar un turno que no existe en el tenant de la sesión
- **THEN** el sistema responde 404