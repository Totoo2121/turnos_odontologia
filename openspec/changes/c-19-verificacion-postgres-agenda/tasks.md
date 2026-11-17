# Tasks

## 1. Fixture PostgreSQL de prueba

- [ ] 1.1 Agregar fixture de integración habilitado solo por `TEST_DATABASE_URL`; verificar que rechaza URL ausente o de producción y que las migraciones crean un tenant de prueba aislado.
- [ ] 1.2 Preparar entidades de agenda ficticias y limpieza transaccional; verificar que ninguna prueba usa datos reales ni deja filas persistentes.

## 2. Reglas de integridad

- [ ] 2.1 Verificar que dos turnos contiguos del mismo profesional y sillón se persisten; ejecutar contra PostgreSQL real.
- [ ] 2.2 Verificar solapamiento por profesional y mapeo de `IntegrityError` a 409 sin fila parcial; ejecutar caso por repositorio y servicio.
- [ ] 2.3 Verificar solapamiento de sillón entre profesionales distintos y liberación del rango al cancelar; comprobar ambas constraints reales.

## 3. Documentación e integración

- [ ] 3.1 Documentar comando, variables de prueba y límites de seguridad; verificar reproducibilidad desde una base vacía.
- [ ] 3.2 Ejecutar pruebas de C-19 y suites existentes de agenda; comprobar los cuatro escenarios de la spec contra PostgreSQL.
