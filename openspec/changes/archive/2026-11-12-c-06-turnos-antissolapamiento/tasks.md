# Tasks

## 1. Modelo y migración

- [x] 1.1 Crear modelo `Turno` (paciente, profesional, sillón, prestación, inicio, fin, estado, origen, token_portal, sobreturno, tenant_id) y migración 004 con tabla `turno`, constraints de exclusión GIST y índices; verificar migración aplica y rollback funciona.
- [x] 1.2 Habilitar extensión `btree_gist` en la migración; verificar con PostgreSQL MCP que los constraints de exclusión existen en `turno`.

## 2. Anti-solapamiento y bloqueos

- [x] 2.1 Implementar repositorio `TurnoRepository` con inserción que capture IntegrityError y mapee a 409; verificar test de solape profesional rechazado a nivel DB.
- [x] 2.2 Implementar validación de bloqueo (RN-AG-05) con motivo; verificar test bloqueo rechaza con motivo.
- [x] 2.3 Implementar cálculo `fin = inicio + duracion + buffer` (RN-AG-03); verificar test de fin calculado.

## 3. Endpoints de ciclo de vida

- [x] 3.1 `POST /turnos` y `PATCH /turnos/{id}/estado`; verificar creación válida y transición de estados.
- [x] 3.2 `POST /turnos/{id}/reprogramar` (valida RN-AG-01/02/05, traslada seña); verificar test reprogramación traslada seña.
- [x] 3.3 `POST /turnos/{id}/cancelar` con antelación mínima (RN-AG-08); verificar test cancelación tardía.
- [x] 3.4 `POST /turnos/sobreturno` (permite_sobreturno + rol recepción o superior, RN-AG-06/RN-G-03); verificar sobreturno sin permiso denegado 403.
- [x] 3.5 `GET /turnos/agenda?vista=dia|semana`; verificar render por profesional/sillón.

## 4. Concurrencia y verificación DB

- [x] 4.1 Test de carrera concurrente por mismo hueco → 409; verificar con test de concurrencia.
- [x] 4.2 Verificación final de constraints y solapamientos mediante PostgreSQL MCP (inspección de esquema, constraints de exclusión, queries de solape); documentar resultados.

## 5. Integración

- [x] 5.1 Ejecutar suite completa de C-06 y verificar todos los tests pasan.