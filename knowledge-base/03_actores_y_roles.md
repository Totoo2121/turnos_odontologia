# Actores y Roles

## Actores del sistema

| Actor | Descripción | Cómo interactúa |
|---|---|---|
| Paciente | Persona con turnos y tratamiento en el consultorio | Reserva online 24/7 (sin cuenta o con cuenta liviana), confirma por WhatsApp, paga seña MP |
| Recepcionista | Gestiona agenda, confirmaciones y cobros en mostrador | App web: agenda del día, estados de turno, caja |
| Odontólogo / profesional | Atiende y registra clínica | App web: su agenda, HCE, odontograma, planes, consentimientos |
| Asistente | Apoya en consultorio (carga, imágenes) | App web con permisos acotados a carga clínica |
| Dueño / gerente (propietario) | Administra el tenant: configuración, reportes, usuarios | Panel admin: reportes, liquidaciones (etapa 2), auditoría, exportación |
| Sistema (actor técnico) | Worker de automatización | Envía recordatorios, procesa lista de espera, recall — vía WA/email |

## RBAC — Matriz de permisos

| Rol → Recurso | Agenda / turnos | Pacientes / HCE | Odontograma / planes | Presupuestos / cobros | Reportes | Configuración / usuarios | Auditoría / exportación |
|---|---|---|---|---|---|---|---|
| Propietario | CRUD | CRUD | R | CRUD | R total | CRUD | R + ejecutar |
| Odontólogo | RUD (sus turnos) | CRUD (sus pacientes) | CRUD | R (sus presupuestos) | R propio | — | — |
| Recepción | CRUD turnos | CR pacientes | R | CRUD cobros | R operativo | — | — |
| Asistente | R turnos | CR (carga) | R (carga adjuntos) | — | — | — | — |
| Paciente (portal) | CR propios | R propios | R propios | Pagar (propios) | — | — | — |

Reglas cruzadas: un odontólogo nunca ve HCE de pacientes de otro profesional salvo rol propietario o derivación explícita (RN-SE-02); recepción no modifica evoluciones clínicas (RN-SE-03).

## Rutas públicas

- `GET /reservar/{slug}` — turnero online 24/7 (sin autenticación; rate-limit + captcha).
- `GET /p/{token}` — portal del paciente (token firmado por turno).
- Webhooks: Mercado Pago IPN, WhatsApp BSP (firmados por el proveedor).
- `GET /health`, docs de API solo en entornos no productivos.
