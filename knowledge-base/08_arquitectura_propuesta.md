# Arquitectura Propuesta

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|---|---|---|
| Monolito modular | `agenda`, `turnos`, `notificaciones`, `clinica`, `cobros`, `admin` | Mantenibilidad con equipo chico; fronteras que permiten extraer servicios luego |
| Multi-tenancy por `tenant_id` | Todas las tablas de dominio | Escalar independiente → clínica sin migraciones (C4.5) |
| Exclusión anti-solapamiento | Tabla `turno` (profesional y sillón) | RN-AG-01/02 garantizadas en base, no solo en código |
| RBAC por middleware | API (rol × recurso) | Matriz de 03, reglas RN-SE-02/03 |
| Jobs + idempotencia | Recordatorios, recall, lista de espera, webhooks MP | Reintentos seguros; `mp_payment_id` único |
| Audit append-only | HCE, evoluciones, eventos sensibles | Trazabilidad clínica y operativa |

## Estructura de directorios

```
proyecto/
├── backend/
│   └── app/
│       ├── domain/            # agenda, clinica, cobros, notificaciones
│       ├── application/       # casos de uso (reservar, confirmar, cobrar, recall)
│       ├── infrastructure/    # db, whatsapp_bsp, mercadopago, smtp, storage
│       ├── api/               # routers FastAPI por recurso
│       └── worker/            # crons y consumidores (recordatorios, lista de espera)
├── frontend/
│   └── src/
│       ├── features/          # agenda, turnero-publico, clinica, caja, reportes
│       ├── shared/            # ui, auth, api-client
│       └── pages/
└── docker-compose.yml         # api + worker + postgres + redis
```

## Seguridad

- Autenticación: JWT access corto + refresh rotado; portal paciente por token firmado de un solo turno.
- Autorización: RBAC (03) + aislamiento `tenant_id` forzado en capa de acceso a datos.
- Validación de input: schemas estrictos (Pydantic v2); turnero público con rate-limit + captcha.
- Secrets management: variables de entorno + vault del deploy; credenciales BSP/MP nunca en frontend.
- Datos sensibles: consentimiento de datos (RN-SE), adjuntos en storage privado con URLs firmadas, backups cifrados.

## Variables de entorno

| Variable | Descripción | Ejemplo | Sensible |
|---|---|---|---|
| `DATABASE_URL` | Conexión PostgreSQL | `postgresql+asyncpg://...` | Y |
| `JWT_SECRET` | Firma de tokens | `***` | Y |
| `WA_BSP_TOKEN` / `WA_PHONE_ID` | WhatsApp Business API | `***` | Y |
| `MP_ACCESS_TOKEN` | Mercado Pago | `***` | Y |
| `SLOT_PUBLIC_BASE_URL` | Base del turnero | `https://turnos.ejemplo.com` | N |
| `REMINDER_T48H_HS` / `REMINDER_T24H_HS` | Ventanas de recordatorio | `48` / `24` | N |
| `DEFAULT_CANCEL_ANTICIP_HS` | Antelación de cancelación | `24` | N |
