# Modelo de Datos

## Dominios

- **Operación**: tenant (organización), sucursal (diseño preparado, full en etapa 2), usuario, rol.
- **Agenda**: profesional, sillón/box (recurso de primera clase), prestación, bloqueo, turno, lista de espera.
- **Clínica**: paciente, historia clínica, odontograma, plan de tratamiento, consentimiento, adjunto (RX/foto).
- **Administración**: presupuesto, cuenta corriente, cobro/seña (Mercado Pago), recordatorio, reporte (derivado).

## ERD (textual)

```
tenant 1──* sucursal 1──* sillon
tenant 1──* usuario (*──* rol)
tenant 1──* profesional 1──* turno *──1 paciente
prestacion 1──* turno (duración variable por prestación)
sillon 1──* turno (un turno ocupa 1 profesional + 1 sillón en un rango)
turno 1──* recordatorio | 1──* cobro | 0..1──1 presupuesto
paciente 1──1 historia_clinica 1──1 odontograma
odontograma 1──* evento_pieza (pieza FDI + superficie + estado + fecha)
presupuesto 1──* item (prestación + pieza) ; presupuesto aceptado ──* plan_tratamiento
paciente *──* lista_espera (por prestación/franja preferida)
```

## Entidades

### tenant
- Atributos: `id (uuid)`, `nombre`, `slug_reserva (único)`, `plan`, `moneda (default ARS)`, `created_at`.
- Relaciones: 1──* usuarios, profesionales, pacientes, turnos.
- Constraints: `slug_reserva` único global; todo acceso filtra por `tenant_id`.
- Índices: `slug_reserva`.

### profesional
- Atributos: `id`, `tenant_id`, `usuario_id?`, `nombre`, `matricula?`, `especialidades[]`, `duracion_default_min`, `activo`.
- Relaciones: *──* prestaciones (habilitadas), 1──* turnos, 1──* bloqueos.
- Constraints: al menos una prestación habilitada para agendar.

### sillon (box / recurso)
- Atributos: `id`, `tenant_id`, `sucursal_id?`, `nombre`, `activo`.
- Relaciones: 1──* turnos.
- Constraints: es recurso de primera clase (oportunidad C4.6 de Discovery); un turno siempre referencia un sillón.

### prestacion
- Atributos: `id`, `tenant_id`, `nombre`, `duracion_min`, `requiere_sillon (bool)`, `permite_sobreturno (bool)`, `seña_obligatoria (bool)`, `monto_seña`, `anticipacion_min_cancel_hs`, `precio ARS`.
- Relaciones: *──* profesionales; 1──* turnos.
- Constraints: `duracion_min > 0`; cambio de duración no altera turnos ya creados.

### turno
- Atributos: `id`, `tenant_id`, `paciente_id`, `profesional_id`, `sillon_id`, `prestacion_id`, `inicio (timestamptz)`, `fin (calculado)`, `estado (reservado|confirmado|en_sala|atendido|cancelado|ausente)`, `origen (mostrador|online|wa|lista_espera)`, `token_portal`.
- Relaciones: ver ERD.
- Constraints: `fin = inicio + duracion_prestacion + buffer`; **exclusión anti-solapamiento** por (`profesional_id`, rango) y por (`sillon_id`, rango) — ver RN-AG-01/02.
- Índices: `(tenant_id, profesional_id, inicio)`, `(tenant_id, sillon_id, inicio)`, `(tenant_id, estado, inicio)`.

### bloqueo
- Atributos: `id`, `tenant_id`, `profesional_id?`, `sillon_id?`, `inicio`, `fin`, `motivo (feriado|licencia|administrativo|mantenimiento)`.
- Constraints: bloquea la oferta de huecos; no se puede crear turno dentro de un bloqueo (RN-AG-05).

### lista_espera
- Atributos: `id`, `tenant_id`, `paciente_id`, `prestacion_id`, `profesional_id?`, `franja_preferida`, `estado (activa|ofrecida|convertida|vencida)`, `created_at`.
- Relaciones: al liberarse un hueco compatible se ofrece por orden (RN-TU-05).

### paciente / historia_clinica / odontograma
- Paciente: `id`, `tenant_id`, `nombre`, `dni?`, `telefono (WhatsApp)`, `obra_social?`, `consentimiento_datos (bool + fecha)`.
- Historia: `id`, `paciente_id`, anamnesis (alergias, medicación, antecedentes), evoluciones con autor y fecha (append-only).
- Odontograma: `id`, `historia_id`; eventos por pieza FDI (1-48) + superficie + estado (sano|caries|obturación|corona|endodoncia|extracción|implante|sellador) + fecha. Presupuesto enlaza a piezas del odontograma (como Bilog).

### presupuesto / plan_tratamiento / cobro
- Presupuesto: `id`, `paciente_id`, `items[]` (prestación + pieza + importe), `total`, `estado (borrador|enviado|aceptado|rechazado)`, `validez_hasta`.
- Aceptado → genera plan de tratamiento por etapas + deuda en cuenta corriente (RN-AD-02).
- Cobro/seña: `id`, `turno_id?`, `medio (mercadopago|efectivo|transferencia)`, `monto`, `estado (pendiente|acreditada|rechazada)`, `mp_payment_id?`.

### consentimiento / adjunto / recordatorio
- Consentimiento: `id`, `paciente_id`, `tipo`, `firma (hash + timestamp + IP/dispositivo)`, PDF generado.
- Adjunto: `id`, `historia_id`, `tipo (rx|foto|documento)`, `storage_key`, `origen`.
- Recordatorio: `id`, `turno_id`, `canal (whatsapp|email)`, `plantilla`, `enviar_at`, `estado`, `confirmado_at?`.

## Seed data inicial

- Roles: propietario, odontólogo, recepción, asistente (ver 03).
- Prestaciones ejemplo: consulta (30'), limpieza (45'), conducto (90'), corona (60'), ortodoncia control (30').
- Un sillón "Box 1" y un profesional demo; feriados nacionales AR del año como bloqueos.
- Plantillas de mensajes WA/email y política de cancelación por defecto.
