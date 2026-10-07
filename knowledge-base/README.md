# Turnos Odontología — Base de Conocimiento

Base de conocimiento generada con `kb-creator` (Modo B, interactiva) a partir del informe de Discovery (`../discovery/discovery.md`, 17 sistemas, 2026-10-03) y las decisiones del usuario (SaaS multi-tenant, FastAPI + React, MVP Turnos + clínica, prioridad mantenibilidad).

## Índice de Archivos

| Archivo | Contenido |
|---|---|
| [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito, objetivos por actor, alcance v1.0, fuera de alcance, métricas |
| [02_descripcion_general.md](02_descripcion_general.md) | Stack FastAPI + React + Postgres, arquitectura multi-tenant, integraciones, API |
| [03_actores_y_roles.md](03_actores_y_roles.md) | 6 actores, matriz RBAC, rutas públicas |
| [04_modelo_de_datos.md](04_modelo_de_datos.md) | Dominios, ERD, 12 entidades, seed data |
| [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | Reglas RN-AG/RN-TU/RN-NO/RN-HC/RN-AD/RN-SE + globales |
| [06_funcionalidades.md](06_funcionalidades.md) | 6 épicas, US con criterios y reglas; etiquetas MVP/E2 |
| [07_flujos_principales.md](07_flujos_principales.md) | Reserva con seña, recordatorios, atención, caja, cancelación, exportación |
| [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones, directorios, seguridad, env vars |
| [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | 6 decisiones + 6 supuestos con validación |
| [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | 2 inconsistencias + 14 preguntas (incl. todo lo "No evidenciado") |

## Quick Start para Desarrolladores

1. Entender el dominio → [01](01_vision_y_objetivos.md), [03](03_actores_y_roles.md)
2. Entender los datos → [04](04_modelo_de_datos.md)
3. Entender las reglas → [05](05_reglas_de_negocio.md)
4. Entender la arquitectura → [02](02_descripcion_general.md), [08](08_arquitectura_propuesta.md)
5. Implementar → [07](07_flujos_principales.md), [06](06_funcionalidades.md)
6. Antes de codificar → [10](10_preguntas_abiertas.md)

## Resumen Ejecutivo

SaaS multi-tenant argentino de turnos + clínica dental (FastAPI + React + Postgres) que ataca el vacío verificado del mercado: nadie ofrece WA full-cycle incluido + MP + ARCA + OO.SS. con precio público en pesos. MVP v1.0: agenda con sillones y anti-solapamiento, reserva 24/7 con señas MP, HCE + odontograma FDI y caja básica; fiscal y obra social en etapa 2.
