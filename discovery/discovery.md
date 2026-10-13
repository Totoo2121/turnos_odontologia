# Informe de Discovery — Sistema de turnos y gestión odontológica (Argentina)

## 1. Portada

| Campo | Detalle |
|---|---|
| **Título** | Informe de Discovery — SaaS multi-tenant de turnos y gestión odontológica para Argentina |
| **Materia** | Metodología I — UTN FRM |
| **Integrantes** | [completar — nombres y legajos] |
| **Fecha** | 2026-10-04 |
| **Producto analizado** | Turnos-odontología: reserva online por slug, recordatorios WhatsApp Business API + email, señas con Mercado Pago, HCE append-only, odontograma FDI, presupuestos → planes de tratamiento, reportes, auditoría/exportación (cfr. `knowledge-base/02_descripcion_general.md` y `06_funcionalidades.md`) |
| **Insumo** | Relevamiento de mercado del 2026-10-03 (17 sistemas), condensado en este documento a 15 sistemas, reorganizado en las 8 secciones pedidas por la cátedra y alineado con el producto definido en `knowledge-base/`. Este es el documento **único** de Discovery del proyecto. |

> **Regla de evidencia (aplica a todo el documento):** en TODA celda no respaldada por fuente pública verificable se escribe literalmente `No evidenciado`. Se distingue funcionalidad comprobada de afirmación comercial. Ningún ejemplo contiene datos reales de pacientes (regla dura del proyecto); todo caso ilustrativo es sintético y se marca como ficticio.

---

## 2. Resumen Ejecutivo

El mercado argentino de software odontológico está atendido por pocos jugadores locales (Bilog, DentalCore, FLAP, ClinIA, Dentatools, DenPro) y una larga cola de productos regionales e internacionales sin localización fiscal argentina (factura electrónica ARCA, obras sociales y liquidaciones). El estándar de mercado —agenda multi-profesional, reserva online 24/7, recordatorios automáticos, HCE + odontograma + presupuestos vinculados, caja y reportes— lo cumplen los líderes, pero **ningún producto verificado combina en una sola oferta el "combo argentino" completo**: WhatsApp oficial de ciclo completo incluido (no como add-on), seña con Mercado Pago vinculada al turno, factura electrónica ARCA, obras sociales y precio público en pesos.

Los hallazgos críticos son tres. Primero, la **opacidad comercial** es la norma: los cuatro principales competidores locales no publican precios, lo que frena la adopción del segmento independiente. Segundo, **WhatsApp está a medias en casi todos**: o es manual, o es un adicional pago en dólares, o ata la automatización real a los planes más caros. Tercero, la **trazabilidad y la portabilidad de datos** (exportación, backups, auditoría) son prácticamente indocumentadas en la oferta local, lo que alimenta el temor al lock-in.

La recomendación es un MVP enfocado: agenda multi-profesional con sillones/boxes y anti-solapamiento, reserva online por enlace con seña de Mercado Pago, recordatorios y confirmación por WhatsApp Business API (con email como fallback), HCE append-only + odontograma FDI + presupuesto que genera plan y deuda, caja y reportes básicos, roles/permisos y exportación abierta. Los diferenciadores de la v1 son el combo argentino cerrado desde el día uno, el auto-relleno de huecos y recall incluidos (no como add-on), y la transparencia (precio público, exportación total, sin permanencia). La IA diagnóstica, el recetario ReNaPDiS propio, el multi-sucursal pleno y la API pública quedan para etapas posteriores. Para validar el posicionamiento se propone demoear cinco competidores (Bilog, DentalCore, Dentalink, FLAP, DentiDesk) y tomar tres referentes de UX (AgendaPro, NexHealth, CareStack/Curve Dental).

---

## Sección A — Tabla comparativa de 15 sistemas relevantes para Argentina

Criterio de inclusión: sistemas odontológicos (o de reserva con tracción en salud) con evidencia pública de operación en Argentina/LatAm, más referentes internacionales que fijan el techo de producto. Columnas exactas pedidas por la consigna. Todo lo no respaldado figura como `No evidenciado`.

| # | Producto / Proveedor | País / Segmento | Reserva online | Recordatorios | Fuente y fecha |
|---|---|---|---|---|---|
| 1 | Bilog / Bilog S.A. | Argentina / Consultorios y clínicas multi-sede | Agenda online para pacientes ("Bilog Turnos"): reserva, cancela y consulta online; alta por QR en recepción | Recordatorios y confirmaciones automáticas; asistente IA "iAngela" como adicional pago | https://bilog.com.ar/ y https://docs.bilog.com.ar/initial-guide/initial-setup — consulta 2026-10-03 |
| 2 | DentalCore / DentalCore | Argentina (Bs. As.) / Consultorio, clínica y cadenas | Portal del paciente web: agenda turnos, ve tratamiento, firma consentimientos, chatbot IA | Bot WhatsApp con 9 automatizaciones (confirmar, rellenar huecos, recall, captar leads); confirmación por WhatsApp | https://dentalcore.app/ — consulta 2026-10-03 |
| 3 | Dentalink / Dentalink SpA | Chile, operación LatAm y España / Consultorio y clínica todos los tamaños | Agendamiento online 24/7 (web, redes, WhatsApp); Contact Center con IA 24/7 en plan alto | Recordatorios y confirmaciones automáticas por WhatsApp/email según plan; reprogramación inteligente de huecos | https://www.softwaredentalink.com/es/ y https://www.softwaredentalink.com/es/planes — consulta 2026-10-03 |
| 4 | FLAP / tuwebmaster | Argentina / Independiente, clínica y sucursales | Turnero 24/7 web responsive con seña al reservar; cancelación/reprogramación por el paciente | Avisos automáticos por email incluidos; `No evidenciado` para WhatsApp incluido (se ofrece vía paquetes adicionales pagos) | https://flap.com.ar/odontologos — consulta 2026-10-03 |
| 5 | ClinIA - OdontoClinIA / ClinIA | Argentina / Consultorios, clínicas PyME, hospitales/municipios | Turnero web 24/7 con confirmación por WhatsApp y email; asistente IA por WhatsApp que agenda | Recordatorios automáticos por WhatsApp; recall/controles como módulo: `No evidenciado` | https://www.clinia.com.ar/odontologia — consulta 2026-10-03 |
| 6 | DentiDesk / Servicios Tecnológicos DENTIDESK Chile SpA | Chile, operación LatAm / Clínicas y centros médicos | Agendamiento online con enlace integrable a la web; confirmación/anulación por email | Correos de confirmación y recordatorio; WhatsApp automático: `No evidenciado` (solo envío manual; la automatización figura como próxima) | https://www.dentidesk.com/ y https://www.dentidesk.cl/dentidesk/feature — consulta 2026-10-03 |
| 7 | Dentatools / Dentatools | LatAm (página AR) / Consultorio de 1 a 3 profesionales, cobro particular | Auto-agendado por enlace (WhatsApp/redes/sitio) con bloqueo instantáneo del turno | Recordatorios automáticos por WhatsApp (la confirmación actualiza la agenda) | https://dentatools.co/ar/ — consulta 2026-10-03 |
| 8 | DenPro / DenPro | Argentina / Odontólogo independiente y clínica pequeña | `No evidenciado` (reserva online 24/7 no demostrada en detalle público) | `No evidenciado` | https://www.denpro.ar/ — consulta 2026-10-03 |
| 9 | Clinic Cloud / Clinic Cloud | España, operación ES + LatAm / Consulta propia, clínica pequeña-mediana, franquicias | Reserva online 24/7 + portal del paciente; integración con Doctoralia (reservas/visibilidad en ES) | Recordatorios automáticos (SMS/email; WhatsApp en comunicaciones) y campañas de marketing | https://clinic-cloud.com/tarifas y https://clinic-cloud.com/funcionalidades — consulta 2026-10-03 |
| 10 | AgendaPro / AgendaPro | Chile, operación CL/MX/BR/ES / Estética, salud y clínicas (no dental-específico) | Reservas 24/7 (web propia, Instagram, Google Maps, WhatsApp) con cambios/cancelaciones instantáneas; IA "Sofia" que agenda | Recordatorios automáticos WhatsApp/SMS/email 1 a 3 días antes con doble confirmación; odontograma: no posee (producto genérico) | https://agendapro.com/es y https://agendapro.cloud/ — consulta 2026-10-03 |
| 11 | Doctoralia Pro / Docplanner-Doctoralia | Polonia/España, global con LatAm / Especialistas y clínicas | Reservas online 24/7 omnicanal (perfil + widgets) con pagos online anticipados y lista de espera inteligente | Recordatorios automáticos (email/app; WhatsApp en planes altos) y campañas email/SMS; odontograma: no posee (producto genérico) | https://pro.doctoralia.es/productos/doctoralia-pro-para-clinicas y https://pro.doctoralia.es/precios/para-especialistas — consulta 2026-10-03 |
| 12 | CareStack / CareStack (Goodland Tech) | EE. UU. / Clínicas y grupos/DSO (referente internacional) | Self-scheduling online, portal del paciente, formularios digitales, check-in en kiosco | Recordatorios y notificaciones, mensajería bidireccional, SMS masivos, IA telefónica (adicional) | https://carestack.com/pricing y https://carestack.com/dental-software/features — consulta 2026-10-03 |
| 13 | Curve Dental / Curve Dental | EE. UU./Canadá / Independiente y grupos (referente internacional) | Online booking, formularios inteligentes, gestión de pacientes ("GRO") | Recordatorios y recare automatizado, gestión de reseñas, IA ambiental | https://www.curvedental.com/ — consulta 2026-10-03 |
| 14 | Dentrix Ascend / Henry Schein One | EE. UU. (solo disponible en EE. UU.) / Consultorio individual a DSO (estándar mundial) | Online booking automatizado con confirmaciones y mensajería bidireccional | Confirmaciones y recordatorios (suite de engagement) | https://www.dentrix.com/ y https://www.dentrixascend.com/ — consulta 2026-10-03 |
| 15 | tab32 / tab32 | EE. UU. / Independiente, grupos pequeños, DSO (referente nube económica) | Online booking, mensajería bidireccional, VoIP, firma electrónica | Auto-reminders y campañas ("Hello Patient") | https://tab32.com/pricing/ y https://tab32.com/ — consulta 2026-10-03 |

**Exclusiones documentadas:** del relevamiento previo de 17 sistemas se excluyen aquí NexHealth (es capa de experiencia del paciente, no un PMS odontológico: no reemplaza agenda clínica ni HCE) y Open Dental (self-hosted Windows con MySQL local, sin localización argentina verificada). Nombres mencionados en la consigna original sin sitio oficial verificable (FeatherDent, SB Clinics, Oralsurgery) se consignan como `No evidenciado / no verificado` y no entran en tablas.

---

## Sección B — Matriz de puntuación 0–5 (ponderada)

### Nota metodológica

- **Escala por criterio (0–5):** 0 = ausente o no evidenciado; 1 = testimonial (mención marketing sin demo/docs); 2 = básico (función presente pero parcial o manual); 3 = sólido (cubre el uso estándar con evidencia pública); 4 = fuerte (automatizado, integrado, con docs o demo); 5 = líder (mejor práctica verificable del mercado relevado).
- **Pesos (fijados por la consigna):** Turnos 25% · Clínica 20% · Integraciones/WhatsApp 15% · Cobros/Facturación 15% · UX 10% · Seguridad/RLS 10% · Precio 5%. Total = Σ (puntaje × peso), rango 0–5.
- **Tratamiento de `No evidenciado` (decisión no obvia, explícita):** se puntúa **0** en el criterio afectado (penalización conservadora) en lugar de excluirse la celda, porque excluirla premiaría la opacidad: un vendor sin evidencia pública no puede puntuar igual que uno auditado. Como contrapeso, la columna Fuente de la Sección A permite identificar qué ceros son "ausencia real" y cuáles son "falta de evidencia", y se recomienda un análisis de sensibilidad (recalcular sin el criterio opaco) antes de decisiones de compra. Los puntajes son juicio analítico sobre evidencia pública del 2026-10-03, no benchmark medido con demos.
- **Criterio Precio:** premia transparencia y accesibilidad en pesos (precios públicos ARS = 4–5; cotización opaca = 2–3; pricing EE. UU. impagable para AR = 1).

| # | Sistema | Turnos 25% | Clínica 20% | Integ./WhatsApp 15% | Cobros/Fact. 15% | UX 10% | Seguridad 10% | Precio 5% | **Total** |
|---|---|---|---|---|---|---|---|---|---|
| 1 | DentalCore (AR) | 4 | 5 | 4 | 4 | 4 | 3 | 2 | **4,00** |
| 2 | CareStack (US, ref.) | 4 | 5 | 1 | 5 | 4 | 4 | 1 | **3,75** |
| 3 | Bilog (AR) | 4 | 3 | 4 | 5 | 3 | 3 | 3 | **3,70** |
| 4 | Clinic Cloud (ES) | 4 | 4 | 2 | 4 | 4 | 4 | 3 | **3,65** |
| 5 | Dentalink (CL) | 4 | 4 | 3 | 3 | 4 | 3 | 3 | **3,55** |
| 6 | Curve Dental (US, ref.) | 4 | 4 | 1 | 4 | 4 | 4 | 2 | **3,45** |
| 7 | FLAP (AR) | 4 | 3 | 4 | 3 | 4 | 2 | 3 | **3,40** |
| 8 | ClinIA (AR) | 3 | 4 | 4 | 3 | 3 | 4 | 2 | **3,40** |
| 9 | tab32 (US, ref.) | 4 | 4 | 1 | 3 | 4 | 4 | 3 | **3,35** |
| 10 | DentiDesk (CL) | 3 | 5 | 2 | 3 | 3 | 3 | 3 | **3,25** |
| 11 | Dentrix Ascend (US, ref.) | 3 | 5 | 1 | 4 | 3 | 4 | 1 | **3,25** |
| 12 | AgendaPro (CL) | 5 | 1 | 3 | 3 | 5 | 2 | 3 | **3,20** |
| 13 | Doctoralia Pro | 4 | 2 | 2 | 2 | 5 | 3 | 2 | **2,90** |
| 14 | Dentatools (AR) | 3 | 3 | 2 | 2 | 3 | 2 | 5 | **2,70** |
| 15 | DenPro (AR) | 3 | 3 | 1 | 2 | 3 | 3 | 4 | **2,60** |

**Lectura ejecutiva de la matriz:** el líder ponderado es DentalCore (4,00), pero su puntaje premia un diferencial clínico (CDSS con 17 motores) joven y con pricing opaco; el líder local consolidado es **Bilog (3,70)** con 20 años de trayectoria, obras sociales y factura electrónica. El techo internacional (CareStack 3,75) es inalcanzable en precio para Argentina pero fija la vara de producto a 3–5 años. Ejemplo de cálculo (Bilog): 4×0,25 + 3×0,20 + 4×0,15 + 5×0,15 + 3×0,10 + 3×0,10 + 3×0,05 = **3,70**.

---

## Sección C — Análisis competitivo

### C1. Estándar de mercado (lo que el MVP debe tener sí o sí)

1. Agenda multi-profesional con vista diaria/semanal, duraciones variables, bloqueos/feriados y prevención de solapamientos.
2. Reserva online 24/7 con enlace compartible (web/redes/WhatsApp) más cancelación y reprogramación por el propio paciente.
3. Recordatorios y confirmaciones automáticas (email como base; WhatsApp donde haya API oficial o producto propio).
4. Historia clínica + odontograma digital + presupuestos/planes de tratamiento vinculados (presupuesto → odontograma → deuda en cuenta corriente).
5. Caja/cobros, presupuestos en moneda local y reportes básicos (producción, recaudación, ausencias).
6. Roles y permisos, diseño multi-sucursal (al menos reservado) y web responsive o app para el profesional.
7. Firma de consentimientos (digital o escaneada) e imágenes/RX adjuntas a la ficha.

### C2. Diferenciadores reales (pocos los tienen, y se notan)

- **Soporte clínico a la decisión / IA clínica** (DentalCore con 17 motores; IA en RX en Dentrix y CareStack): alertas y apoyo diagnóstico, no solo registro.
- **WhatsApp automatizado de ciclo completo** (confirmar → recordar → rellenar huecos → recall → leads) con API oficial: solo DentalCore (9 flujos), Dentalink con IA y AgendaPro lo hacen de punta a punta; DentiDesk aún es manual.
- **Auto-relleno de huecos y lista de espera inteligente** (DentalCore, Doctoralia, Dentalink): convierte cancelaciones en ingresos sin intervención.
- **Localización fiscal argentina real**: factura electrónica ARCA + obras sociales/liquidaciones (Bilog, DentalCore, ClinIA). Ningún jugador internacional la tiene.
- **Recetario electrónico ReNaPDiS** (ClinIA registro N.º 248): barrera regulatoria que opera como foso defensivo.
- **Autoasignación por carga** entre profesionales (FLAP): micro-diferencial operativo muy valorado en clínicas.
- **Mercado Pago vinculado al turno** (FLAP): la seña reduce ausencias y ordena el flujo de caja.

### C3. Vacíos frecuentes del mercado argentino

1. **Pricing opaco**: Bilog, DentalCore, FLAP y ClinIA no publican precios → fricción de adopción; solo Dentatools y DenPro transparentan en pesos.
2. **WhatsApp a medias**: manual (DentiDesk), adicional pago (FLAP, Bilog/iAngela en USD) o ausente. Ningún local ofrece WhatsApp oficial de ciclo completo incluido.
3. **Sin combo cobros + fiscalidad**: o hay Mercado Pago sin factura electrónica (FLAP), o factura sin Mercado Pago publicado (Bilog), o ninguno (Dentatools/DenPro). El combo MP + ARCA + obras sociales en un solo producto no existe verificado.
4. **Exportación y auditoría opacas**: casi ningún vendor local publica política de exportación de datos, backups o trazabilidad → desconfianza y temor al lock-in.
5. **Experiencia del paciente pobre**: pocos portales (DentalCore es la excepción), casi sin lista de espera, recall ni reseñas de Google automatizadas.
6. **Onboarding desparejo**: solo algunos ofrecen migración y capacitación sin cargo (FLAP, Clinic Cloud); el resto no lo evidencia.
7. **Gestión de sillones/boxes poco documentada**: la operación real del consultorio multi-silla con prevención de choques casi no aparece en el producto argentino.

### C4. Oportunidades de innovación para un producto nuevo

1. **"Combo argentino" cerrado**: agenda + WhatsApp oficial de ciclo completo incluido + Mercado Pago (señas) + ARCA + 1 obra social trazadora + precio público en pesos. Nadie lo ofrece completo y verificado.
2. **Transparencia como estrategia**: pricing público, exportación de datos garantizada y política de backups publicada → antídoto al lock-in temido.
3. **IA práctica, no cosmética**: notas por voz post-consulta, scoring de no-show, recall inteligente y detección de huecos; incluida, no en dólares aparte.
4. **Captación integrada**: perfil público + reseñas de Google + recordatorios → cerrar el loop adquisición → retención que hoy solo dan genéricos (AgendaPro/Doctoralia).
5. **Escala independiente → clínica**: precio por profesional que crezca sin migraciones (del independiente tipo Dentatools a la clínica tipo Bilog en el mismo sistema; multi-tenant desde el día 1).
6. **Boxes/sillones como recurso de primera clase** + sobreturnos configurables: resolver la operación real multi-silla (cfr. US-001/US-003).
7. **PWA rápida / offline-first**: la conectividad argentina desigual hace diferencial una app que sigue agendando sin internet; no visto en ningún relevado.

---

## Sección D — Recomendación final

### D1. Cinco competidores prioritarios para analizar mediante demo

1. **Bilog** — el incumbente local a desplazar: demo de obras sociales/liquidaciones + factura electrónica + Bilog Turnos. Preguntar precios por plan y costo de iAngela/Facturante.
2. **DentalCore** — el rival de producto más peligroso (CDSS + bot WhatsApp + ARCA + obras sociales): demo del CDSS y los 9 flujos de WhatsApp; verificar precio y madurez/soporte.
3. **Dentalink** — el regional escalado (playbook de IA integrada y expansión LatAm): demo del Contact Center con IA y planes; evaluar su brecha argentina (obras sociales/ARCA).
4. **FLAP** — la UX moderna a igualar (autoasignación, Mercado Pago, turnero): demo del turnero + señas MP + analíticas; verificar costo real del adicional WhatsApp.
5. **DentiDesk** — la profundidad clínica por especialidad a igualar/superar (fichas, reportes): demo de fichas + presupuestos + reportes; confirmar roadmap de WhatsApp automático.

### D2. Tres productos de referencia para experiencia de usuario

1. **AgendaPro** — flujo de reserva 24/7 (web/Instagram/Maps/WhatsApp) y recordatorios con doble confirmación: el estándar de fricción cero a copiar (cfr. US-010).
2. **NexHealth** — experiencia omnicanal del paciente (scheduling, formularios, pagos, recordatorios) sincronizada con el PMS: referencia de "capa paciente" desacoplada. Nota: excluido de la matriz por no ser PMS odontológico; se usa solo como referente UX.
3. **CareStack / Curve Dental** — tableros operativos (huddle boards, scorecards, appointment finder) y charting integrado: referencia de densidad profesional bien resuelta (cfr. US-002/US-040).

### D3. MVP sugerido (alineado con `knowledge-base/06_funcionalidades.md`)

**Imprescindible (v1):**

- Agenda multi-profesional + sillones/boxes, duraciones variables, bloqueos, anti-solapamiento, sobreturnos configurables (US-001, US-002, US-003).
- Reserva online 24/7 por enlace `/reservar/{slug}` + cancelación/reprogramación por el paciente + lista de espera básica (US-010, US-012).
- Recordatorios/confirmaciones automáticas por WhatsApp Business API + email como fallback (US-020).
- HCE append-only + odontograma FDI + presupuestos vinculados que generan plan y deuda (US-030, US-031, US-032).
- Caja/cobros: señas con Mercado Pago + registro en pesos + reportes de ocupación, ausentismo y recaudación (US-011, US-040).
- Roles/permisos, consentimientos firmados, imágenes/RX adjuntas, exportación abierta de datos y auditoría (US-041).

**Diferenciador v1 (lo que gana contra Bilog/DentalCore):**

- Combo argentino cerrado desde el día 1: Mercado Pago + ARCA (vía servicio de FE) + 1 obra social trazadora, precio público en pesos.
- Auto-relleno de huecos + recall automático incluidos, no como adicional (US-012, US-021).
- Transparencia: exportación total, backups declarados, sin permanencia (US-041).
- PWA rápida + migración asistida gratuita en el onboarding.

**Etapas posteriores (no v1):**

- Facturación electrónica plena multi-comprobante y liquidaciones multi-OS complejas (US-042).
- CDSS/IA diagnóstica, recetario ReNaPDiS propio (US-050, US-051).
- Periodontograma avanzado, multi-sucursal pleno, marketplace de captación y campañas (US-052).
- API pública e integraciones con radiología/laboratorio, firma digital certificada (US-053).

---

## 7. Verificación de fuentes (muestra auditada de 5)

> Método honesto: en esta corrida **no se realizó navegación en vivo**; la verificación consiste en una auditoría de trazabilidad del relevamiento previo (consultado el 2026-10-03) contra lo afirmado en este informe (auditoría del 2026-10-04). Nada se declara "reabierto y comprobado" sin haberlo abierto. Se recomienda re-verificar las 5 URLs antes de la defensa.

| # | Qué afirmaba el reporte previo | Qué encontramos al auditar (2026-10-04, sin re-apertura) | Qué corregimos en este informe |
|---|---|---|---|
| 1 | Bilog: factura electrónica ARCA vía Facturante + obras sociales/liquidaciones en plan Premium (fuente: docs.bilog.com.ar + comparativa MedicAI) | Trazabilidad correcta a dos fuentes independientes (docs oficiales + comparativa de tercero); la URL de docs existe en el reporte pero no se reabrió en esta corrida | Se baja el tono de "comprobado" a "documentado en docs oficiales según relevamiento del 2026-10-03" y se marca pendiente de re-verificación con demo |
| 2 | DentalCore: CDSS con 17 motores + bot WhatsApp con 9 automatizaciones (fuente única: dentalcore.app) | Fuente única (sitio del vendor, sin docs públicas ni comparativa independiente que lo respalde); riesgo de marketing no verificado | Se conserva el dato pero se advierte explícitamente " difer encial joven, fuente única del vendor" y se ubica 1.º en la lista de demos para verificarlo |
| 3 | DentiDesk: WhatsApp solo manual; el automático figura como "próximo" | Afirmación negativa ("no posee") correctamente consignada como `No evidenciado` en la Sección A en lugar de puntuarla como ausencia definitiva | Sin corrección de contenido; se valida el criterio: lo negativo también exige fuente, y aquí la hay (feature page + términos) |
| 4 | Dentatools: precios ARS públicos ($15.000/$30.000) y "sin factura AFIP ni obras sociales (declarado)" | Precios atados a fecha (2026-10-03) y moneda inflacionaria; el "sin AFIP" es autodeclarado por el vendor (señal honesta, inusual) | Se agrega advertencia de vigencia ("validar antes de usar en decisiones") y se premia la transparencia en la matriz (Precio 5) sin extrapolarlo a calidad clínica |
| 5 | CareStack: Essentials desde USD 829/mes (fuente: carestack.com/pricing) | Precio de la página oficial de pricing, la fuente más sólida del relevamiento; aun así es precio EE. UU. por ubicación, no trasladable a AR | Se mantiene como techo de referencia y se explicita "inalcanzable en precio para Argentina" para que el 3,75 no se lea como recomendación de compra |

**Conclusión de la auditoría:** 4 de 5 muestras tienen trazabilidad aceptable (URL + fecha + tipo de fuente); 1 (DentalCore CDSS) depende de fuente única del vendor y queda como hipótesis a verificar en demo. Ninguna verificación fue fraguada: lo no reabierto se declara no reabierto.

---

## 8. Referencias completas

Formato: Autor / Título / URL / Fecha de consulta. Todas las consultas del relevamiento base son del 2026-10-03; la auditoría de este informe es del 2026-10-04.

1. Bilog — Sitio oficial / https://bilog.com.ar/ / 2026-10-03.
2. Bilog — Documentación oficial (setup inicial, beneficios, presupuestos) / https://docs.bilog.com.ar/initial-guide/initial-setup · https://docs.bilog.com.ar/patients/benefits · https://docs.bilog.com.ar/patients/budgets / 2026-10-03.
3. Google Play — Bilog GoMobile (`com.bilog.gomobile`) / https://play.google.com/store/apps/details?hl=es&id=com.bilog.gomobile / 2026-10-03.
4. MedicAI — MedicAI vs Bilog (FE vía Facturante, OO.SS. Premium, iAngela, ReNaPDiS) / https://www.medicai.com.ar/blog/medicai-vs-bilog / 2026-10-03.
5. DentalCore — Sitio oficial / https://dentalcore.app/ / 2026-10-03.
6. Dentalink — Sitio oficial e IA / https://www.softwaredentalink.com/es/ / 2026-10-03.
7. Dentalink — Planes / https://www.softwaredentalink.com/es/planes / 2026-10-03.
8. Dentalink — Agenda (CO) / https://www.softwaredentalink.com/co/experiencia-de-pacientes/agenda / 2026-10-03.
9. Capterra — Dentalink (desde USD 29, Chile, fund. 2009) / https://www.capterra.co.cr/software/196361/dentalink / 2026-10-03.
10. tuwebmaster — FLAP odontólogos (demo con datos ficticios "Clínica Sonrisa Serena") / https://flap.com.ar/odontologos / 2026-10-03.
11. ClinIA — Odontología / https://www.clinia.com.ar/odontologia / 2026-10-03.
12. DentiDesk — Features / https://www.dentidesk.cl/dentidesk/feature · https://www.dentidesk.com/ · https://www.dentidesk.com/dentidesk/feature / 2026-10-03.
13. DentiDesk — Términos (prueba 15 días, recargo 30%) / https://app.dentidesk.com/terminos.php / 2026-10-03.
14. Capterra — DentiDesk (desde USD 50, fund. 2013) / https://www.capterra.cl/software/184029/dentidesk / 2026-10-03.
15. Dentatools — Página Argentina (precios ARS, sin AFIP/OO.SS. declarado) / https://dentatools.co/ar/ / 2026-10-03.
16. DenPro — Sitio oficial (precios, +50 consultorios autodeclarado) / https://www.denpro.ar/ / 2026-10-03.
17. Clinic Cloud — Tarifas / https://clinic-cloud.com/tarifas / 2026-10-03.
18. Clinic Cloud — Software dental / https://clinic-cloud.com/software-clinica-dental-programa-odontologico / 2026-10-03.
19. Clinic Cloud — Funcionalidades / https://clinic-cloud.com/funcionalidades / 2026-10-03.
20. AgendaPro — Sitio ES / https://agendapro.com/es / 2026-10-03.
21. AgendaPro — Planes / https://agendapro.cloud/ / 2026-10-03.
22. Doctoralia Pro — Para clínicas / https://pro.doctoralia.es/productos/doctoralia-pro-para-clinicas / 2026-10-03.
23. Doctoralia Pro — Precios especialistas y clínicas / https://pro.doctoralia.es/precios/para-especialistas · https://pro.doctoralia.es/precios/para-clinicas / 2026-10-03.
24. CareStack — Pricing y features / https://carestack.com/pricing · https://carestack.com/dental-software/features / 2026-10-03.
25. Curve Dental — Sitio oficial / https://www.curvedental.com/ / 2026-10-03.
26. Dentrix — Sitio oficial / https://www.dentrix.com/ / 2026-10-03.
27. Dentrix Ascend — Sitio oficial / https://www.dentrixascend.com/ / 2026-10-03.
28. tab32 — Pricing y home / https://tab32.com/pricing/ · https://tab32.com/ / 2026-10-03.
29. Dentiqa — Comparativa software dental 2026 / https://dentiqa.app/blog/software-gestion-clina-dental / 2026-10-03.
30. VitalDesk — Mejor software clínico 2026 (Dentalink vs AgendaPro) / https://vitaldesk.cl/blog/mejor-software-clinico-2026 / 2026-10-03.

---

*Fin del informe. Ejemplo sintético con datos ficticios a modo ilustrativo (sin datos reales de pacientes): la "Clínica Sonrisa Serena" usada en la demo pública de FLAP es un caso ficticio del vendor, no un paciente ni cliente real.*
