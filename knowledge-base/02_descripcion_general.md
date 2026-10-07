# Descripción General

## Stack tecnológico

| Capa | Tecnologías | Versión mínima |
|---|---|---|
| Backend | Python FastAPI | 0.110+ |
| Frontend | React (Vite) | React 18+ |
| Base de datos | PostgreSQL | 15+ |
| Migraciones | Alembic | 1.13+ |
| Auth | JWT (access + refresh) | — |
| Jobs / recordatorios | Worker asíncrono (Celery + Redis o APScheduler según escala inicial) | — |
| Pagos | Mercado Pago Checkout Pro / API | SDK vigente |
| Mensajería | WhatsApp Business API (proveedor BSP oficial) + SMTP email | — |
| Deploy inicial | Docker Compose (API + worker + Postgres + Redis) | — |

> **Suposición:** PostgreSQL como base (no fue parte de la respuesta de stack, solo "FastAPI + React"). Se elige por JSONB para odontograma, constraints de exclusión para anti-solapamiento y Row-Level Security futura por tenant. Ver `09_decisiones_y_supuestos.md` (DD-03) y `10_preguntas_abiertas.md`.

## Arquitectura general

Monolito modular SaaS multi-tenant: un solo deploy, aislamiento lógico por `tenant_id` en todas las tablas de dominio, RBAC por rol y recurso. Módulos: `agenda`, `turnos`, `notificaciones`, `clinica`, `cobros`, `admin`.

```
Paciente → Frontend React → API FastAPI → PostgreSQL
   ↑ (WhatsApp/Mercado Pago)      ↕ worker (recordatorios, recall, lista de espera)
```

Justificación (prioridad del usuario: **mantenibilidad**): el monolito modular evita la sobrecarga de microservicios para un equipo chico, con fronteras de módulo que permiten extraer servicios (notificaciones, pagos) cuando la escala lo pida. Multi-tenant desde el día 1 para escalar de independiente a clínica/cadena sin migraciones — oportunidad C4.5 de Discovery ("modo independiente → clínica").

## Integraciones externas

| Servicio | Propósito | Tipo | Etapa |
|---|---|---|---|
| WhatsApp Business API (BSP oficial) | Recordatorios, confirmaciones, recall, lista de espera | REST/webhook | MVP |
| Mercado Pago | Señas vinculadas al turno, cobro de saldos | SDK/API + webhook IPN | MVP |
| SMTP / email | Recordatorios fallback y comprobantes | SMTP | MVP |
| AFIP/ARCA (vía servicio de FE) | Factura electrónica argentina | API (etapa 2) | Posterior |
| Obras sociales / prepagas | Validación y liquidaciones | Varias (etapa 2) | Posterior |
| ReNaPDiS | Recetario electrónico (cfr. ClinIA #248) | HL7 FHIR (etapa 2+) | Posterior |
| Google Calendar | Sincronización de agenda (deseable) | API | Posterior |

## API REST

Recursos principales agrupados:

- `/tenants`, `/usuarios`, `/roles` — operación y accesos.
- `/profesionales`, `/sillones`, `/prestaciones`, `/bloqueos` — configuración de agenda.
- `/turnos`, `/lista-espera`, `/recordatorios` — ciclo del turno.
- `/pacientes`, `/historias-clinicas`, `/odontogramas`, `/planes-tratamiento`, `/consentimientos` — clínica.
- `/presupuestos`, `/cobros`, `/senias` — administración.
- `/reportes` — ocupación, ausentismo, recaudación.
