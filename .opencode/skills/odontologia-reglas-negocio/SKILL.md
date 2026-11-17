---
name: odontologia-reglas-negocio
description: Use when planning, implementing, or reviewing odontological appointment and agenda changes, including slots, overlap, cancellations, rescheduling, deposits, and C-19 PostgreSQL verification. Apply the project's RN-AG rules and identify missing scenarios before coding.
---

# Reglas de agenda odontológica

## Propósito

Aplicar las reglas de agenda del proyecto de forma consistente y convertirlas en escenarios comprobables. Esta skill complementa la base de conocimiento; no inventa decisiones de producto.

## Entradas

- Change o funcionalidad afectada y sus dependencias.
- Reglas relevantes de `knowledge-base/05_reglas_de_negocio.md` y modelo de `knowledge-base/04_modelo_de_datos.md`.
- Implementación, migración y pruebas actuales.
- Para validación de persistencia, conexión PostgreSQL local/de prueba disponible por el MCP.

## Procedimiento

1. Leer `CHANGES.md`, el change/spec activo y las reglas y entidades pertinentes. Revisar `knowledge-base/10_preguntas_abiertas.md` si aparece una decisión de dominio no resuelta.
2. Mapear cada RN-AG/RN-G involucrada a una regla existente, capa responsable y escenario. Marcar explícitamente las reglas sin cobertura o con decisiones ambiguas.
3. Revisar intervalos como `[inicio, fin)`, duración y buffer, bloqueos, profesional, sillón, tenant, estados cancelados y carreras de reserva. No asumir que una prueba con store de memoria valida un constraint de PostgreSQL.
4. Si se necesita comprobar el esquema, conectar el MCP a una base local/de prueba con perfil `ro`. Consultar solo metadatos necesarios (por ejemplo `pg_constraint`); no leer datos de pacientes ni ejecutar DDL/DML desde el MCP. Si el servidor no está disponible, declarar la verificación pendiente.
5. Proponer pruebas que distingan validación de aplicación y persistencia. Para conflictos de integridad, comprobar el resultado observable esperado (por ejemplo 409) y que no queden escrituras parciales.

## Resultado

Presentar: (a) mapa regla→capa→escenario, (b) hallazgos/decisiones abiertas, (c) escenarios de éxito, error y borde, y (d) evidencia MCP separada de las pruebas que todavía deben implementarse. No afirmar que una validación pasó si solo se inspeccionó el esquema.

## Reglas del dominio

- RN-AG-01/02: no hay solapamiento por profesional/sillón; la garantía final vive en PostgreSQL.
- RN-AG-03/04: duración y buffer definen `fin`; los huecos siguen la grilla y descuentan turnos/bloqueos.
- RN-AG-05: bloqueos impiden crear o mover turnos y explican el motivo.
- RN-AG-06 / RN-G-03: sobreturnos requieren prestación y rol habilitados; el turnero público no los ofrece.
- RN-AG-07/08: reprogramar conserva reglas y seña; cancelar respeta la anticipación configurada.

## Referencias

- `knowledge-base/04_modelo_de_datos.md`
- `knowledge-base/05_reglas_de_negocio.md`
- `knowledge-base/10_preguntas_abiertas.md`
- `CHANGES.md` y specs OpenSpec del change activo.
