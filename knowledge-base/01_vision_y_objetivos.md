# Visión y Objetivos

## Propósito del sistema

Un SaaS multi-tenant de gestión de turnos y clínica odontológica para el mercado argentino que cierra el "combo argentino": agenda + WhatsApp oficial full-cycle + señas con Mercado Pago + HCE/odontograma + obras sociales y factura electrónica ARCA, con precio público en pesos.

Contexto: los consultorios y clínicas argentinas gestionan turnos por WhatsApp/papel o con software de pricing opaco, WhatsApp a medias y sin combo MP+ARCA+OOSS integrado, lo que genera ausencias, huecos perdidos y fricción administrativa (ver `../discovery/discovery.md`, problema validado contra 17 sistemas relevados el 2026-10-03).

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|---|---|---|
| Odontólogo | Atender con HCE + odontograma + plan de tratamiento en una sola pantalla | Ver su agenda del día, firmar consentimientos, adjuntar RX/fotos |
| Recepcionista / administrativo | Mantener la agenda del día ocupada y confirmada sin llamadas | Confirmar turnos, reasignar huecos, cobrar señas y saldos |
| Dueño / gerente de clínica | Rentabilidad y trazabilidad: ocupación, ausentismo, recaudación, liquidaciones OS | Reportes por profesional/sede, auditoría, exportación de datos |
| Paciente | Reservar/cancelar/reprogramar online sin llamar, 24/7 | Confirmar por WhatsApp, pagar seña, ver su tratamiento y próximos controles |

## Alcance v1.0 (MVP: Turnos + clínica)

- Agenda multi-profesional con sillones/boxes, duraciones variables por prestación, bloqueos y prevención de solapamientos.
- Reserva online 24/7 por enlace compartible + cancelación/reprogramación por el paciente + lista de espera con auto-relleno.
- Recordatorios y confirmaciones automáticas por WhatsApp (API oficial) + email.
- HCE odontológica + odontograma FDI + presupuestos vinculados (presupuesto aceptado → plan de tratamiento → deuda en cuenta corriente).
- Caja y cobros: señas con Mercado Pago vinculadas al turno, cobro de saldos, reportes básicos.
- Roles y permisos, consentimientos firmados, imágenes/RX adjuntas, exportación total de datos.

## Fuera de alcance (etapas posteriores)

- Facturación electrónica ARCA y liquidaciones de obras sociales/prepagas (etapa 2 — el diferencial de Bilog/DentalCore/ClinIA que exige integración fiscal y nomencladores).
- Recetario electrónico ReNaPDiS (moat regulatorio de ClinIA #248; se evalúa en etapa 2).
- CDSS / IA diagnóstica (17 motores tipo DentalCore, Detect AI/VideaHealth) — IA práctica sí entra (notas por voz, no-show scoring), diagnóstico asistido no.
- Periodontograma avanzado, multi-sucursal full, marketplace de captación + campañas, API pública, integraciones con radiología/laboratorio.
- Apps móviles nativas (el MVP es web responsive + PWA evaluable).

## Métricas de éxito

- Ausentismo < 10% en consultorios activos (línea base: el mercado declara -35% con recordatorios inteligentes — Dentalink).
- Ocupación de agenda > 80% con auto-relleno de huecos.
- Tiempo de reserva online < 2 minutos sin intervención del consultorio.
- Pricing público en pesos y exportación de datos garantizada como palancas de adopción (antídoto al vacío de transparencia detectado).
