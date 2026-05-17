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

CREATE TABLE IF NOT EXISTS garch_forecasts (
    id BIGSERIAL PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    forecast_for TIMESTAMPTZ NOT NULL,
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    target TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    horizon_step INTEGER NOT NULL CHECK (horizon_step > 0),
    yhat_mean DOUBLE PRECISION NOT NULL,
    yhat_variance DOUBLE PRECISION NOT NULL CHECK (yhat_variance >= 0),
    yhat_volatility DOUBLE PRECISION NOT NULL CHECK (yhat_volatility >= 0)
);

CREATE INDEX IF NOT EXISTS idx_garch_forecasts_lookup
    ON garch_forecasts (target, model_name, forecast_for DESC);

CREATE TABLE IF NOT EXISTS anomaly_events (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_time TIMESTAMPTZ NOT NULL,
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    target TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    is_anomaly BOOLEAN NOT NULL,
    method TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_anomaly_events_lookup
    ON anomaly_events (target, model_name, event_time DESC);

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
