# C-19 — Verificación PostgreSQL de reglas de agenda

## Problema

C-06 define exclusión por profesional y sillón en PostgreSQL. La suite actual prueba varios conflictos a través de `MemoryTurnoStore`; eso no demuestra que las restricciones reales de PostgreSQL rechacen el solapamiento ni que el límite entre turnos contiguos se comporte como intervalo semiabierto.

## Resultado

Agregar pruebas de integración optativas sobre PostgreSQL real para comprobar los constraints existentes y el mapeo del conflicto de persistencia a HTTP 409. No se agregan tablas ni cambia la lógica funcional.

## Alcance

- Fixture aislado, migrado hasta `head`, con datos sintéticos de tenant, profesional, sillón y prestación.
- Pruebas de intervalos contiguos válidos, solapamiento por profesional y solapamiento por sillón entre profesionales distintos.
- Comprobación de que cancelar libera el rango según el predicado existente de los constraints.
- Guía para ejecutar la suite con una URL explícita de base de prueba.

## Fuera de alcance

- Cambiar RN-AG-01/02, la política de cancelación o constraints existentes.
- Ejecutar las pruebas contra producción o cargar datos reales.
- Agregar horarios laborales o porcentaje de capacidad.

## Dependencias

C-06 (`turnos-antissolapamiento`) y C-15 (API de ciclo de vida), ambos archivados.

## Verificación

Los escenarios nuevos deben ejecutarse contra PostgreSQL; las pruebas existentes de memoria siguen siendo pruebas unitarias, no sustitutos de esta verificación.
