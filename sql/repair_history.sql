-- Additive publication of independently validated historical repairs.
SET lock_timeout = '2s';
SET statement_timeout = '15s';
CREATE SCHEMA IF NOT EXISTS history_repair;
CREATE TABLE IF NOT EXISTS history_repair.runs (
    run_id TEXT PRIMARY KEY,
    evidence_sha256 TEXT NOT NULL,
    validation JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS history_repair.predictions (
    run_id TEXT NOT NULL REFERENCES history_repair.runs(run_id),
    model_name TEXT NOT NULL,
    repair_key TEXT NOT NULL,
    original_id BIGINT,
    generated_at TIMESTAMPTZ NOT NULL,
    predicted_for TIMESTAMPTZ NOT NULL,
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    target TEXT NOT NULL,
    horizon_step INTEGER NOT NULL CHECK (horizon_step > 0),
    raw_yhat DOUBLE PRECISION NOT NULL CHECK (raw_yhat > '-Infinity'::float8 AND raw_yhat < 'Infinity'::float8),
    yhat DOUBLE PRECISION NOT NULL CHECK (yhat > '-Infinity'::float8 AND yhat < 'Infinity'::float8),
    baseline DOUBLE PRECISION NOT NULL CHECK (baseline > '-Infinity'::float8 AND baseline < 'Infinity'::float8),
    actual DOUBLE PRECISION CHECK (actual IS NULL OR (actual > '-Infinity'::float8 AND actual < 'Infinity'::float8)),
    actual_at TIMESTAMPTZ,
    train_cutoff TIMESTAMPTZ NOT NULL,
    provenance TEXT NOT NULL,
    output_policy TEXT NOT NULL,
    alignment TEXT NOT NULL,
    PRIMARY KEY(run_id,model_name,repair_key),
    CHECK (generated_at < predicted_for AND train_cutoff <= generated_at),
    CHECK ((actual IS NULL) = (actual_at IS NULL)),
    CHECK (actual_at IS NULL OR actual_at > generated_at)
);
CREATE INDEX IF NOT EXISTS repair_history_original ON history_repair.predictions(original_id) WHERE original_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS repair_history_time ON history_repair.predictions(model_name,predicted_for);
CREATE TABLE IF NOT EXISTS history_repair.unresolved (
    run_id TEXT NOT NULL REFERENCES history_repair.runs(run_id),
    model_name TEXT NOT NULL,
    repair_key TEXT NOT NULL,
    original_id BIGINT,
    reason TEXT NOT NULL,
    PRIMARY KEY(run_id,model_name,repair_key)
);
CREATE INDEX IF NOT EXISTS repair_unresolved_original ON history_repair.unresolved(original_id) WHERE original_id IS NOT NULL;

CREATE OR REPLACE VIEW public.predictions_repaired AS
SELECT p.id AS original_id,p.generated_at,p.predicted_for,p.source_database,p.source_table,
       p.target,p.model_name,p.model_version,p.horizon_step,p.yhat,
       coalesce(p.raw_yhat,p.yhat) AS raw_yhat,p.output_policy,
       'original'::text AS provenance,NULL::text AS repair_run,
       NULL::double precision AS actual,NULL::timestamptz AS actual_at,
       NULL::double precision AS baseline,NULL::timestamptz AS train_cutoff
FROM public.predictions p
WHERE NOT EXISTS (SELECT 1 FROM history_repair.predictions h JOIN history_repair.runs r USING(run_id)
                  WHERE h.original_id=p.id AND r.published_at IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM history_repair.unresolved h JOIN history_repair.runs r USING(run_id)
                  WHERE h.original_id=p.id AND r.published_at IS NOT NULL)
UNION ALL
SELECT h.original_id,h.generated_at,h.predicted_for,h.source_database,h.source_table,
       h.target,h.model_name,('repair:'||h.run_id),h.horizon_step,h.yhat,h.raw_yhat,h.output_policy,
       h.provenance,h.run_id,h.actual,h.actual_at,h.baseline,h.train_cutoff
FROM history_repair.predictions h JOIN history_repair.runs r USING(run_id)
WHERE r.published_at IS NOT NULL;
