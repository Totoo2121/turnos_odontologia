# Design

## Context

El esquema persiste turnos, señas MP y movimientos append-only de cuenta corriente. No existe un calendario de jornadas laborales por profesional, por lo que no hay denominador fiable para porcentaje de ocupación.

## Goals / Non-Goals

**Goals:** reportes tenant-scoped y acotados por fecha; alcance total para propietario, operativo para recepción/asistente y propio para odontólogo; separar señas y créditos de deuda actual de planes.

**Non-Goals:** configurar jornadas, cambiar el cierre de caja de C-15, exportar archivos, emitir reportes fiscales.

## Decisions

- Exponer `/api/reportes/ocupacion`, `/ausentismo` y `/recaudacion`, con fechas inclusivas y rango máximo de 367 días.
- Ocupación devuelve turnos y minutos ocupados; no inventa capacidad disponible ni porcentaje.
- Ausentismo es `ausentes / todos los turnos del período`; cancelaciones se informan separadas.
- Recaudación trata señas acreditadas y créditos de cuenta como cobros; deuda neta de planes es un saldo actual fuera del rango temporal.
- Pagos y deuda que no pueden atribuirse a un profesional no se exponen en el alcance propio.
- El frontend carga reportes independientes en paralelo y oculta recaudación a recepción/asistente.

## Risks / Trade-offs

Sin jornadas no se puede comparar ocupación contra capacidad. No se asignan cobros manuales a profesionales porque el ledger no guarda esa atribución.
