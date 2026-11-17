# Diseño — C-19

## Enfoque

Usar una base PostgreSQL de prueba independiente, aplicar Alembic hasta `head` y crear únicamente entidades ficticias requeridas por las claves foráneas. Las pruebas se habilitan solo cuando `TEST_DATABASE_URL` apunta explícitamente a una base de prueba; no deben reutilizar `DATABASE_URL` automáticamente.

Usar el `TurnoService` y `DbTurnoStore` de producción para observar el mapeo de `IntegrityError` a `AppError(409)`. Para validar la capa de datos sin depender de prevalidaciones de disponibilidad, incluir también una inserción directa en una transacción de prueba y comprobar el nombre de la constraint que rechaza el solapamiento. La transacción se revierte al finalizar.

## Escenarios y fronteras

- Dos turnos con el mismo profesional y sillón, contiguos en `[inicio, fin)`, se guardan sin conflicto.
- Solapamiento por profesional (aunque cambie el sillón) se rechaza y no deja una fila parcial.
- Solapamiento por sillón entre profesionales distintos se rechaza.
- Luego de cancelar un turno, el rango queda disponible de acuerdo con el `WHERE estado <> 'cancelado'` que ya usan las dos exclusiones.

## Datos y seguridad

Solo fixture sintético y una base descartable. La URL se provee fuera del repositorio. Ningún test lee pacientes reales ni usa credenciales de producción. El MCP se utiliza en modo solo lectura para inspeccionar `pg_constraint`; las pruebas DML corren desde pytest con el usuario de la base de test, nunca a través del MCP.

## Revisión crítica aplicada

La consulta MCP confirmó `excl_turno_profesional` y `excl_turno_sillon` con rangos `tstzrange(inicio, fin)` y exclusión de filas canceladas. La skill apuntó que las pruebas unitarias que usan `MemoryTurnoStore` no ejercitan esos constraints. C-19 cubre esa brecha sin alterar el dominio.
