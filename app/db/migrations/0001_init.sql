-- 0001_init: baseline. Extensiones y control de migraciones.
-- Idempotente: se puede reaplicar sin efectos.

-- pgcrypto -> gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Registro de migraciones aplicadas (lo usa el runner app/db/migrate.py).
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

-- Stubs de auth.uid()/auth.jwt() para que las POLÍTICAS RLS sean creables en un
-- Postgres plano (dev/tests). En Supabase estas funciones YA existen, así que solo
-- las creamos si faltan (no-op en Supabase). En Fase 0 devuelven NULL: el wiring de
-- claims llega en Fase 1; mientras tanto la app conecta como owner (bypassa RLS) y
-- el control de acceso lo hace la capa de aplicación.
CREATE SCHEMA IF NOT EXISTS auth;

DO $$
BEGIN
    IF to_regprocedure('auth.uid()') IS NULL THEN
        CREATE FUNCTION auth.uid() RETURNS uuid
            LANGUAGE sql STABLE AS $fn$ SELECT NULL::uuid $fn$;
    END IF;
    IF to_regprocedure('auth.jwt()') IS NULL THEN
        CREATE FUNCTION auth.jwt() RETURNS jsonb
            LANGUAGE sql STABLE AS $fn$ SELECT NULL::jsonb $fn$;
    END IF;
END $$;
