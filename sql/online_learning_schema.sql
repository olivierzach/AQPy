CREATE TABLE IF NOT EXISTS online_training_state (
    model_name TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    last_seen_ts TIMESTAMPTZ NOT NULL,
    last_trained_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_time_col TEXT NOT NULL,
    source_target_col TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS online_training_metrics (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_target_col TEXT NOT NULL,
    train_rows INTEGER NOT NULL,
    holdout_rows INTEGER NOT NULL,
    holdout_mae DOUBLE PRECISION NOT NULL,
    holdout_rmse DOUBLE PRECISION NOT NULL,
    baseline_mae DOUBLE PRECISION NOT NULL,
    baseline_rmse DOUBLE PRECISION NOT NULL,
    mae_improvement_pct DOUBLE PRECISION NOT NULL,
    rmse_improvement_pct DOUBLE PRECISION NOT NULL,
    learning_rate DOUBLE PRECISION NOT NULL,
    batch_size INTEGER NOT NULL,
    epochs INTEGER NOT NULL,
    new_rows_since_last INTEGER NOT NULL,
    update_from_ts TIMESTAMPTZ,
    update_to_ts TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_online_training_metrics_model_time
    ON online_training_metrics (model_name, recorded_at DESC);

CREATE TABLE IF NOT EXISTS retention_runs (
    id BIGSERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_name TEXT NOT NULL,
    source_database TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_time_col TEXT NOT NULL,
    rows_deleted BIGINT NOT NULL,
    delete_cutoff TIMESTAMPTZ NOT NULL,
    retention_days INTEGER NOT NULL,
    safety_hours INTEGER NOT NULL
);
