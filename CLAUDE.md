# Turnos Odontología — Instrucciones para Agentes

> Este archivo (y su copia `CLAUDE.md`) es lo PRIMERO que todo agente lee al entrar al repo.
> Generado a partir de `knowledge-base/` y `CHANGES.md`. No editar a mano sin re-sincronizar ambos archivos.

---

## Stack Tecnológico

<!-- Tabla desde knowledge-base/02_descripcion_general.md §Stack tecnológico -->

| Capa | Tecnología | Versión |
|------|------------|---------|
| Backend | Python FastAPI | 0.110+ |
| Frontend | React 18 + Vite | 18+ |
| Base de datos | PostgreSQL | 15+ |
| Migraciones | Alembic | 1.13+ |
| Auth | JWT (access + refresh) | — |
| Jobs / recordatorios | Worker asíncrono (Celery + Redis o APScheduler) | — |
| Pagos | Mercado Pago Checkout Pro / API | SDK vigente |
| Mensajería | WhatsApp Business API (BSP oficial) + SMTP | — |
| Deploy inicial | Docker Compose (API + worker + Postgres + Redis) | — |

Detalle completo: [knowledge-base/02_descripcion_general.md](knowledge-base/02_descripcion_general.md)

---

## Base de Conocimiento

La fuente de verdad del dominio vive en `knowledge-base/`. **Leé el archivo relevante ANTES de implementar.**

| Archivo | Cuándo leerlo |
|---------|---------------|
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Entender propósito y alcance |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | Auth, RBAC, permisos |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Entidades, ERD, migraciones |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | Reglas codificadas (RN-XX) |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Historias de usuario por épica |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Flujos E2E |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Patrones, estructura, env vars |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | ⚠️ Inconsistencias a resolver ANTES de codear |

> ⚠️ Resolver las preguntas de prioridad **Alta** de `10_preguntas_abiertas.md` antes de arrancar el primer change.

---

## Skills Disponibles

| Agente | Rol | Skills que carga |
|--------|-----|------------------|
| **Backend Core** | FastAPI / SQLAlchemy / Alembic / RLS | `python-fastapi-development`, `supabase-postgres-best-practices`, `tdd` |
| **Backend Aux** | Integraciones MP/WA, PDFs, reportes | `pdf`, `supabase-postgres-best-practices`, `tdd` |
| **Frontend** | React (turnero 24/7, odontograma, agenda) | `vercel-react-best-practices` |
| **Orquestación** | OPSX / SDD / docs | `active-orchestrator`, `kb-creator`, `roadmap-generator`, `discovery-research`, `agents-md-generator`, `find-skills`, `web-scraper`, `skill-creator` |

Cargá la skill correspondiente al contexto ANTES de escribir código.

> Los compact rules de cada skill los resuelve el orquestador desde `.atl/skill-registry.md` (generado por `skill-registry`; no versionado — no está en el repo). Esta tabla solo mapea skill→rol.

---

## Roadmap de Changes

El plan de implementación completo está en [CHANGES.md](CHANGES.md). Resumen:

- **Total**: 18 changes en 7 fases (Cimientos → Identidad y acceso → Agenda y turnos → Pagos y notificaciones → Clínica → Cierre MVP → Etapa 2).
- **Camino crítico** (8): `C-01 → C-02 → C-03 → C-05 → C-06 → C-10 → C-16 → C-17`.
- **Primer change**: `C-01` (foundation-setup).

**Antes de cualquier `/opsx:propose`**: leé [CHANGES.md](CHANGES.md), identificá las dependencias del change y los archivos de "Leer antes".

---

## Reglas Duras

> Reglas globales ya definidas en `~/.claude/CLAUDE.md` (orquestador, governance, TDD, engram): el proyecto las hereda. Acá viven solo las reglas **específicas de este proyecto** + las universales que el global no cubra.

Son contrato; romperlas es un defecto:

- NUNCA datos reales de pacientes en el repo ni en ejemplos (nombres, DNI, teléfonos, HCE, RX) → usar siempre datos sintéticos marcados como ficticios.
- NUNCA commitear ni pushear sin pedido explícito → commits en español, estilo convencional (`feat:`, `fix:`…), sin co-autoría de IA.
- NUNCA secretos en código (tokens MP/WA, JWT, DB) → variables de entorno según [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md).
- NUNCA tabla de tenant sin RLS + FORCE RLS → aislamiento multi-tenant a nivel DB, no solo `WHERE` en app.
- NUNCA cambio de schema sin migración Alembic numerada → prohibido DDL ad-hoc.
- NUNCA editar ni borrar evoluciones clínicas → corrección como nueva entrada (append-only, RN-HC-01).
- NUNCA endpoint público (turnero, webhooks) sin rate-limit + validación de firma/captcha según corresponda.

---

## Flujo de Trabajo

```
1. Leer la KB relevante (knowledge-base/)        → entender el dominio
2. Identificar el change en CHANGES.md           → respetar dependencias
3. /opsx:propose C-NN-nombre                     → proposal + design + specs + tasks
4. Implementar las tasks (cargando skills)       → respetando las reglas duras
5. /opsx:archive C-NN-nombre + marcar [x]        → cerrar el change
```

Aplicar TODAS las reglas duras en cada paso. Ante conflicto entre la KB y este archivo, las reglas duras prevalecen.
