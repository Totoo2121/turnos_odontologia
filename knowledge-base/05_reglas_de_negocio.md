# Reglas de Negocio

Cada regla tiene código único para trazabilidad. Fuente principal: Discovery C1 (estándares) + C3 (vacíos) + state.discovery.

## Dominio: Agenda (RN-AG)

- **RN-AG-01**: Un profesional no puede tener dos turnos cuyos rangos `[inicio, fin)` se solapen. Se aplica en base (constraint de exclusión) y en API — la API nunca confía solo en el frontend.
- **RN-AG-02**: Un sillón/box no puede estar ocupado por dos turnos solapados, aunque sean de distintos profesionales. El sillón es recurso de primera clase (oportunidad C4.6).
- **RN-AG-03**: La duración del turno la determina la prestación (`prestacion.duracion_min + buffer`), no el profesional. El fin se calcula al crear: `fin = inicio + duración + buffer`.
- **RN-AG-04**: Los huecos ofrecidos (mostrador y online) se generan en múltiplos de la duración de la prestación sobre la grilla del profesional, descontando bloqueos y turnos existentes.
- **RN-AG-05**: Dentro de un bloqueo (feriado, licencia, mantenimiento) no se puede crear ni mover un turno; el sistema lo rechaza con el motivo del bloqueo.
- **RN-AG-06**: Sobreturno solo si `prestacion.permite_sobreturno = true` y con autorización de rol recepción o superior; el sobreturno queda marcado y no consume hueco de grilla.
- **RN-AG-07**: Reprogramar respeta RN-AG-01/02/05 en el nuevo horario y libera el anterior; la seña pagada se traslada al nuevo turno (no se pierde).
- **RN-AG-08**: Cancelación con antelación mínima configurable por prestación (`anticipacion_min_cancel_hs`); cancelación tardía libera el hueco pero puede perder la seña según política visible al reservar.

## Dominio: Turnos digitales (RN-TU)

- **RN-TU-01**: El turnero público (`/reservar/{slug}`) no exige cuenta; exige nombre + WhatsApp válido y validación anti-bots.
- **RN-TU-02**: Toda reserva online queda en estado `reservado` y requiere confirmación (WhatsApp o email) antes del umbral configurable; sin confirmación se libera el hueco.
- **RN-TU-03**: El paciente puede cancelar/reprogramar desde su token de portal hasta el límite de `anticipacion_min_cancel_hs`.
- **RN-TU-04**: Reserva con seña obligatoria genera orden de Mercado Pago; el turno queda `reservado-pendiente-pago` hasta acreditación o vencimiento (RN-AD-04).
- **RN-TU-05**: Al liberarse un hueco, se ofrece automáticamente a la lista de espera compatible por orden de antigüedad y preferencia; oferta con vencimiento, luego pasa al siguiente.

## Dominio: Notificaciones y automatización (RN-NO)

- **RN-NO-01**: Todo turno activo recibe recordatorio por WhatsApp (API oficial) a T-48h y T-24h, más email de respaldo; plantillas aprobadas, sin spam.
- **RN-NO-02**: La confirmación por WhatsApp (botón/palabra clave) cambia el estado a `confirmado` y registra fecha/hora/canal.
- **RN-NO-03**: Ausente (`ausente`) dispara recall: mensaje a los 7 días y oferta de reprogramación; dos ausencias seguidas marcan al paciente para exigir seña en la próxima reserva.
- **RN-NO-04**: Controles periódicos (ej. ortodoncia, limpieza semestral) generan recall automático según intervalo de la prestación.
- **RN-NO-05**: Ningún flujo de WhatsApp usa números personales ni API no oficial; todo sale por la cuenta Business API del tenant (diferencial vs. "WhatsApp a medias" del mercado).

## Dominio: Clínica (RN-HC)

- **RN-HC-01**: Cada paciente tiene una única historia clínica por tenant; las evoluciones son append-only (se agregan, no se editan; corrección = nueva entrada que referencia la anterior).
- **RN-HC-02**: El odontograma usa nomenclatura FDI; cada evento registra pieza + superficie + estado + fecha + autor.
- **RN-HC-03**: Presupuesto enlaza a piezas del odontograma; presupuesto `aceptado` genera plan de tratamiento por etapas y deuda en cuenta corriente (patrón Bilog).
- **RN-HC-04**: Consentimiento informado firmado (hash + timestamp + dispositivo) es requisito para iniciar un plan invasivo.
- **RN-HC-05**: RX/fotos se adjuntan a la historia, nunca al turno; el turno solo referencia.

## Dominio: Administración (RN-AD)

- **RN-AD-01**: Precios y presupuestos siempre en ARS (moneda del tenant configurable, default pesos).
- **RN-AD-02**: Presupuesto aceptado → plan por etapas + deuda exigible en cuenta corriente del paciente.
- **RN-AD-03**: La seña de Mercado Pago queda vinculada al turno (estado de cobro visible en la agenda, patrón FLAP); cancelar en término la devuelve o la deja como crédito según política.
- **RN-AD-04**: Orden de pago vencida sin acreditación libera el hueco y anula la reserva (`reservado-pendiente-pago` → `cancelado`).
- **RN-AD-05**: Facturación electrónica ARCA y liquidaciones de obras sociales son etapa 2: el modelo ya reserva `obra_social`, `nomenclador` y `comprobante_fiscal` en el esquema, pero no se implementan en v1.0.

## Dominio: Seguridad y operación (RN-SE)

- **RN-SE-01**: Aislamiento por tenant en cada query de dominio; prohibido el acceso cruzado entre organizaciones.
- **RN-SE-02**: HCE visible solo para profesionales tratantes y propietario (o derivación explícita registrada).
- **RN-SE-03**: Recepción y asistente no modifican evoluciones clínicas.
- **RN-SE-04**: Exportación total de datos del tenant en formato abierto a pedido del propietario, sin costo ni retención (diferencial de transparencia, C4.2).
- **RN-SE-05**: Auditoría append-only de eventos sensibles (accesos a HCE, cambios de agenda, cobros, exportaciones).

## Excepciones globales

- **RN-G-01**: Toda regla que diga "No evidenciado" en Discovery se trata como supuesto, no como hecho — ver `10_preguntas_abiertas.md`.
- **RN-G-02**: Ante conflicto entre disponibilidad y cobro, la agenda manda: un turno impago dentro del plazo libera el hueco (RN-AD-04 por encima de RN-TU-04).
- **RN-G-03**: Emergencias las gestiona el consultorio por mostrador (sobreturno autorizado RN-AG-06); el turnero online nunca ofrece sobreturnos.
