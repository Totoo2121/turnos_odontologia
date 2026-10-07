# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **turnos-odontologia** (SaaS multi-tenant de turnos + clínica odontológica para Argentina).
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

---

## Cómo usar este documento

1. Identificar el change a implementar (verificar que sus dependencias están en `openspec/changes/archive/`).
2. Leer los docs de la knowledge-base indicados en "Leer antes".
3. Ejecutar `/opsx:propose <nombre-del-change>`.
4. Al terminar el change, archivarlo con `/opsx:archive <nombre-del-change>`.
5. Marcar el checkbox `[x]` en este archivo.

---

## Árbol de dependencias

```
C-01 foundation-setup
  └── C-02 core-models-multitenant
        └── C-03 auth-rbac                          ← desbloquea TODO lo demás
              │
              ├── C-04 app-shell-frontend
              │     ├── C-07 agenda-mostrador-ui    ← + C-06
              │     └── C-15 clinica-caja-ui        ← + C-10 + C-14
              │
              ├── C-05 catalogo-agenda
              │     └── C-06 turnos-antissolapamiento
              │           ├── C-08 turnero-online-publico
              │           │     └── C-09 lista-espera-autorelleno  ← + C-06
              │           ├── C-10 cobros-mercadopago
              │           │     ├── C-15 (ver arriba)
              │           │     ├── C-16 caja-reportes             ← + C-14
              │           │     └── C-17 auditoria-exportacion     ← + C-14
              │           └── C-11 notificaciones-whatsapp
              │
              └── C-12 pacientes-hce
                    └── C-13 odontograma-adjuntos
                          └── C-14 presupuestos-planes
                                ├── C-15 (ver arriba)
                                ├── C-16 (ver arriba)
                                ├── C-17 (ver arriba)
                                └── C-18 esquema-etapa2-reserva [E2, fuera del MVP]
```

### Paralelismo por fase

> Cada "gate" es un punto de sincronización. Los changes dentro de un grupo pueden ejecutarse en paralelo.

```
GATE 0: ninguna
  → C-01 (solo)

GATE 1: C-01 ✓
  → C-02 (solo)

GATE 2: C-02 ✓
  → C-03 (solo)

GATE 3: C-03 ✓                     ← PRIMER FORK (3 paralelos)
  → C-04 app-shell-frontend        [Agente C]
  → C-05 catalogo-agenda           [Agente A]
  → C-12 pacientes-hce             [Agente B]

GATE 4: C-05 + C-12 ✓
  → C-06 turnos-antissolapamiento  [Agente A]
  → C-13 odontograma-adjuntos      [Agente B]

GATE 5: C-04 + C-06 + C-13 ✓       ← FORK (4 paralelos)
  → C-07 agenda-mostrador-ui       [Agente C]
  → C-08 turnero-online-publico    [Agente A]
  → C-10 cobros-mercadopago        [Agente B]
  → C-14 presupuestos-planes       [Agente C — tras C-07]

GATE 6: C-08 + C-10 ✓
  → C-09 lista-espera-autorelleno  [Agente A]
  → C-11 notificaciones-whatsapp   [Agente B]

GATE 7: C-09 + C-11 + C-14 ✓       ← JOIN pre-cierre MVP
  → C-15 clinica-caja-ui           [Agente A]
  → C-16 caja-reportes             [Agente B]
  → C-17 auditoria-exportacion     [Agente C]

GATE 8: MVP completo ✓
  → C-18 esquema-etapa2-reserva    [Agente A — fuera del MVP]
```

### Camino crítico (8 changes — mínimo irreducible)

```
C-01 → C-02 → C-03 → C-05 → C-06 → C-10 → C-16 → C-17
```

> La rama clínica (C-12 → C-13 → C-14) corre en paralelo y converge en C-15/C-16/C-17: debe completarse antes del cierre pero no alarga el crítico. El turnero online (C-08) y WhatsApp (C-11) son MVP y paralelizan sin alargar el crítico. C-18 queda fuera del camino crítico (etapa 2).

### Plan óptimo con 3 agentes

```
Paso │ Agente A (Backend Core)      │ Agente B (Backend Aux)       │ Agente C (Frontend)
─────┼──────────────────────────────┼──────────────────────────────┼─────────────────────────
  1  │ C-01 foundation-setup        │         —                    │         —
  2  │ C-02 core-models             │         —                    │         —
  3  │ C-03 auth-rbac               │         —                    │         —
  4  │ C-05 catalogo-agenda         │ C-12 pacientes-hce           │ C-04 app-shell-frontend
  5  │ C-06 turnos-antissolapamiento│ C-13 odontograma-adjuntos    │         —
  6  │ C-08 turnero-online-publico  │ C-10 cobros-mercadopago      │ C-07 agenda-mostrador-ui
  7  │ C-09 lista-espera-autorelleno│ C-11 notificaciones-whatsapp │ C-14 presupuestos-planes
  8  │ C-15 clinica-caja-ui         │ C-16 caja-reportes           │ C-17 auditoria-exportacion
  9  │ C-18 esquema-etapa2-reserva  │         —                    │         —
```

---

## FASE 0 — Cimientos

### [C-01] `foundation-setup`
- **Estado**: `[x]` completado (archivado 2026-10-03)
- **Scope**: Scaffolding completo del monorepo + infraestructura base (US transversales, sin US funcional propia)
  - Estructura de directorios según `08_arquitectura_propuesta.md` §Estructura: `backend/app/{domain,application,infrastructure,api,worker}`, `frontend/src/{features,shared,pages}`
  - `backend/`: FastAPI 0.110+ app mínima con `GET /api/health`, Alembic 1.13+ inicializado, `shared/` con settings (Pydantic), logger, db (asyncpg), exceptions
  - `frontend/`: Vite + React 18+ + TypeScript scaffolding, Zustand instalado, api-client base con refresh de JWT
  - `docker-compose.yml`: servicios `api` + `worker` + `postgres:15+` + `redis`
  - `.env.example` en cada sub-proyecto con `DATABASE_URL`, `JWT_SECRET`, `WA_BSP_TOKEN`, `WA_PHONE_ID`, `MP_ACCESS_TOKEN`, `SLOT_PUBLIC_BASE_URL`, `REMINDER_T48H_HS`, `REMINDER_T24H_HS`, `DEFAULT_CANCEL_ANTICIP_HS` (secretos sin defaults hardcodeados)
  - GitHub Actions CI: jobs paralelos backend (pytest) y frontend (tsc + build)
  - Tests: health check, carga de settings, conexión a DB en compose
- **Dependencias**: ninguna
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/01_vision_y_objetivos.md` (qué es el sistema y por qué existe)
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios + §Variables de entorno
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01 + §DD-03

---

### [C-02] `core-models-multitenant`
- **Estado**: `[x]` completado (archivado 2026-10-03)
- **Scope**: Entidades base multi-tenant + patrones de acceso a datos + seed mínimo (base de C-03 y de todo el dominio)
  - Modelos: `Tenant` (`slug_reserva` único global, `plan`, `moneda` default ARS), `Sucursal` (diseño preparado, full en E2), `Usuario`, `Rol`, `UserRol`
  - `AuditMixin` con `is_active`, `created_at`, `updated_at`, `deleted_at`; `BaseRepository[T]` + `UnitOfWork`; scoping forzado por `tenant_id` en capa de acceso (RN-SE-01)
  - Migración 001: tablas `tenant`, `sucursal`, `usuario`, `rol`, `user_rol`
  - Seed mínimo: 1 tenant demo, roles `propietario|odontologo|recepcion|asistente` (ver 03), 1 usuario ADMIN propietario
  - Tests: aislamiento multi-tenant (query cruzada denegada), CRUD repositorio genérico, soft-delete del mixin
- **Dependencias**: C-01
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §tenant + §Seed data inicial
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados (multi-tenancy, Repository, UoW)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-01
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01 + §SU-06

---

## FASE 1 — Identidad y acceso

### [C-03] `auth-rbac`
- **Estado**: `[x]` completado (archivado 2026-10-03)
- **Scope**: Autenticación JWT + RBAC por matriz rol×recurso + portal paciente por token (desbloquea todo lo protegido)
  - `POST /api/auth/login` — JWT access corto + refresh rotado, rate limiting 5/60s por IP+email
  - `POST /api/auth/refresh` — rotación con blacklist del anterior; `POST /api/auth/logout` — blacklist del access; `GET /api/auth/me`
  - Claims JWT: `sub`, `tenant_id`, `roles`, `email`, `jti`, `type`, `iat`, `exp`; refresh en cookie HttpOnly (secure, samesite=lax)
  - `PermissionContext`: `require_role()`, guards por recurso según matriz de 03 (odontólogo solo sus pacientes salvo propietario/derivación RN-SE-02; recepción/asistente sin evoluciones clínicas RN-SE-03)
  - Token firmado de portal paciente (un solo turno, expirable) para `GET /p/{token}`
  - Turnero `GET /reservar/{slug}` y webhooks declarados como rutas públicas con rate-limit + captcha (implementación en C-08/C-10/C-11)
  - Migración 002: tablas `revoked_token`, `portal_token`
  - Tests: login ok/expirado/rate-limit, rotación refresh, matriz RBAC (5 roles × recursos), aislamiento `tenant_id`
- **Dependencias**: C-02
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` (matriz RBAC + rutas públicas)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-01 + §RN-SE-02 + §RN-SE-03
  - `knowledge-base/08_arquitectura_propuesta.md` §Seguridad
  - `knowledge-base/04_modelo_de_datos.md` §tenant

---

### [C-04] `app-shell-frontend`
- **Estado**: `[x]` completado (archivado 2026-10-03)
- **Scope**: Shell de la app web + autenticación frontend + guards por rol (base de todas las UI de FASE 2/4/5)
  - Rutas y layout: login, agenda, pacientes/clínica, caja, reportes, admin; guards por rol según matriz de 03
  - Flujo login/refresh/logout contra C-03 con api-client (interceptor 401 → refresh → retry)
  - `shared/ui` base (tabla, modal, formulario, toast) + `features/` por dominio según §Estructura
  - Web responsive (MVP web, sin apps nativas); PWA evaluable solo si no cuesta (fuera de alcance si complica)
  - Tests: guards por rol, flujo login/logout, render shell por rol
- **Dependencias**: C-03
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios
  - `knowledge-base/03_actores_y_roles.md` (qué ve cada rol)
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico
  - `knowledge-base/01_vision_y_objetivos.md` §Fuera de alcance (no nativas)

---

## FASE 2 — Agenda y turnos online

> C-05 y C-12 pueden proponerse en paralelo (dominios independientes tras C-03). C-05 debe archivarse antes de C-06.

### [C-05] `catalogo-agenda`
- **Estado**: `[x]` completado (archivado 2026-10-04)
- **Scope**: Configuración de agenda — profesionales, sillones, prestaciones, bloqueos (US-001)
  - Modelos: `Profesional` (matrícula, especialidades, `duracion_default_min`, *──* prestaciones habilitadas), `Sillon` (recurso de primera clase, `sucursal_id?`), `Prestacion` (`duracion_min>0`, buffer, `requiere_sillon`, `permite_sobreturno`, `seña_obligatoria`, `monto_seña`, `anticipacion_min_cancel_hs`, precio ARS), `Bloqueo` (profesional?/sillón?, rango, motivo)
  - Endpoints CRUD: `/profesionales`, `/sillones`, `/prestaciones`, `/bloqueos` (cambio de duración no altera turnos ya creados RN-AG-03)
  - Generador de huecos: múltiplos de duración sobre grilla del profesional descontando turnos + bloqueos (RN-AG-04)
  - Migración 003: tablas `profesional`, `sillon`, `prestacion`, `profesional_prestacion`, `bloqueo`
  - Seed: prestaciones ejemplo (consulta 30', limpieza 45', conducto 90', corona 60', ortodoncia control 30'), 1 sillón "Box 1", 1 profesional demo, feriados nacionales AR como bloqueos
  - Tests: CRUD + aislamiento tenant, huecos descuentan bloqueos/turnos, duración inmutable en turnos existentes
- **Dependencias**: C-03
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §profesional + §sillon + §prestacion + §bloqueo + §Seed data inicial
  - `knowledge-base/05_reglas_de_negocio.md` §RN-AG-03 + §RN-AG-04 + §RN-AG-05
  - `knowledge-base/06_funcionalidades.md` §US-001
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados (exclusión, RBAC)

---

### [C-06] `turnos-antissolapamiento`
- **Estado**: `[ ]` pendiente
- **Scope**: Núcleo de turnos con anti-solapamiento en base + ciclo de vida + sobreturnos (US-002, US-003)
  - Modelo `Turno`: `paciente_id`, `profesional_id`, `sillon_id`, `prestacion_id`, `inicio`, `fin = inicio + duracion + buffer` (RN-AG-03), `estado (reservado|confirmado|en_sala|atendido|cancelado|ausente)`, `origen (mostrador|online|wa|lista_espera)`, `token_portal`, flag `sobreturno`
  - Constraints de exclusión Postgres por (`profesional_id`, rango) y (`sillon_id`, rango) — RN-AG-01/02 garantizadas en base, nunca solo en código
  - Endpoints: `POST /turnos` (rechaza solape/bloqueo con motivo RN-AG-05), `PATCH /turnos/{id}/estado`, `POST /turnos/{id}/reprogramar` (valida RN-AG-01/02/05 en destino, traslada seña RN-AG-07), `POST /turnos/{id}/cancelar` (antelación por prestación RN-AG-08), `POST /turnos/sobreturno` (solo `permite_sobreturno` + rol recepción o superior RN-AG-06/RN-G-03, marcado visible, sin grilla)
  - `GET /turnos/agenda?vista=dia|semana&profesional_id|sillon_id` con estados y estado de cobro visible (patrón FLAP)
  - Migración 004: tabla `turno` + constraints de exclusión + índices `(tenant_id, profesional_id, inicio)`, `(tenant_id, sillon_id, inicio)`, `(tenant_id, estado, inicio)`
  - Tests: solape profesional y sillón rechazados a nivel DB, bloqueo rechaza con motivo, sobreturno sin permiso denegado, reprogramación traslada seña, 409 ante carrera por el mismo hueco
- **Dependencias**: C-05
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §turno
  - `knowledge-base/05_reglas_de_negocio.md` §RN-AG-01 + §RN-AG-02 + §RN-AG-06 + §RN-AG-07 + §RN-AG-08 + §RN-G-03
  - `knowledge-base/06_funcionalidades.md` §US-002 + §US-003
  - `knowledge-base/07_flujos_principales.md` §Flujo 5 (cancelación y auto-relleno)

---

### [C-07] `agenda-mostrador-ui`
- **Estado**: `[ ]` pendiente
- **Scope**: Agenda del mostrador — vistas día/semana + operatoria de recepción (frontend de US-002/US-003)
  - `features/agenda`: vista día y semana por profesional y por sillón, con estados y cobros visibles
  - Crear turno solo en huecos válidos (solape/bloqueo rechazados con mensaje + motivo), sobreturno con confirmación de rol
  - Acciones: confirmar, en-sala, atender, cancelar, reprogramar, marcar ausente — contra endpoints de C-06
  - Tests: render por rol recepción, creación en hueco válido/inválido, flujo de estados
- **Dependencias**: C-06, C-04
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-002 + §US-003
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios (frontend)
  - `knowledge-base/03_actores_y_roles.md` (recepcionista)
  - `knowledge-base/07_flujos_principales.md` §Flujo 4 (cobro en mostrador)

---

### [C-08] `turnero-online-publico`
- **Estado**: `[ ]` pendiente
- **Scope**: Reserva online 24/7 por enlace + portal del paciente (US-010)
  - `GET /reservar/{slug}` (público, rate-limit + captcha, sin cuenta — nombre + WhatsApp válido RN-TU-01): prestaciones → profesionales habilitados → huecos válidos
  - `POST /reservar/{slug}/turnos` — crea `reservado`; carrera por hueco → 409 + alternativas + oferta de lista de espera (Flujo 1)
  - `GET /p/{token}` + `POST /p/{token}/cancelar|reprogramar` hasta `anticipacion_min_cancel_hs` (RN-TU-03); política de cancelación visible al reservar
  - Sin confirmación antes del umbral → se libera el hueco (RN-TU-02); turnero online nunca ofrece sobreturnos (RN-G-03)
  - Frontend público responsive del turnero + portal (sin cuenta obligatoria)
  - Sin migración nueva (usa `token_portal` de 004)
  - Tests: reserva sin cuenta, 409 con carrera concurrente, cancelación dentro/fuera de plazo, rate-limit + captcha
- **Dependencias**: C-06
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §RN-TU-01 + §RN-TU-02 + §RN-TU-03 + §RN-G-03
  - `knowledge-base/06_funcionalidades.md` §US-010
  - `knowledge-base/07_flujos_principales.md` §Flujo 1 (reserva online con seña)
  - `knowledge-base/03_actores_y_roles.md` §Rutas públicas

---

### [C-09] `lista-espera-autorelleno`
- **Estado**: `[ ]` pendiente
- **Scope**: Lista de espera con oferta por orden y auto-relleno (US-012)
  - Modelo `ListaEspera`: `paciente_id`, `prestacion_id`, `profesional_id?`, `franja_preferida`, `estado (activa|ofrecida|convertida|vencida)`
  - Endpoints: `POST /lista-espera`, `GET /lista-espera`, worker ante hueco liberado: ofrece al compatible más antiguo (RN-TU-05) con vencimiento → pasa al siguiente; aceptación → turno normal con todas sus reglas
  - Migración 005: tabla `lista_espera`
  - Tests: orden por antigüedad/preferencia, vencimiento rota al siguiente, conversión respeta RN-AG-01/02/05
- **Dependencias**: C-06, C-08
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §lista_espera
  - `knowledge-base/05_reglas_de_negocio.md` §RN-TU-05
  - `knowledge-base/06_funcionalidades.md` §US-012
  - `knowledge-base/07_flujos_principales.md` §Flujo 5 (cancelación y auto-relleno)

---

## FASE 3 — Pagos y notificaciones

> C-10 y C-11 son independientes entre sí (ambos dependen solo de C-06): pueden proponerse en paralelo.

### [C-10] `cobros-mercadopago`
- **Estado**: `[ ]` pendiente
- **Scope**: Señas con Mercado Pago vinculadas al turno + caja de mostrador backend (US-011, parte cobros de US-040)
  - `POST /turnos/{id}/orden-senia` — crea orden MP si `seña_obligatoria`; turno queda `reservado-pendiente-pago` (RN-TU-04)
  - `POST /webhooks/mercadopago` (firma MP) — acredita o vence: acreditada → `confirmado`; vencida/sin pago → anula y libera hueco (RN-AD-04, RN-G-02: la agenda manda)
  - Idempotencia por `mp_payment_id` único ante IPN duplicado (Flujo 4); cancelación en término devuelve seña o la deja como crédito según política (RN-AD-03)
  - `POST /cobros` (efectivo/transferencia/MP) + recibo + actualización de cuenta corriente; `GET /turnos` expone estado de cobro (patrón FLAP)
  - Credenciales MP solo en backend/vault, nunca en frontend
  - Migración 006: tablas `cobro` (`turno_id?`, `medio`, `monto`, `estado`, `mp_payment_id` único)
  - Tests: checkout → webhook acredita, IPN duplicado idempotente, vencimiento libera hueco, política de seña al cancelar
- **Dependencias**: C-06
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §RN-TU-04 + §RN-AD-03 + §RN-AD-04 + §RN-G-02
  - `knowledge-base/06_funcionalidades.md` §US-011
  - `knowledge-base/07_flujos_principales.md` §Flujo 1 + §Flujo 4 (cobro en mostrador)
  - `knowledge-base/02_descripcion_general.md` §Integraciones externas (Mercado Pago)

---

### [C-11] `notificaciones-whatsapp`
- **Estado**: `[ ]` pendiente
- **Scope**: Automatización WhatsApp Business API full-cycle + email fallback + worker (US-020, US-021)
  - Infra `whatsapp_bsp` (Business API oficial del tenant — nunca números personales ni API no oficial RN-NO-05) + `smtp`; plantillas aprobadas versionadas
  - Worker (Celery + Redis o APScheduler): recordatorios T-48h/T-24h configurables (`REMINDER_T48H_HS`, `REMINDER_T24H_HS`) por WA + email respaldo (RN-NO-01); registra `recordatorio` enviado
  - `POST /webhooks/whatsapp` — confirmación por botón/palabra clave → `confirmado` + `confirmado_at` auditado (RN-NO-02); sin confirmación al umbral → aviso a recepción + oferta a lista de espera
  - Recall: ausente → mensaje a 7 días + reprogramación; doble ausencia → flag exige-seña (RN-NO-03); controles periódicos por intervalo de prestación (RN-NO-04)
  - Reintento con backoff + fallback email + alerta operativa ante fallo BSP (Flujo 2)
  - Migración 007: tablas `recordatorio` (`turno_id`, `canal`, `plantilla`, `enviar_at`, `estado`, `confirmado_at?`), `plantilla_mensaje`
  - Seed: plantillas WA/email + política de cancelación por defecto
  - Tests: envío en ventanas, confirmación cambia estado, recall a 7 días, doble ausencia exige seña, reintento ante fallo BSP
- **Dependencias**: C-06
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §RN-NO-01 + §RN-NO-02 + §RN-NO-03 + §RN-NO-04 + §RN-NO-05
  - `knowledge-base/06_funcionalidades.md` §US-020 + §US-021
  - `knowledge-base/07_flujos_principales.md` §Flujo 2 (confirmación y recordatorios)
  - `knowledge-base/02_descripcion_general.md` §Integraciones externas (WhatsApp/SMTP)

---

## FASE 4 — Clínica odontológica

> C-12 es independiente de la FASE 2 (solo depende de C-03): puede proponerse en paralelo con C-05.

### [C-12] `pacientes-hce`
- **Estado**: `[ ]` pendiente
- **Scope**: Pacientes + historia clínica única con evoluciones append-only (US-030)
  - Modelos: `Paciente` (nombre, dni?, teléfono WA, obra_social? reservado, `consentimiento_datos` bool + fecha), `HistoriaClinica` (1 por paciente por tenant), `Evolucion` append-only con autor + fecha (corrección = nueva entrada que referencia la anterior RN-HC-01)
  - Endpoints: CRUD `/pacientes`, `/historias-clinicas`, `POST /historias-clinicas/{id}/evoluciones` (sin edición destructiva)
  - Visibilidad: solo tratantes + propietario o derivación explícita registrada (RN-SE-02); recepción/asistente no tocan evoluciones (RN-SE-03)
  - Migración 008: tablas `paciente`, `historia_clinica`, `evolucion`
  - Tests: unicidad HCE por paciente/tenant, append-only (update directo rechazado), visibilidad cruzada denegada salvo propietario/derivación
- **Dependencias**: C-03
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §paciente / historia_clinica / odontograma
  - `knowledge-base/05_reglas_de_negocio.md` §RN-HC-01 + §RN-SE-02 + §RN-SE-03
  - `knowledge-base/06_funcionalidades.md` §US-030
  - `knowledge-base/07_flujos_principales.md` §Flujo 3 (atención con HCE)
  - `knowledge-base/10_preguntas_abiertas.md` (SU-04: alcance regulatorio a validar con asesor legal)

---

### [C-13] `odontograma-adjuntos`
- **Estado**: `[ ]` pendiente
- **Scope**: Odontograma FDI por eventos + adjuntos RX/fotos + consentimientos firmados (US-031, consentimientos de US-032)
  - Modelo `Odontograma` (1 por historia) + `EventoPieza`: pieza FDI + superficie + estado (`sano|caries|obturación|corona|endodoncia|extracción|implante|sellador`) + fecha + autor (RN-HC-02)
  - Endpoints: `GET /odontogramas/{historia_id}`, `POST /odontogramas/{historia_id}/eventos`, `POST /historias-clinicas/{id}/adjuntos` (rx|foto|documento → storage privado con URLs firmadas; adjuntos a la historia, nunca al turno RN-HC-05)
  - `Consentimiento`: tipo, firma (hash + timestamp + IP/dispositivo), PDF generado; requerido para planes invasivos (RN-HC-04)
  - Endpoints: `POST /consentimientos`, `GET /consentimientos/{id}/pdf`
  - Migración 009: tablas `odontograma`, `evento_pieza`, `adjunto`, `consentimiento`
  - Tests: eventos FDI con autor/fecha, adjunto con URL firmada expirable, consentimiento con hash verificable
- **Dependencias**: C-12
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §paciente / historia_clinica / odontograma + §consentimiento / adjunto / recordatorio
  - `knowledge-base/05_reglas_de_negocio.md` §RN-HC-02 + §RN-HC-04 + §RN-HC-05
  - `knowledge-base/06_funcionalidades.md` §US-031
  - `knowledge-base/07_flujos_principales.md` §Flujo 3 (atención con HCE)

---

### [C-14] `presupuestos-planes`
- **Estado**: `[ ]` pendiente
- **Scope**: Presupuestos sobre odontograma → plan por etapas + deuda en cuenta corriente (US-032)
  - Modelo `Presupuesto`: items (prestación + pieza + importe ARS RN-AD-01), total, `estado (borrador|enviado|aceptado|rechazado)`, `validez_hasta`; enlaza a piezas del odontograma (patrón Bilog RN-HC-03)
  - Aceptación → genera `PlanTratamiento` por etapas + deuda exigible en cuenta corriente del paciente (RN-AD-02)
  - Planes invasivos exigen consentimiento firmado previo (RN-HC-04, verifica C-13)
  - Endpoints: CRUD `/presupuestos`, `POST /presupuestos/{id}/enviar|aceptar|rechazar`, `GET /planes-tratamiento`
  - Migración 010: tablas `presupuesto`, `presupuesto_item`, `plan_tratamiento`, `cuenta_corriente`, `movimiento_cc`
  - Tests: aceptado genera plan + deuda exacta, invasivo sin consentimiento bloqueado, importes siempre en ARS
- **Dependencias**: C-13
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §presupuesto / plan_tratamiento / cobro
  - `knowledge-base/05_reglas_de_negocio.md` §RN-HC-03 + §RN-HC-04 + §RN-AD-01 + §RN-AD-02
  - `knowledge-base/06_funcionalidades.md` §US-032
  - `knowledge-base/07_flujos_principales.md` §Flujo 3 (atención con HCE)

---

### [C-15] `clinica-caja-ui`
- **Estado**: `[ ]` pendiente
- **Scope**: Frontend clínico + cobro de saldos en mostrador (UI de US-030/031/032 y cobros de C-10/C-14)
  - `features/clinica`: HCE + evoluciones (solo lectura según rol), odontograma FDI interactivo por pieza/superficie, adjuntos RX/fotos, armado y envío de presupuestos, firma de consentimientos
  - `features/caja` (mostrador): deuda/turno con estado de cobro MP, cobro de saldo (efectivo/transferencia/MP) + recibo, cierre de caja diario vs. turnos atendidos
  - Cierre de turno como `atendido` + agenda de control (recall futuro) desde la ficha
  - Tests: odontograma interactivo, presupuesto→aceptar, cobro de saldo, guards (recepción no edita clínica)
- **Dependencias**: C-14, C-10, C-04
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-030 + §US-031 + §US-032
  - `knowledge-base/07_flujos_principales.md` §Flujo 3 + §Flujo 4
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios (frontend)
  - `knowledge-base/03_actores_y_roles.md` (odontólogo, recepción, asistente)

---

## FASE 5 — Cierre MVP

### [C-16] `caja-reportes`
- **Estado**: `[ ]` pendiente
- **Scope**: Reportes operativos del dueño + cierre de caja (resto de US-040)
  - `GET /reportes/ocupacion`, `/ausentismo` (cancelaciones/ausencias), `/recaudacion` (por profesional, incluye señas pendientes y deuda de planes si C-14 ✓), `/senias-pendientes`
  - Agregaciones multi-tenant eficientes (índices de 004); `R total` vs `R operativo` vs `R propio` según rol
  - UI de reportes en `features/reportes` (densidad profesional bien resuelta, referencia CareStack/Curve)
  - Tests: cifras cuadran con turnos/cobros seed, scoping por tenant y por rol
- **Dependencias**: C-10, C-14
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-040
  - `knowledge-base/05_reglas_de_negocio.md` §RN-AD-01
  - `knowledge-base/07_flujos_principales.md` §Flujo 4 (cobro en mostrador)
  - `knowledge-base/04_modelo_de_datos.md` §presupuesto / plan_tratamiento / cobro + §turno (índices)

---

### [C-17] `auditoria-exportacion`
- **Estado**: `[ ]` pendiente
- **Scope**: Auditoría append-only + exportación total de datos (US-041, diferencial DD-06)
  - Middleware/decorador de auditoría: accesos a HCE, cambios de agenda, cobros, exportaciones → tabla `audit_evento` append-only (RN-SE-05)
  - `POST /admin/exportacion` → worker genera paquete (pacientes, turnos, HCE, cobros) en formato abierto + descarga con evento auditado (Flujo 6, RN-SE-04)
  - `GET /admin/auditoria` (propietario): consulta de eventos sensibles
  - Migración 011: tabla `audit_evento`
  - Tests: evento sensible queda registrado e inmutable, exportación contiene todo el dominio del tenant y nada de otros
- **Dependencias**: C-10, C-14
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SE-04 + §RN-SE-05
  - `knowledge-base/06_funcionalidades.md` §US-041
  - `knowledge-base/07_flujos_principales.md` §Flujo 6 (exportación)
  - `knowledge-base/08_arquitectura_propuesta.md` §Seguridad + §Patrones aplicados (audit)

---

## FASE 6 — Etapa 2: preparación (fuera del MVP)

> Los changes de esta fase NO entran en el camino crítico ni en el GATE del MVP. Reservan esquema y dejan stubs para no bloquear la etapa 2 (FE ARCA, OO.SS., ReNaPDiS, IA, marketplace, API pública).

### [C-18] `esquema-etapa2-reserva`
- **Estado**: `[ ]` pendiente
- **Scope**: Reserva de esquema etapa 2 sin implementar integraciones (US-042 + Épica 6 como alcance declarado no-MVP)
  - Migración 012 (solo columnas/tablas reservadas, sin lógica): `paciente.obra_social`, tablas stub `nomenclador`, `comprobante_fiscal` (RN-AD-05)
  - Stubs documentados (endpoints 501 + ADRs): FE ARCA, liquidaciones OO.SS./prepagas, recetario ReNaPDiS (moat ClinIA #248), IA práctica (notas por voz, no-show scoring), perfil público/reseñas, API pública, radiología/laboratorio
  - ADR que declara qué queda explícitamente fuera de v1.0 (DD-02) y el plan de activación por stub
  - Tests: columnas reservadas existen y son nulables (no rompen MVP), stubs responden 501 con mensaje de etapa
- **Dependencias**: C-14
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §RN-AD-05
  - `knowledge-base/06_funcionalidades.md` §US-042 + §Épica 6 (diferenciadores futuros)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-02
  - `knowledge-base/10_preguntas_abiertas.md` (E2: API pública, periodontograma, Google Calendar)
