-- 0002_worker: tabla de trabajadores/cuentas.
-- REQ-05: code_norm es la identificación inequívoca -> UNIQUE en BD (garantía real
--         frente a altas concurrentes; el chequeo en Python NO basta).
-- REQ-24: RLS habilitado + políticas por rol.
-- NOTA (Fase 0): las políticas referencian auth.uid()/auth.jwt() (modelo Supabase).
--   En Fase 0 NO inyectamos esos claims en la conexión, así que el control de acceso
--   efectivo lo hace la capa de app; la inyección de claims se cablea en Fase 1.
-- Idempotente.

CREATE TABLE IF NOT EXISTS worker (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code            text NOT NULL,
    code_norm       text NOT NULL,
    first_name      text NOT NULL,
    last_name       text NOT NULL,
    pin_hash        text NOT NULL,
    pin_temporary   boolean NOT NULL DEFAULT true,
    role            text NOT NULL DEFAULT 'empleado',
    is_active       boolean NOT NULL DEFAULT true,
    failed_attempts integer NOT NULL DEFAULT 0,
    locked_until    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid,
    CONSTRAINT worker_role_check
        CHECK (role IN ('empleado','supervisor','admin','rlt','inspeccion'))
);

-- Unicidad de la identificación inequívoca (REQ-05).
CREATE UNIQUE INDEX IF NOT EXISTS worker_code_norm_key ON worker (code_norm);

-- ---- Row Level Security (REQ-24) ----
ALTER TABLE worker ENABLE ROW LEVEL SECURITY;

-- Empleado: solo su propia fila.
DROP POLICY IF EXISTS worker_self_select ON worker;
CREATE POLICY worker_self_select ON worker FOR SELECT
    USING ( auth.uid() = id );

-- Roles de supervisión/oversight: lectura global.
DROP POLICY IF EXISTS worker_oversight_select ON worker;
CREATE POLICY worker_oversight_select ON worker FOR SELECT
    USING ( (auth.jwt() ->> 'role') IN ('supervisor','admin','rlt','inspeccion') );

-- Alta de trabajadores: solo admin.
DROP POLICY IF EXISTS worker_admin_insert ON worker;
CREATE POLICY worker_admin_insert ON worker FOR INSERT
    WITH CHECK ( (auth.jwt() ->> 'role') = 'admin' );

-- Actualización (cambio/reset de PIN, lockout): el propio trabajador o un admin.
DROP POLICY IF EXISTS worker_self_or_admin_update ON worker;
CREATE POLICY worker_self_or_admin_update ON worker FOR UPDATE
    USING ( auth.uid() = id OR (auth.jwt() ->> 'role') = 'admin' );
