# Tasks

## 1. Estructura y store

- [x] 1.1 Crear `frontend/src/features/agenda/` con componentes, store Zustand y api hooks; verificar que `tsc` compila sin errores.
- [x] 1.2 Registrar rutas de agenda en app shell con guard por rol; verificar navegación por rol recepción/odontólogo.

## 2. Vistas día/semana

- [x] 2.1 Implementar grilla día por profesional y por sillón con estados y cobro visible; verificar render con datos seed.
- [x] 2.2 Implementar vista semana con navegación de fechas; verificar cambio de vista y carga de turnos.

## 3. Creación de turno

- [x] 3.1 Implementar modal de creación sobre hueco con validación; verificar creación en hueco válido crea turno.
- [x] 3.2 Manejar rechazo 409 solape/bloqueo con toast y motivo; verificar mensaje visible en hueco inválido.

## 4. Ciclo de estados y sobreturno

- [x] 4.1 Implementar acciones confirmar/en-sala/atender/cancelar/reprogramar/ausente; verificar flujo de estados en UI.
- [x] 4.2 Implementar sobreturno con modal de confirmación y guard de rol; verificar marcado visible y denegación por rol.

## 5. Tests

- [x] 5.1 Tests de render por rol recepción y flujo de estados; verificar `npm test` verde.
- [x] 5.2 Tests de creación en hueco válido/inválido; verificar cobertura de escenarios de spec.
