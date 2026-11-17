# agenda-db-integrity Specification

## Purpose

Demostrar con PostgreSQL real que las reglas anti-solapamiento de agenda no dependen solamente de las validaciones en memoria o de aplicación.

## ADDED Requirements

### Requirement: Restricciones de agenda verificables en PostgreSQL

El proyecto MUST ofrecer pruebas de integración aisladas que comprueben las restricciones actuales por profesional y sillón, sin aplicar cambios de esquema.

#### Scenario: Turnos contiguos permitidos

- **WHEN** dos turnos del mismo profesional y sillón tienen intervalos contiguos, donde el segundo inicia exactamente al finalizar el primero
- **THEN** ambos se persisten porque `tstzrange(inicio, fin)` usa límites semiabiertos `[)`

#### Scenario: Solapamiento por profesional rechazado

- **WHEN** dos turnos con el mismo profesional se solapan aunque tengan sillones distintos
- **THEN** PostgreSQL rechaza la segunda persistencia y el flujo de aplicación devuelve HTTP 409 sin guardar una fila parcial

#### Scenario: Solapamiento por sillón rechazado

- **WHEN** dos profesionales distintos intentan ocupar el mismo sillón en intervalos solapados
- **THEN** PostgreSQL rechaza la segunda persistencia por `excl_turno_sillon`

#### Scenario: Cancelación libera el rango

- **WHEN** se cancela un turno y luego se crea otro en su rango
- **THEN** la nueva persistencia se permite según el predicado existente `estado <> 'cancelado'`
