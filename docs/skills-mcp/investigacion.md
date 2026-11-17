# Investigación: skill propia y servidor MCP

**Proyecto:** Turnos Odontología · **Consulta de fuentes:** 16 de noviembre de 2026

## Necesidad y change

La ficha anterior elegía C-11 y una skill de WhatsApp. C-11 ya está archivado; para esta aplicación se eligió **C-19 `verificacion-postgres-agenda`**, agregado al roadmap como pendiente. C-06 exige exclusión de turnos por profesional y sillón en PostgreSQL; la revisión encontró que los casos de conflicto de `test_c15_turnos.py` usan `MemoryTurnoStore`. Se necesita preparar pruebas de persistencia real, incluyendo contigüidad `[inicio, fin)`.

## Skill creadora y skill del proyecto

- **Creadora:** `skill-creator` del sistema de Codex. Está preinstalada en Codex bajo `~/.codex/skills/.system/skill-creator`; se usó para revisar propósito, activación, procedimiento, salidas y casos de evaluación de la skill propia. Comprobar que existe `SKILL.md`; normalmente no se instala por separado. Si faltara: `$skill-installer install https://github.com/openai/skills/tree/main/skills/.system/skill-creator` y reiniciar Codex.
- **Fuente/compatibilidad:** [OpenAI Skills — skill-creator](https://github.com/openai/skills/tree/main/skills/.system/skill-creator); compatible con Codex. En esta instalación se confirmó su disponibilidad leyendo la skill instalada.
- **Skill propia:** `odontologia-reglas-negocio`, versión para Codex en `.agents/skills/odontologia-reglas-negocio/SKILL.md` y espejo para OpenCode en `.opencode/skills/odontologia-reglas-negocio/SKILL.md`.
- **Propósito y uso:** mapear RN-AG a capas y escenarios al preparar, implementar o revisar agenda/turnos; señalar decisiones abiertas; separar pruebas de memoria, pruebas PostgreSQL y evidencia MCP. Entradas: change, KB, código y esquema. Salida: mapa regla→capa→escenario, brechas y plan de pruebas.
- **Criterios:** no inventar política, no afirmar que memoria verifica PostgreSQL, usar datos ficticios y perfil MCP de solo lectura en una base local/de prueba. Casos de prueba de la skill: `evals/evals.json` dentro de su carpeta.

## Comparación y selección de MCP

| Servidor | Capacidades/compatibilidad | Acceso, requisitos y costo |
|---|---|---|
| **Microsoft PostgreSQL MCP** (elegido) | Perfil de conexión, contexto de esquema y consultas SQL de solo lectura; compatible con Codex por stdio. Sirve para comprobar constraints de C-19. | Node.js/npx y PostgreSQL alcanzable. Perfil `access_mode=ro` más usuario DB con solo `SELECT`; credenciales al keyring, no en config. El paquete no requiere servicio pago; solo podría haber costo si la DB alojada lo tiene. |
| **Filesystem MCP** | Lee/lista y también puede escribir archivos en directorios permitidos; implementación de referencia del MCP. No inspecciona constraints PostgreSQL. | Node.js/npx y allowlist de rutas. En el modo de escritura podría modificar el repo. Sin cuota del paquete; costos solo por infraestructura. |

Se seleccionó PostgreSQL por la necesidad de C-19 de inspeccionar `pg_constraint`. No se instaló Filesystem: sus funciones no cubren esa consulta y amplían acceso local sin aportar al change. La comparación se basa en las capacidades y guías oficiales enlazadas al final.

## Configuración y comprobación

Codex: `codex mcp add postgres -- npx -y @microsoft/postgres-mcp run`; confirmar con `codex mcp list` y reiniciar Codex. Crear un perfil separado a una DB de prueba con `npx -y @microsoft/postgres-mcp connection add <perfil> "host=127.0.0.1 port=5432 user=<rol_ro> dbname=turnos" --access-mode ro`; guardar la contraseña con `connection set-password <perfil>` (entrada oculta). Instrucciones, grants y diagnóstico están en [README.md](../../README.md#configuración-del-servidor-mcp-postgresql).

En una sesión con MCP disponible: `postgres_mcp_list_connection_profiles` → `postgres_mcp_connect` → `postgres_mcp_query`; consultar únicamente constraints y desconectar. La evidencia ejecutada para esta preparación está en `docs/skills-mcp/evidencias/mcp-postgres-constraints.json`. Se migró una DB temporal vacía y se usó un rol de solo lectura.

## Archivos previstos/actualizados

Skill Codex y espejo OpenCode; `.atl/skill-registry.md`; `AGENTS.md`/`CLAUDE.md`; `README.md`; `CHANGES.md`; artefactos SDD pendientes de C-19; informe de aplicación y evidencia en `docs/skills-mcp/`.

## Fuentes oficiales (consultadas 2026-11-16)

- Microsoft, README y herramientas: https://github.com/microsoft/postgres-mcp/blob/main/README.md
- Microsoft, configuración, seguridad y perfiles de solo lectura: https://github.com/microsoft/postgres-mcp/blob/main/USAGE.md
- OpenAI, skill-creator: https://github.com/openai/skills/tree/main/skills/.system/skill-creator
- Model Context Protocol, Filesystem: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
