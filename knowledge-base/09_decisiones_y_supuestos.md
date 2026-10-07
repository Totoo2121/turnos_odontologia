# Decisiones y Supuestos

## Decisiones documentadas

### DD-01 — SaaS multi-tenant web (no app nativa, no single-tenant)
**Decisión**: web responsive + API propia, aislamiento por `tenant_id` desde el día 1.
**Contexto**: usuarios Discovery van de independiente a cadena; el mercado muestra que migrar de sistema (DentiDesk ofrece migración) es fricción.
**Alternativas consideradas**: single-tenant simple; apps móviles nativas; PWA offline-first ya.
**Justificación**: escala sin migraciones (oportunidad C4.5); el panel y el turnero web cubren el MVP; offline-first queda como diferencial evaluable luego (C4.7).
**Trade-offs aceptados**: más disciplina en cada query (tenant scoping); sin offline real en v1.0.

### DD-02 — MVP "Turnos + clínica" (OO.SS./ARCA en etapa 2)
**Decisión**: v1.0 = agenda + turnos 24/7 + WA + MP + HCE/odontograma + caja básica; FE ARCA y liquidaciones OS en etapa 2.
**Contexto**: Discovery C1 marca el estándar mínimo; C4.1 marca el combo completo como norte.
**Alternativas consideradas**: solo turnos (más rápido, sin clínica real — replicaría el techo de AgendaPro); full argentino ya (máximo riesgo fiscal).
**Justificación**: respuesta del usuario (P2); la clínica es lo que separa un PMS dental de un agendador genérico.
**Trade-offs aceptados**: sin diferencial fiscal en v1.0; el esquema ya reserva los campos (RN-AD-05).

### DD-03 — Python FastAPI + React + PostgreSQL
**Decisión**: stack elegido por el usuario (FastAPI + React); PostgreSQL como base.
**Contexto**: P4 respondió stack sin DB.
**Alternativas consideradas**: MySQL; SQLite (descartado por multi-tenant concurrente).
**Justificación**: JSONB para odontograma, exclusiones anti-solapamiento, RLS futura; ecosistema UTN.
**Trade-offs aceptados**: **Suposición** — PostgreSQL no fue confirmado explícitamente; ver SU-06.

### DD-04 — WhatsApp por Business API oficial, incluido (no add-on)
**Decisión**: WA full-cycle incluido en el producto, nunca add-on en USD.
**Contexto**: vacío C3.2 — el mercado cobra WA aparte (FLAP add-on, Bilog/iAngela en USD) o lo hace manual (DentiDesk).
**Justificación**: es el diferencial de adopción #1 en Argentina.
**Trade-offs aceptados**: costo BSP por conversación; hay que diseñar plantillas y pricing que lo absorba.

### DD-05 — Mercado Pago para señas en el MVP
**Decisión**: señas vinculadas al turno con MP (patrón FLAP verificado).
**Contexto**: ningún relevado local combina MP + ARCA + OO.SS. verificado (vacío C3.3).
**Justificación**: reduce ausencias y da flujo de caja; el webhook con idempotencia lo hace robusto.
**Trade-offs aceptados**: MP no resuelve facturación; ARCA queda para E2.

### DD-06 — Transparencia como estrategia (pricing público + exportación garantizada)
**Decisión**: precio público en pesos y exportación total de datos como features, no como promesas.
**Contexto**: vacíos C3.1 (pricing opaco) y C3.4 (exportación opaca) — antídoto C4.2.
**Justificación**: es barato de implementar y caro de copiar para incumbentes opacos.

## Supuestos inferidos

### SU-01 — Consultorios dispuestos a migrar desde WhatsApp/papel o Bilog instalado
**Supuesto**: existe voluntad de cambio si el combo es superior.
**Origen**: riesgo declarado en Discovery (state.discovery.riesgos).
**Riesgo si es falso**: sin adopción no hay producto.
**Cómo validar**: demos a 5 competidores prioritarios (D1) + pilotos con 2-3 consultorios.

### SU-02 — Puntajes 0–5 de la matriz como guía, no como benchmark medido
**Supuesto**: el ranking orienta pero no prueba superioridad.
**Origen**: Discovery B (juicio analítico sobre evidencia pública).
**Riesgo si es falso**: priorizar mal el MVP.
**Cómo validar**: demos D1 antes del roadmap.

### SU-03 — Precios ARS de Dentatools/DenPro vigentes
**Supuesto**: $15.000–$30.000 (Dentatools) y $19.900/$29.900 (DenPro) siguen vigentes.
**Origen**: Discovery A (precios publicados, fecha 2026-10-03).
**Riesgo si es falso**: posicionamiento de precio errado.
**Cómo validar**: re-chequear antes de fijar precio propio.

### SU-04 — Alcance regulatorio argentino validable después
**Supuesto**: HCE, consentimientos y firma digital del diseño alcanzan para v1.0 sin matrícula regulatoria especial.
**Origen**: Discovery (adecuación AR declarada por vendors, sin validación legal).
**Riesgo si es falso**: rediseño de compliance.
**Cómo validar**: consulta legal antes del sprint de clínica.

### SU-05 — Pacientes aceptan confirmar por WhatsApp y pagar seña online
**Supuesto**: el loop WA + MP no genera abandono.
**Origen**: FLAP (MP nativo) y DentalCore (bot 9 flujos) lo validan parcialmente.
**Riesgo si es falso**: caída de conversión del turnero.
**Cómo validar**: medir conversión y no-show en piloto.

### SU-06 — PostgreSQL como base de datos
**Supuesto**: ver DD-03 — no confirmado por el usuario.
**Origen**: inferencia técnica (P4 solo dijo FastAPI + React).
**Riesgo si es falso**: cambio de motor al inicio del build.
**Cómo validar**: confirmar en la revisión de esta KB (pregunta abierta PRI-09).
