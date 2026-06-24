-- 0007_retention: log de gobernanza del ciclo de conservación (REQ-03).
-- REQ-03: conservación 4 años. El job de retención NUNCA borra registros < 4 años; los que
--         cruzan el umbral quedan marcados como 'eligible' y registrados aquí. El borrado
--         físico de time_record está bloqueado por su trigger anti-mutación (inmutabilidad,
--         Reglas de Oro #1/#4): este log es la prueba de que el ciclo de retención se siguió.
-- MUTABLE: es un log operativo, NO parte del ledger legal (no append-only, sin trigger).
-- Idempotente.

CREATE TABLE IF NOT EXISTS retention_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name  text NOT NULL,
    record_id   uuid NOT NULL,
    -- Trabajador dueño del registro afectado.
    -- DECISIÓN DIFERIDA (ver docs/DEFERRED.md): el borrado físico de time_record está fuera de
    -- alcance por ahora. Cuando se implemente, revisar el ON DELETE de este FK para que un
    -- borrado legítimo tras los 4 años de retención NI se bloquee NI deje el log huérfano. La
    -- dirección probable es ON DELETE SET NULL, de modo que el log de gobernanza SOBREVIVA al
    -- borrado del registro que referencia (el log es la prueba de que la retención se cumplió y
    -- debe perdurar más que el registro borrado). No se cambia el esquema ahora.
    worker_id   uuid REFERENCES worker(id),
    -- Fecha del registro afectado y su antigüedad en días al loguear.
    occurred_at timestamptz NOT NULL,
    age_days    integer NOT NULL,
    action      text NOT NULL DEFAULT 'eligible',
    -- Quién ejecuta un borrado posterior (nullable: 'eligible' lo emite el job, sin actor).
    executed_by uuid REFERENCES worker(id),
    reason      text,
    logged_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT retention_log_action_check
        CHECK (action IN ('eligible','deleted'))
);

CREATE INDEX IF NOT EXISTS retention_log_logged_idx ON retention_log (logged_at DESC);
-- Evita duplicar el marcado 'eligible' del mismo registro en ejecuciones repetidas del job.
CREATE UNIQUE INDEX IF NOT EXISTS retention_log_eligible_key
    ON retention_log (table_name, record_id, action);
