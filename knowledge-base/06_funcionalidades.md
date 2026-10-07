# Funcionalidades

Etiquetas: **[MVP]** entra en v1.0 (alcance "Turnos + clínica"); **[E2]** etapa posterior (OO.SS./ARCA, IA clínica, marketplace).

## Épica 1: Agenda del consultorio

### US-001 — Configurar agenda (profesionales, sillones, prestaciones) [MVP]
**Como** propietario **Quiero** dar de alta profesionales, sillones/boxes y prestaciones con duración **Para** que la agenda refleje la operación real.
**Criterios de aceptación**:
- [ ] Prestación con duración, buffer, seña y antelación de cancelación configurables.
- [ ] Sillón como recurso asignable a cada turno.
- [ ] Bloqueos por profesional/sillón con motivo.
**Reglas relacionadas**: RN-AG-03, RN-AG-04, RN-AG-05.

### US-002 — Ver agenda diaria/semanal multi-profesional [MVP]
**Como** recepcionista **Quiero** ver el día/semana con estados y cobros **Para** operar el mostrador sin llamadas.
**Criterios de aceptación**:
- [ ] Vista día y semana por profesional y por sillón.
- [ ] Estados: reservado, confirmado, en sala, atendido, cancelado, ausente.
- [ ] Crear turno solo en huecos válidos (solape y bloqueo rechazados).
**Reglas relacionadas**: RN-AG-01, RN-AG-02, RN-AG-05.

### US-003 — Sobreturnos controlados [MVP]
**Como** recepcionista **Quiero** crear sobreturnos autorizados **Para** atender urgencias sin romper la agenda.
**Criterios de aceptación**:
- [ ] Solo en prestaciones habilitadas y con rol autorizado.
- [ ] Marcado visible como sobreturno.
**Reglas relacionadas**: RN-AG-06, RN-G-03.

## Épica 2: Turnos digitales 24/7

### US-010 — Reserva online por enlace [MVP]
**Como** paciente **Quiero** reservar eligiendo prestación, profesional y horario **Para** no tener que llamar.
**Criterios de aceptación**:
- [ ] Enlace `/reservar/{slug}` responsive, sin cuenta obligatoria.
- [ ] Solo huecos válidos; confirmación inmediata en pantalla + WhatsApp.
- [ ] Cancelación/reprogramación desde token hasta el límite configurado.
**Reglas relacionadas**: RN-TU-01, RN-TU-02, RN-TU-03.

### US-011 — Reserva con seña por Mercado Pago [MVP]
**Como** paciente **Quiero** pagar la seña al reservar **Para** asegurar mi turno.
**Criterios de aceptación**:
- [ ] Checkout MP y vuelta con estado visible.
- [ ] Webhook acredita o vence la reserva; vencida libera el hueco.
**Reglas relacionadas**: RN-TU-04, RN-AD-03, RN-AD-04.

### US-012 — Lista de espera con auto-relleno [MVP]
**Como** paciente en espera **Quiero** que me ofrezcan huecos liberados **Para** adelantar mi atención.
**Criterios de aceptación**:
- [ ] Alta en lista por prestación/franja; oferta por orden con vencimiento.
- [ ] Convertida → turno normal con sus reglas.
**Reglas relacionadas**: RN-TU-05.

## Épica 3: Automatización por WhatsApp

### US-020 — Recordatorios y confirmación [MVP]
**Como** sistema **Quiero** enviar recordatorios T-48h/T-24h por WA + email **Para** bajar ausentismo.
**Criterios de aceptación**:
- [ ] Plantillas aprobadas; confirmación por WA cambia estado y queda auditada.
- [ ] Todo sale por Business API del tenant.
**Reglas relacionadas**: RN-NO-01, RN-NO-02, RN-NO-05.

### US-021 — Recall de ausentes y controles [MVP]
**Como** sistema **Quiero** recuperar ausentes y citar controles periódicos **Para** no perder pacientes.
**Criterios de aceptación**:
- [ ] Ausente → recall a 7 días; doble ausencia → exige seña próxima vez.
- [ ] Controles por intervalo de prestación.
**Reglas relacionadas**: RN-NO-03, RN-NO-04.

## Épica 4: Clínica odontológica

### US-030 — HCE + evoluciones [MVP]
**Como** odontólogo **Quiero** historia con anamnesis y evoluciones append-only **Para** atender con trazabilidad.
**Criterios de aceptación**:
- [ ] Anamnesis estructurada; evoluciones con autor/fecha, sin edición destructiva.
**Reglas relacionadas**: RN-HC-01, RN-SE-02, RN-SE-03.

### US-031 — Odontograma FDI + imágenes [MVP]
**Como** odontólogo **Quiero** odontograma por pieza/superficie con RX/fotos **Para** diagnosticar y planificar.
**Criterios de aceptación**:
- [ ] Eventos con pieza FDI + estado + fecha + autor; adjuntos en la historia.
**Reglas relacionadas**: RN-HC-02, RN-HC-05.

### US-032 — Presupuesto → plan + deuda [MVP]
**Como** odontólogo **Quiero** presupuestar sobre el odontograma y que lo aceptado genere plan y deuda **Para** cerrar tratamientos.
**Criterios de aceptación**:
- [ ] Ítems por prestación/pieza en ARS; aceptación → etapas + cuenta corriente.
- [ ] Consentimiento firmado requerido en planes invasivos.
**Reglas relacionadas**: RN-HC-03, RN-HC-04, RN-AD-01, RN-AD-02.

## Épica 5: Administración y operación

### US-040 — Caja y reportes [MVP]
**Como** dueño **Quiero** ocupación, ausentismo y recaudación por profesional **Para** decidir.
**Criterios de aceptación**:
- [ ] Reportes: ocupación, cancelaciones/ausencias, recaudación, señas pendientes.
**Reglas relacionadas**: RN-AD-01.

### US-041 — Exportación y auditoría [MVP]
**Como** propietario **Quiero** exportar todos mis datos y ver auditoría **Para** no quedar cautivo.
**Criterios de aceptación**:
- [ ] Exportación completa en formato abierto; log de eventos sensibles.
**Reglas relacionadas**: RN-SE-04, RN-SE-05.

### US-042 — FE ARCA + obras sociales **[E2]**
**Como** dueño **Quiero** facturar y liquidar OS/prepagas **Para** operar formal.
**Criterios de aceptación**:
- [ ] Esquema ya reservado (obra_social, nomenclador, comprobante_fiscal).
**Reglas relacionadas**: RN-AD-05.

## Épica 6: Diferenciadores futuros [E2]

- US-050 Recetario ReNaPDiS (moat regulatorio tipo ClinIA #248).
- US-051 IA práctica: notas por voz post-consulta, no-show scoring.
- US-052 Captación: perfil público + reseñas Google automatizadas.
- US-053 API pública e integraciones radiología/laboratorio.
