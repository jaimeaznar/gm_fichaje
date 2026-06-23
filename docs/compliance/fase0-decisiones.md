# Fase 0 — Decisiones de cumplimiento

Registro de las decisiones de diseño con impacto legal tomadas en la Fase 0
(cimientos). Sirve de base para la DPIA y el registro de actividades de tratamiento.

> No es asesoramiento jurídico. Validar con laboralista/DPO antes de producción.

## Base jurídica del tratamiento (REQ-10 🟢)
- El registro de jornada se ampara en el **cumplimiento de una obligación legal**
  (art. 6.1.c RGPD; art. 34.9 ET). No requiere consentimiento del trabajador para el
  registro en sí.
- **Minimización**: la tabla `worker` solo almacena lo imprescindible para identificar
  y autenticar (nombre, apellido, código, hash de PIN, rol, estado). Sin email, sin
  biometría, sin datos personales no necesarios.

## Residencia de datos en la UE (REQ-23 🟡/base 🟢)
- `app/core/config.py::assert_eu_region()` valida `DEPLOY_REGION` y `SUPABASE_REGION`
  contra una allowlist UE/EEE. El **arranque de la app falla** si no son UE.
- `scripts/check_region.py` repite la verificación en deploy/CI (**exit 1** si no UE).
- **Prerrequisito pendiente**: crear el proyecto **Supabase en región UE** (p. ej.
  Frankfurt / `eu-central-1`) y apuntar `DATABASE_URL` a él. Hasta entonces, dev/tests
  corren sobre Postgres local (docker-compose).

## Identificación y autenticación (REQ-05 🟢, REQ-21 🟡)
- **Identificación inequívoca** = `code_norm` con **UNIQUE en Postgres**
  (`0002_worker.sql`). La unicidad se garantiza en BD, no solo en código; el alta usa
  **reintento transaccional** ante colisión (`services/onboarding.py`).
- **Autenticación** = PIN de 6 dígitos con **hash bcrypt**; nunca en claro ni en logs.
  El PIN inicial se genera con `secrets`, es **no trivial** y se muestra **una sola vez**.
- **Sin biometría** (prohibida por AEPD/reforma).
- **Lockout** por intentos fallidos (PIN corto): columnas `failed_attempts` /
  `locked_until` y bloqueo temporal en `auth.py`. La emisión de `audit_alert` se
  cablea en Fase 4.

## Row Level Security (REQ-24 🟡)
- `worker` tiene **RLS habilitado** y políticas por rol (empleado ve su fila; oversight
  lee global; alta solo admin).
- **Decisión Fase 0**: la **inyección de claims** (`auth.uid()`/`auth.jwt()`) se
  **difiere a Fase 1** (con `time_record`). En Fase 0 la app conecta como owner
  (bypassa RLS) y el control de acceso efectivo lo hace la capa de aplicación
  (`require_role`). Las políticas quedan escritas y probables; se cablearán al introducir
  la inyección de claims por transacción.

## Sellado temporal (REQ-15 🟡) — semilla
- `app/core/time.py` aporta `utc_now()` (hora del servidor en UTC) y `chain_hash()`
  (SHA-256 encadenado). La cadena completa sobre `time_record` se implementa en Fase 1.

## Inmutabilidad — fuera de alcance en Fase 0
- `worker` **no** es append-only (es dato de cuenta, mutable: cambio/reset de PIN). La
  inmutabilidad (REQ-02) aplica a `time_record`, que llega en Fase 1.
