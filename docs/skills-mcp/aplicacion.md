# Informe de aplicación — skill y MCP

**Proyecto:** Turnos Odontología · **Fecha:** 16 de noviembre de 2026

## Cambio preparado

La ficha original apuntaba a C-11, pero C-11 ya está archivado. Se agregó **C-19 `verificacion-postgres-agenda`** como change pendiente, con proposal, design, spec y tasks. Cubre pruebas contra constraints existentes, no cambia el esquema ni afirma haber completado la funcionalidad. Ver [`CHANGES.md`](../../CHANGES.md) y [`openspec/changes/c-19-verificacion-postgres-agenda/`](../../openspec/changes/c-19-verificacion-postgres-agenda/).

## Uso de la skill propia

- **Skill creadora aplicada:** la `skill-creator` del sistema de Codex guió el ajuste de activación, procedimiento, salida y evals. Fuente: https://github.com/openai/skills/tree/main/skills/.system/skill-creator.
- **Solicitud de trabajo aplicada:** “Aplicá `odontologia-reglas-negocio` para revisar la cobertura de RN-AG en C-06 y preparar un change pendiente que compruebe en PostgreSQL los conflictos y los casos de borde”.
- **Resultado:** se mapearon RN-AG-01/02 a las exclusiones por profesional y sillón, se confirmó en código que los conflictos de `test_c15_turnos.py` se prueban con `MemoryTurnoStore`, y se definieron en C-19 los casos contiguos, solapamiento por profesional, sillón compartido y cancelación. La skill quedó descubrible en `.agents/skills` para Codex, espejada para OpenCode, registrada en `.atl/skill-registry.md` y referenciada desde AGENTS/CLAUDE.
- **Revisión crítica:** C-06 tasks marcaba verificación vía PostgreSQL MCP, pero el resultado archivado no incluye un registro reproducible de esa consulta; los tests unitarios de memoria no prueban los constraints de la DB. La regla fuente RN-AG-01/02 y la migración C-06 justifican cubrir la brecha en C-19 sin cambiar política.
- **Evaluación:** se agregaron tres prompts a `evals/evals.json` de la skill para el flujo normal, el límite contiguo y la afirmación incorrecta de que memoria prueba la DB. Esta revisión fue manual; no se ejecutó benchmark comparativo independiente.

## Uso real del MCP

- **Servidor:** Microsoft `@microsoft/postgres-mcp`, v0.3.0; Codex lo tiene registrado. Se creó en el keyring/config local el perfil `tpi-local`, con `access_mode=ro` y un rol PostgreSQL con permisos de lectura.
- **Entorno:** PostgreSQL local temporal, base vacía `turnos`, migrada a `f18a1b2c3d4e5` (head). No se usó `.env`, datos de pacientes ni credenciales de producción.
- **Herramientas ejecutadas:** `postgres_mcp_list_connection_profiles`, `postgres_mcp_connect` y `postgres_mcp_query`; desconexión al terminar.
- **Consulta:** `SELECT conname, contype, pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid = 'public.turno'::regclass AND contype = 'x' ORDER BY conname`.
- **Resultado:** PostgreSQL devolvió `excl_turno_profesional` y `excl_turno_sillon`, ambos con `EXCLUDE USING gist` sobre `tstzrange(inicio, fin)`, excluyendo estado `cancelado`. Resultado sin datos de filas guardado en [`evidencias/mcp-postgres-constraints.json`](evidencias/mcp-postgres-constraints.json).
- **Límite de permisos comprobado con el MCP:** `current_user=tpi_mcp_ro`, `SELECT=True`, `INSERT=False` sobre `public.turno`.
- **Aporte:** confirmó los nombres y definiciones que C-19 verificará. La consulta de esquema no demuestra todavía el resultado de INSERT solapado; eso queda como tarea de integración en el change pendiente.

## Archivos cambiados y motivo

- `.agents/skills/odontologia-reglas-negocio/`: ruta descubrible por Codex y evals.
- `.opencode/skills/odontologia-reglas-negocio/SKILL.md`: espejo para mantener soporte de OpenCode.
- `.atl/skill-registry.md`, `AGENTS.md`, `CLAUDE.md`: registrar y activar la skill del proyecto.
- `CHANGES.md`, `openspec/changes/c-19-verificacion-postgres-agenda/`: nuevo change pendiente preparado con cuatro escenarios y tareas de verificación.
- `README.md`: configuración correcta y reproducible del servidor MCP, sin secretos.
- `docs/skills-mcp/investigacion.md`, este informe y `evidencias/`: corregir la selección y preservar decisión, uso real y resultado.

## Límites pendientes

C-19 no se implementó ni archivó. La base temporal corrió PostgreSQL 18; la verificación de comportamiento debe ejecutarse también en la versión objetivo de Docker (PostgreSQL 15). `codex mcp list` confirma el registro habilitado, pero el conjunto de herramientas MCP no se cargó dentro de esta sesión; la llamada real se verificó mediante el protocolo MCP stdio. Reiniciar Codex para mostrar esas herramientas en la siguiente sesión. La entrega del video y del archivo TXT con los enlaces se realiza en el campus. Según `documento-tpi.pdf`, el video no debe superar los 10 minutos. Los nombres de integrantes y enlaces deben completarse con los datos reales del equipo antes de entregar. C-19 continúa pendiente de implementación.
