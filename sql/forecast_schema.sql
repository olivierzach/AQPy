CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    predicted_for TIMESTAMPTZ NOT NULL,
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    target TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    horizon_step INTEGER NOT NULL CHECK (horizon_step > 0),
    yhat DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_predictions_lookup
    ON predictions (target, model_name, predicted_for DESC);

CREATE TABLE IF NOT EXISTS model_registry (
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    trained_at TIMESTAMPTZ NOT NULL,
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    target TEXT NOT NULL,
    metrics JSONB NOT NULL,
    artifact_path TEXT NOT NULL,
    PRIMARY KEY (model_name, model_version)
);
