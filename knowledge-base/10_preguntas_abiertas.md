# Preguntas Abiertas

Todo lo que en Discovery figura como "No evidenciado" se traslada acá como pregunta o supuesto — no se inventa ningún dato.

## Inconsistencias detectadas

### IN-01 — Líder del ranking: DentalCore 4.00 vs. Bilog como líder real
**Documento A dice**: matriz B ordena DentalCore (4.00) primero.
**Documento B dice**: lectura ejecutiva aclara que el líder local real es Bilog (trayectoria + OO.SS./FE verificados).
**Impacto**: priorizar el rival equivocado para las demos.
**Resolución propuesta**: demos a ambos primeros (Bilog D1-1, DentalCore D1-2) y recién después fijar posicionamiento.

### IN-02 — Precios ARS publicados vs. resto opaco
**Documento A dice**: Dentatools/DenPro publican en pesos; Bilog, DentalCore, FLAP y ClinIA no publican (a cotización).
**Documento B dice**: la estrategia propia es pricing público (DD-06).
**Impacto**: sin referencia de precio del incumbente, el propio pricing se fija a ciegas.
**Resolución propuesta**: pedir cotización en las demos D1 como tarea de inteligencia comercial.

## Preguntas abiertas (priorizadas)

| Prioridad | Pregunta | Bloquea | Decisor |
|---|---|---|---|
| Alta | ¿Existen FeatherDent / SB Clinics / Oralsurgery o se descartan? En Discovery figuran como **No evidenciado / no verificado** (sin sitio oficial hallado) | Roadmap (¿son competidores?) | Product Owner |
| Alta | ¿Precios reales de Bilog / DentalCore / FLAP / ClinIA? Todos figuran como **No evidenciado** (a cotización) | Pricing propio y matriz | Product Owner |
| Alta | ¿Mercado Pago en Bilog? Figura como **No evidenciado**; si lo tuviera, el vacío C3.3 se achica | Alcance de cobros MVP | Equipo (demo D1-1) |
| Alta | ¿WhatsApp automático real en DentiDesk y alcance del de DentalCore fuera de planes altos? Detalle **No evidenciado** en planes base | Diseño de automatización | Equipo (demos) |
| Alta | ¿Política de exportación de datos, backups y trazabilidad de vendors AR? Casi todo **No evidenciado** en lo público | Diferencial DD-06 (hay que superarlo de verdad) | Tech Lead |
| Alta | ¿Alcance regulatorio v1.0 (HCE, consentimientos, firma, Ley 25.326)? Adecuación AR declarada por vendors pero **No evidenciado** a fondo | Sprint de clínica | Asesor legal |
| Media | ¿Multi-sucursal desde el día 1 o un solo consultorio? (pregunta abierta heredada de Discovery) | Modelo de datos sucursal | Product Owner |
| Media | ¿Login de paciente vs. reserva sin registro? (pregunta heredada; RN-TU-01 propone sin cuenta) | UX del turnero | Product Owner |
| Media | ¿Confirmar PostgreSQL como DB (SU-06)? P4 solo definió FastAPI + React | Sprint 1 backend | Tech Lead |
| Media | ¿Google Calendar bidireccional en MVP o posterior? Para la mayoría es **No evidenciado** como integración real | Integraciones | Equipo |
| Media | ¿Vigencia de precios ARS publicados (Dentatools/DenPro)? Pueden haber cambiado desde 2026-10-03 | Pricing | Product Owner |
| Baja | ¿Cantidad real de clientes de cada vendor? Solo claims autodeclarados (**No evidenciado** independiente) | Go-to-market | Product Owner |
| Baja | ¿Periodontograma en MVP o E2? Solo Clinic Cloud lo muestra sólido; resto **No evidenciado**/parcial | Alcance clínico | Odontólogo asesor |
| Baja | ¿API pública y marketplace en qué etapa? (US-052/053 son E2 por defecto) | Roadmap | Product Owner |

## Origen de cada "No evidenciado"

Todos provienen de `../discovery/discovery.md` (tablas A, sección C3 y nota de nombres no verificados), relevamiento del 2026-10-03 con regla de evidencia: lo no demostrado públicamente se consigna como "No evidenciado".
