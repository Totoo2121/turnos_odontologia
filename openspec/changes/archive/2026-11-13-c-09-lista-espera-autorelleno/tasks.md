# Tasks

## 1. Modelo y migración

- [x] 1.1 Crear modelo `ListaEspera` con campos y relaciones; verificar import en app.
- [x] 1.2 Crear migración Alembic 005 `lista_espera` con RLS + FORCE RLS; verificar `alembic upgrade head`.

## 2. Endpoints

- [x] 2.1 Implementar `POST /lista-espera` y `GET /lista-espera`; verificar tests de alta/consulta.
- [x] 2.2 Implementar aceptación de oferta → turno normal; verificar tests de conversión.

## 3. Worker de oferta/vencimiento

- [x] 3.1 Implementar job de oferta al liberar hueco; verificar test orden por antigüedad/preferencia.
- [x] 3.2 Implementar job de vencimiento y rotación; verificar test vencimiento rota al siguiente.

## 4. Integración y tests

- [x] 4.1 Integrar disparo de oferta en cancelación de turno (C-06); verificar flujo E2E.
- [x] 4.2 Tests anti-solapamiento en conversión (RN-AG-01/02/05); verificar suite verde.