# Design

## Context

Ver proposal.md — Why. El frontend ya tiene app shell (C-04) con rutas, guards por rol y `shared/ui` (tabla, modal, formulario, toast) y api-client con refresh JWT. Los endpoints de agenda y turnos ya existen en backend (C-05/C-06). Este change es puramente frontend; no requiere migración.

## Goals / Non-Goals

**Goals:**
- Feature `features/agenda` con vistas día/semana por profesional y por sillón.
- Consumo de endpoints existentes con manejo de errores (solape/bloqueo → mensaje + motivo).
- Acciones de ciclo de vida y sobreturno con confirmación de rol.
- Tests de render por rol, creación válida/inválida y flujo de estados.

**Non-Goals:**
- No se toca backend ni migraciones.
- No se implementa turnero público (C-08) ni clínica/caja (C-15).
- No se implementa arrastre drag-and-drop (opcional, fuera de MVP si complica).

## Decisions

- **Calendario**: usar componente de grilla propio sobre `shared/ui` (tabla) en lugar de librería externa, para mantener control de estados y evitar dependencia pesada. Alternativa: `react-big-calendar` — descartado por peso y acoplamiento al modelo de datos.
- **Estado local**: Zustand store por feature (`useAgendaStore`) para filtros (vista, profesional, sillón, fecha) y cache de turnos; api-client para llamadas.
- **Manejo de errores**: mapear códigos 409 (solape/bloqueo) a toast con motivo; 403 a mensaje de permiso.
- **Sobreturno**: modal de confirmación con checkbox de autorización; solo visible si rol autorizado.

## Risks / Trade-offs

- [Rendimiento de vista semana con muchos profesionales] → paginación/virtualización si se detecta; MVP con lista simple.
- [Desfase de estado tras acción concurrente] → re-fetch de agenda tras cada mutación.
- [Accesibilidad del calendario] → teclado básico; mejora en etapa 2.

## Migration Plan

No aplica (solo frontend). Deploy estándar de build Vite.

## Open Questions

Ninguna que bloquee; refinamiento de UX queda para implementación.
