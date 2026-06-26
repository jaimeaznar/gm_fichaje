# Plan de implementación — Fichajes Global Meats

Roadmap por fases para construir la app con Claude Code. Cada fase cierra con su
checklist (`compliance_check.py` + tests). Los REQ-XX remiten a la matriz de la skill
`legal-compliance`. 🟢 = obligación legal vigente · 🟡 = objetivo reforma 2026.

## Cómo ejecutar cada fase con Claude Code

Prompt tipo para arrancar una fase:

> "Vamos con la Fase N del plan de fichajes. Lee `CLAUDE.md` y las skills implicadas,
> implementa las tareas de la fase y deja los tests en verde. Antes de cerrar, corre
> `compliance_check.py`."

Claude Code debe abrir las skills que correspondan (no asumir de memoria) y referenciar
el REQ en cada commit.

---

## Fase 0 — Cimientos y cumplimiento de base

**Objetivo**: esqueleto del proyecto + andamiaje de cumplimiento operativo.

- Estructura de carpetas (`fastapi-supabase`).
- `core/config.py` con verificación de **región UE** (REQ-23 🟡).
- `core/security.py`: PIN bcrypt, JWT con `role`/`worker_id` (REQ-05 🟢, 21 🟡).
- **Alta de empleados** (`onboarding-empleados`): generación de `employee_code` sin
  colisiones (UNIQUE en BD + reintento transaccional), PIN inicial aleatorio mostrado una
  vez, `pin_temporary`. Endpoint de admin + cambio de PIN obligatorio en primer login.
- `core/time.py`: utilidades UTC y sellado (REQ-15 🟡).
- Conexión Supabase async; primera migración vacía + RLS habilitado por defecto.
- Integrar `compliance_check.py` en CI.

**Aceptación**: app levanta; login PIN funciona; deploy falla si la región no es UE.

---

## Fase 1 — Registro diario inmutable (núcleo legal vigente)

**Objetivo**: cumplir el mínimo VIGENTE del art. 34.9 con garantías de inmutabilidad.

- Tabla `time_record` append-only (`fichaje-domain`).
- Servicio `audit/chain.py`: timestamp servidor + hash encadenado (REQ-15 🟡).
- Trigger + revoke UPDATE/DELETE (REQ-02 🟢, `audit-trail`).
- Endpoint `POST /fichaje/event` (check_in/check_out) (REQ-01 🟢).
- Reconstrucción de jornada vía máquina de estados (`fichaje-domain`).
- RLS: empleado solo ve lo suyo (REQ-05/24).

**Aceptación**: REQ-01, REQ-02 verdes. UPDATE/DELETE rechazado. Cadena de hash verificable.

---

## Fase 2 — Pausas, desplazamientos y tiempo efectivo

**Objetivo**: distinguir tiempo efectivo del bruto (evita la presunción legal).

- Eventos `break_*` y `travel_*` (REQ-07 🟢, REQ-09 🟢).
- Cálculo de tiempo efectivo (`domain/hours.py`).
- `time_policy` configurable: pausas computables, periodo de cómputo (REQ-13 🟢).
- Modalidades presencial/teletrabajo/móvil (REQ-06 🟢).

**Aceptación**: REQ-06,07,09,13 verdes; pausas no computables no restan; traslado en
puesta a disposición no computa pero queda registrado.

---

## Fase 3 — Horas extra y cómputo flexible

**Objetivo**: art. 35.5 ET + flexibilidad supra-diaria.

- Agregador de horas por periodo (REQ-12 🟢).
- Totalización y resumen de horas extra, flag abono/descanso (REQ-08 🟢).
- Clasificación ordinarias/extra/complementarias (REQ-26 🟡).
- Endpoint `GET /reports/overtime`.

**Aceptación**: REQ-08,12 verdes; exceso diario no es extra si el periodo cuadra;
resumen exportable.

---

## Fase 4 — Correcciones y auditoría

**Objetivo**: editar sin romper la inmutabilidad + detección de manipulación.

- `record_correction` con `reason` obligatorio, autor, referencia al original (REQ-16 🟡).
- Verificador periódico de cadena de hash.
- `audit_alert`: intentos de mutación, cadena rota, accesos anómalos, fallos de login
  (REQ-25 🟡).

**Aceptación**: REQ-16 verde; corrección deja rastro; alertas se generan.

---

## Fase 5 — Acceso, exportación y conservación

**Objetivo**: disponibilidad inmediata + retención.

- Portal del trabajador (sus registros 24/7) (REQ-18 🟡).
- Export PDF/CSV verificable: id, detalle, correcciones, totales (REQ-04 🟢, 19 🟡).
- Acceso de Inspección solo lectura/remoto (REQ-17 🟡); cumple ya el "a disposición"
  vigente (REQ-04 🟢).
- Roles RLT/inspección (REQ-24 🟡).
- Job de retención que NO borra < 4 años y loguea borrados posteriores (REQ-03 🟢).

**Aceptación**: REQ-03,04 verdes; export operativo; retención respeta los 4 años.

---

## Fase 6 — RGPD avanzado y robustez

**Objetivo**: cerrar los objetivos de reforma y el endurecimiento de privacidad.

- Geolocalización puntual con consentimiento y cifrado (REQ-20 🟡).
- Cifrado en reposo de columnas sensibles; verificación de residencia UE (REQ-23 🟡).
- Funcionamiento offline + sync sin pérdida (REQ-22 🟡).
- DPIA y registro de actividades de tratamiento (REQ-10 🟢).
- Excepciones de ámbito: alta dirección, ETT→usuaria, subcontrata (REQ-11 🟢).
- Módulo de desconexión digital (REQ-26 🟡).

**Aceptación**: REQ-10,11 verdes; geo solo puntual; offline sincroniza; DPIA documentada.

---

## Estado de cumplimiento objetivo al cerrar el plan

- **100% de los REQ 🟢 (vigentes)**: obligatorio antes de producción.
- **REQ 🟡 (reforma)**: implementados como objetivo de diseño. Revisar contra el texto
  definitivo cuando se publique en BOE (a 22/06/2026 sigue pendiente).

> Recordatorio: esto es soporte técnico, no asesoramiento jurídico. Validar con
> laboralista antes de producción.


# Fase 7 — Frontend (Jinja2 + Alpine/htmx)

> Plan de implementación de la capa visible para el trabajador y el administrador.
> Stack fijado (skill `frontend-fichaje`): HTML server-rendered con Jinja2 desde FastAPI
> + islas de interactividad con Alpine.js y htmx. Sin build de JS. Uso desde el ordenador
> de escritorio de cada trabajador (uso personal, red de oficina estable).

## Contexto

Fases 0–6 completas: el backend expone toda la lógica (fichaje, tiempo efectivo, horas
extra, correcciones, export, portal `/me/records`, retención, RGPD). Hasta ahora todo se
ha probado vía Swagger. La Fase 7 construye las pantallas que usarán las personas reales,
consumiendo los endpoints que ya existen — **no añade lógica de negocio nueva**, solo la
capa de presentación. El backend es la fuente de verdad; el frontend la refleja.

## Objetivo

Dar a cada trabajador una interfaz para fichar y consultar sus registros, y al
administrador las pantallas de gestión y exportación, cumpliendo la disponibilidad
inmediata (REQ-04) y el acceso permanente del trabajador (REQ-18) a nivel de experiencia
de usuario, no solo de API.

## Requisitos que toca

| REQ | Cómo lo cubre el frontend | Estado |
|-----|---------------------------|--------|
| REQ-01 | Pantalla de fichar (check_in/out, pausas, desplazamientos) | 🟢 |
| REQ-04 | Botones de descarga PDF/CSV siempre accesibles | 🟢 |
| REQ-05 | Login por código de empleado + PIN | 🟢 |
| REQ-18 | Pantalla "mis registros" sobre `/me/records` | 🟡 |
| REQ-24 | Vistas y acciones según rol (empleado/supervisor/admin/inspección) | 🟡 |

## Principios (de la skill `frontend-fichaje`)

- El **estado de jornada lo reconstruye el backend**; el front solo lo muestra. Nunca
  calcular el estado ABIERTA/EN_PAUSA en el cliente.
- El **cronómetro es solo visual**; la hora válida la sella el servidor (REQ-15).
- **Offline = red de seguridad ligera**: si un `POST` de evento falla por red, encolar en
  el navegador con la hora real y reintentar. Sin Service Worker + IndexedDB completo
  (ordenador de oficina, red estable).
- Sin exponer datos de otros trabajadores en una pantalla de empleado (RLS + API ya lo
  garantizan; el front no debe pedir lo que no le corresponde).
- Accesibilidad básica (foco, teclado, etiquetas); trabajadores sin perfil técnico.
- Mensajes en español, claros (jornada ya abierta, transición inválida, bloqueo por PIN).

## Pantallas y criterios de aceptación

### 1. Login (código + PIN) — REQ-05
- Dos campos: código de empleado (recordado en el navegador vía cookie no sensible) y PIN
  (nunca recordado). Botón de fichar deshabilitado hasta autenticar.
- **Aceptación**: login correcto → redirige a fichar; PIN incorrecto → mensaje de error;
  tras N intentos → mensaje de bloqueo temporal (el backend ya emite la alerta).

### 2. Cambio de PIN obligatorio (primer login / reset) — REQ-05
- Si el trabajador tiene `pin_temporary = true`, el login lleva **obligatoriamente** aquí;
  no puede fichar hasta cambiarlo. Pide PIN nuevo dos veces; rechaza triviales y el temporal.
- **Aceptación**: con PIN temporal no se puede acceder a fichar; tras cambiarlo
  (`pin_temporary = false`) → pantalla de fichar.

### 3. Fichar — REQ-01
- Muestra el estado de jornada actual (reconstruido por el backend) y los botones válidos
  según ese estado: check_in / break_start / break_end / travel_start / travel_end /
  check_out. Cronómetro visual de la jornada en curso.
- Envío de evento vía htmx (`POST /fichaje/event`); la respuesta refresca el estado.
- **Aceptación**: la secuencia completa (entrada → pausa → vuelta → salida) funciona y
  refleja el estado correcto; una transición inválida muestra el error 409 de forma legible;
  tras fichar, vuelve a pantalla neutra (sesión corta).

### 4. Mis registros — REQ-18
- Capa visual sobre `GET /me/records`: lista de jornadas del trabajador con detalle diario,
  totales del periodo, y sus correcciones (original + corrección, nunca solo el corregido).
  Filtros por rango de fechas vía htmx. Enlaces de descarga a `/export/records.csv` y `.pdf`.
- **Aceptación**: el trabajador ve solo lo suyo; los totales coinciden con el backend; las
  descargas funcionan; una corrección previa se muestra junto al original.

### 5. Panel admin / export — REQ-04, REQ-24
- Para roles de supervisión: alta de trabajadores (genera código + PIN inicial mostrado una
  vez), edición de `time_policy`, consulta y exportación de registros de cualquier
  trabajador, vista de alertas de auditoría y verificación de cadena bajo demanda.
- **Aceptación**: un empleado no accede al panel (403/redirect); un admin sí; el PIN inicial
  se muestra una sola vez con aviso; la exportación de otro trabajador funciona para
  inspección/admin.

## Mapa de ficheros (orientativo)

| Fichero | Contenido |
|---------|-----------|
| `app/web/__init__.py` · `app/web/router.py` | Router de páginas HTML (separado de la API JSON) |
| `app/web/templates/base.html` | Layout base, carga de Alpine/htmx por `<script>` |
| `app/web/templates/login.html` | Login código + PIN |
| `app/web/templates/change_pin.html` | Cambio de PIN obligatorio |
| `app/web/templates/fichar.html` | Pantalla de fichar + cronómetro (Alpine) |
| `app/web/templates/mis_registros.html` | "Mis registros" sobre `/me/records` |
| `app/web/templates/admin/*.html` | Alta, política, export, alertas |
| `app/web/static/` | Alpine.js, htmx (servidos como estáticos o CDN con SRI) |
| `app/web/session.py` | Sesión de navegador (cookie corta, código recordado) |
| `app/main.py` | Montar el router web junto a los de API |
| `tests/test_web_*.py` | Tests de render, flujos y aislamiento por rol |

## Reutilización (Fases 0–6)

- Toda la lógica ya existe: `/auth/login`, `/auth/change-pin`, `/fichaje/event`,
  `/fichaje/summary`, `/me/records`, `/export/records.{csv,pdf}`, `/admin/*`. El frontend
  **solo consume**; no reimplementa cálculo ni acceso a datos.
- El control de acceso por rol ya está en el backend; las plantillas solo muestran u ocultan
  según el rol del JWT, pero la seguridad real la impone la API + RLS.

## Verificación end-to-end

1. `ruff check .` limpio · `pytest -q` verde (suite previa + tests de render y flujo).
2. Manual en navegador (no solo Swagger): login → cambio de PIN → fichar la secuencia
   completa → mis registros → descargar CSV/PDF. Con rol admin: alta de trabajador, ver el
   PIN una vez, exportar a otro trabajador.
3. Probar la red de seguridad offline: cortar la red, fichar, ver "pendiente de
   sincronizar", restaurar red, confirmar que el evento se registra sin duplicar.
4. Aislamiento: un empleado no puede ver registros ni panel de otro (la API responde 403 y
   la UI lo refleja).
5. `compliance_check.py` sin regresión.
6. Commit por el usuario: `feat(fase7): frontend de fichaje y panel admin [REQ-01,04,05,18,24]`.

## Fuera de alcance (siguiente fase)

- Despliegue a producción (Railway + Supabase UE), variables de entorno de prod, y
  programación de los cron jobs (retención, verificador de cadena).
- Cierre de la compensación de horas extra (abono/descanso, `DEFERRED.md` punto 2).
- Alta inicial de la plantilla real e importación de datos históricos si los hubiera.
- Validación legal del cómputo con laboralista (`DEFERRED.md` punto 1).