# CLAUDE.md — Fichajes Global Meats

> Guía operativa para Claude Code. Léela completa antes de tocar código.
> El detalle normativo vive en las skills (`.claude/skills/`) y en `docs/compliance/`.

## 1. Qué es esto

Aplicación de **registro de jornada (control horario)** para Global Meats S.L.U.,
desplegada en `fichajes.globalmeats.es`. Sustituye cualquier registro en papel/Excel
por un sistema digital, trazable, inmutable y accesible para Inspección de Trabajo.

Cumple con:
- **Lo legalmente exigible HOY** (RDL 8/2019, art. 34.9 y 35.5 ET). NO negociable.
- **Los requisitos anticipados de la reforma 2026** (digitalización obligatoria,
  sellado temporal, log de modificaciones, acceso remoto, etc.). Diseñamos para
  cumplirlos desde el día 1 aunque la reforma aún no esté en vigor (a 22/06/2026 el
  Decreto-ley sigue sin fecha tras el dictamen crítico del Consejo de Estado del
  23/03/2026). Tratar estos como objetivos de diseño, no como obligación legal vigente.

La fuente de verdad legal es la **Guía oficial del Ministerio de Trabajo** sobre el
registro de jornada y el texto del art. 34.9/35.5 ET. Los blogs comerciales NO son
fuente; tienen sesgo de venta de software.

## 2. Stack (fijado)

- **Backend**: FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.x async.
- **DB / Auth**: Supabase (PostgreSQL) con **Row Level Security (RLS)** obligatorio
  en todas las tablas con datos personales.
- **Frontend**: HTML server-rendered con **Jinja2** (desde FastAPI) + islas de
  interactividad con **Alpine.js** y **htmx**. Sin build de JS. El fichaje se hace desde
  el ordenador de escritorio de cada trabajador (uso personal, red de oficina estable).
  Ver skill `frontend-fichaje`.
- **Auth de trabajador**: **código de empleado + PIN** (los trabajadores NO tienen email).
  El código identifica (inequívoco, REQ-05); el PIN (6 dígitos, hash **bcrypt**) autentica.
  NO biometría (prohibida por AEPD/reforma).
- **Hosting**: Railway. Región **UE** obligatoria (RGPD: datos en servidores UE).
- **Build**: `mise` para gestión de versiones de Python (atención al fallo conocido
  de build Python/mise ya resuelto en el proyecto del wedding site; replicar fix).
- **Frontend**: por confirmar (asunción: SSR ligero o SPA mínima). Las skills no
  asumen framework de front concreto.

## 3. Reglas de oro (violarlas = incumplimiento legal)

1. **Inmutabilidad**: un registro de fichaje NUNCA se actualiza ni se borra in-place.
   Las correcciones se hacen por versionado append-only. Ver skill `audit-trail`.
2. **Sellado temporal**: cada registro lleva timestamp del servidor (UTC) + hash
   encadenado con el registro anterior del mismo trabajador. Ver skill `audit-trail`.
3. **RLS siempre**: ninguna query salta la fila de otro trabajador salvo roles
   autorizados. Ver skill `rgpd-dataguard`.
4. **Conservación 4 años**: ningún job de limpieza borra registros con < 4 años.
5. **Disponibilidad inmediata**: endpoints de exportación (PDF/CSV) y acceso del
   trabajador a SUS registros deben existir y estar siempre operativos.
6. **Datos en la UE**: no mover datos personales fuera de la UE. Verificar región
   de Railway/Supabase antes de cualquier despliegue.
7. **Geolocalización**: solo puntual en el momento del fichaje, jamás continua,
   con consentimiento informado. Opcional por configuración.

Si una tarea entra en conflicto con cualquiera de estas reglas, **párate y avisa**
antes de implementar.

## 4. Mapa de skills

Consulta la skill correspondiente ANTES de implementar la funcionalidad asociada:

| Skill | Cuándo consultarla |
|-------|--------------------|
| `legal-compliance` | Cualquier decisión sobre QUÉ debe registrar/conservar/exportar el sistema. Matriz de requisitos legales ↔ implementación. |
| `fichaje-domain` | Modelado del dominio: tipos de evento, pausas, horas extra, desplazamientos, jornada flexible, modalidades (presencial/teletrabajo/móvil). |
| `audit-trail` | Inmutabilidad, sellado temporal, hash encadenado, versionado de correcciones, logs. |
| `rgpd-dataguard` | RLS, roles, cifrado, retención, geolocalización, consentimiento, derechos del trabajador. |
| `fastapi-supabase` | Convenciones de implementación del stack: estructura, migraciones, RLS en Supabase, patrones async. |
| `frontend-fichaje` | UI: pantallas (login código+PIN, fichar, mis registros, admin), Jinja2 + Alpine/htmx, cronómetro, offline ligero. |
| `onboarding-empleados` | Alta de trabajadores: generación de código de empleado sin colisiones, PIN inicial aleatorio mostrado una vez, cambio de PIN obligatorio en primer login. |

## 5. Flujo de trabajo con Claude Code

1. Lee este `CLAUDE.md`. Al planificar una nueva fase, consulta `docs/DEFERRED.md` (registro de
   decisiones diferidas y deuda técnica) para reconsiderar los pendientes en el momento oportuno.
2. Identifica qué requisito(s) toca la tarea → abre `legal-compliance`.
3. Abre la(s) skill(s) técnica(s) implicadas.
4. Implementa siguiendo los patrones de `fastapi-supabase`.
5. Antes de cerrar la tarea, corre el checklist de `legal-compliance/scripts/compliance_check.py`.
6. Commit con referencia al requisito (ej: `feat(fichaje): sellado templa [REQ-15]`).

## 6. Orden de construcción sugerido (roadmap)

Ver `docs/IMPLEMENTATION_PLAN.md` para el desglose por fases con criterios de
aceptación atados a cada requisito legal.
