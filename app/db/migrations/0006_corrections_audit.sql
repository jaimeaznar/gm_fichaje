-- 0006_corrections_audit: correcciones versionadas y alertas de auditoría.
-- REQ-16: corrección de un time_record SIN romper la inmutabilidad. Nunca se edita el
--         original; se inserta una fila en record_correction con motivo (obligatorio) y autor.
--         La corrección también es append-only y hash-sellada (cadena propia por trabajador),
--         igual que el ledger time_record: tampoco se puede alterar a posteriori.
-- REQ-25: tabla audit_alert para alertas de manipulación/seguridad (cadena rota, fallos y
--         bloqueos de login, intentos de mutación, accesos anómalos).
-- Reutiliza la función prevent_mutation() creada en 0003. Idempotente.

-- ---- record_correction (REQ-16): corrección versionada, append-only, hash-sellada ----
CREATE TABLE IF NOT EXISTS record_correction (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    original_record_id uuid NOT NULL REFERENCES time_record(id),
    -- Trabajador dueño del registro corregido (cadena de correcciones por trabajador).
    worker_id          uuid NOT NULL REFERENCES worker(id),
    seq                bigint NOT NULL,
    field              text NOT NULL,
    corrected_value    text NOT NULL,
    -- Justificación obligatoria (la reforma exige campo de motivo).
    reason             text NOT NULL,
    -- Quién corrige (admin/supervisor).
    author_id          uuid NOT NULL REFERENCES worker(id),
    -- Hora del servidor (UTC) de la corrección.
    occurred_at        timestamptz NOT NULL,
    prev_hash          text NOT NULL,
    hash               text NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT record_correction_field_check
        CHECK (field IN ('occurred_at','event_type','modalidad','travel_computes','geo'))
);

CREATE UNIQUE INDEX IF NOT EXISTS record_correction_worker_seq_key
    ON record_correction (worker_id, seq);
CREATE UNIQUE INDEX IF NOT EXISTS record_correction_hash_key
    ON record_correction (hash);
CREATE INDEX IF NOT EXISTS record_correction_original_idx
    ON record_correction (original_record_id);

-- Append-only: revoca mutaciones (el superusuario las ignora -> el trigger es la garantía).
REVOKE UPDATE, DELETE ON record_correction FROM PUBLIC;

DROP TRIGGER IF EXISTS no_mutate_record_correction ON record_correction;
CREATE TRIGGER no_mutate_record_correction
  BEFORE UPDATE OR DELETE ON record_correction
  FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- RLS (defensa en profundidad, REQ-24): el trabajador ve las correcciones de SUS registros;
-- la supervisión ve todas.
ALTER TABLE record_correction ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS record_correction_self_select ON record_correction;
CREATE POLICY record_correction_self_select ON record_correction FOR SELECT
    USING ( auth.uid() = worker_id );

DROP POLICY IF EXISTS record_correction_oversight_select ON record_correction;
CREATE POLICY record_correction_oversight_select ON record_correction FOR SELECT
    USING ( (auth.jwt() ->> 'role') IN ('supervisor','admin','rlt','inspeccion') );

-- ---- audit_alert (REQ-25): alertas de manipulación/seguridad ----
-- MUTABLE (no es ledger append-only): en el futuro podrá marcarse como revisada/resuelta.
CREATE TABLE IF NOT EXISTS audit_alert (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type  text NOT NULL,
    worker_id   uuid REFERENCES worker(id),   -- afectado (nullable)
    actor_id    uuid REFERENCES worker(id),   -- quien la provoca (nullable)
    detail      text NOT NULL,
    severity    text NOT NULL DEFAULT 'warning',
    detected_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT audit_alert_type_check
        CHECK (alert_type IN (
            'chain_broken','login_failed','account_locked','mutation_attempt','anomalous_access'
        )),
    CONSTRAINT audit_alert_severity_check
        CHECK (severity IN ('info','warning','critical'))
);

CREATE INDEX IF NOT EXISTS audit_alert_detected_idx ON audit_alert (detected_at DESC);
