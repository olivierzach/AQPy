from psycopg2.extras import Json


def ensure_online_tables(conn):
    ddl = """
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
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def get_training_state(conn, model_name):
    query = """
    SELECT model_name, model_version, artifact_path, last_seen_ts
    FROM online_training_state
    WHERE model_name = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (model_name,))
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "model_name": row[0],
        "model_version": row[1],
        "artifact_path": row[2],
        "last_seen_ts": row[3],
    }


def upsert_training_state(
    conn,
    model_name,
    model_version,
    artifact_path,
    last_seen_ts,
    source_database,
    source_table,
    source_time_col,
    source_target_col,
):
    query = """
    INSERT INTO online_training_state (
        model_name,
        model_version,
        artifact_path,
        last_seen_ts,
        last_trained_at,
        source_database,
        source_table,
        source_time_col,
        source_target_col
    )
    VALUES (%s, %s, %s, %s, now(), %s, %s, %s, %s)
    ON CONFLICT (model_name) DO UPDATE
    SET model_version = EXCLUDED.model_version,
        artifact_path = EXCLUDED.artifact_path,
        last_seen_ts = EXCLUDED.last_seen_ts,
        last_trained_at = now(),
        source_database = EXCLUDED.source_database,
        source_table = EXCLUDED.source_table,
        source_time_col = EXCLUDED.source_time_col,
        source_target_col = EXCLUDED.source_target_col
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                model_name,
                model_version,
                artifact_path,
                last_seen_ts,
                source_database,
                source_table,
                source_time_col,
                source_target_col,
            ),
        )
    conn.commit()


def insert_training_metric(conn, metric_row):
    query = """
    INSERT INTO online_training_metrics (
        model_name,
        model_version,
        source_database,
        source_table,
        source_target_col,
        train_rows,
        holdout_rows,
        holdout_mae,
        holdout_rmse,
        baseline_mae,
        baseline_rmse,
        mae_improvement_pct,
        rmse_improvement_pct,
        learning_rate,
        batch_size,
        epochs,
        new_rows_since_last,
        update_from_ts,
        update_to_ts
    )
    VALUES (%(model_name)s, %(model_version)s, %(source_database)s, %(source_table)s,
            %(source_target_col)s, %(train_rows)s, %(holdout_rows)s, %(holdout_mae)s,
            %(holdout_rmse)s, %(baseline_mae)s, %(baseline_rmse)s, %(mae_improvement_pct)s,
            %(rmse_improvement_pct)s, %(learning_rate)s, %(batch_size)s, %(epochs)s,
            %(new_rows_since_last)s, %(update_from_ts)s, %(update_to_ts)s)
    """
    with conn.cursor() as cur:
        cur.execute(query, metric_row)
    conn.commit()


def count_new_rows(conn, table, time_col, since_ts):
    query = f"SELECT COUNT(*) FROM {table} WHERE {time_col} > %s"
    with conn.cursor() as cur:
        cur.execute(query, (since_ts,))
        return int(cur.fetchone()[0])


def insert_or_update_model_registry(conn, payload):
    query = """
    INSERT INTO model_registry (
        model_name,
        model_version,
        trained_at,
        source_database,
        source_table,
        target,
        metrics,
        artifact_path
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (model_name, model_version) DO UPDATE
    SET metrics = EXCLUDED.metrics,
        artifact_path = EXCLUDED.artifact_path
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                payload["model_name"],
                payload["model_version"],
                payload["trained_at"],
                payload["database"],
                payload["table"],
                payload["target"],
                Json(payload["metrics"]),
                payload["artifact_path"],
            ),
        )
    conn.commit()


def get_min_last_seen_ts(conn, model_name=None):
    if model_name:
        query = """
        SELECT MIN(last_seen_ts)
        FROM online_training_state
        WHERE model_name = %s
        """
        params = (model_name,)
    else:
        query = "SELECT MIN(last_seen_ts) FROM online_training_state"
        params = ()
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()[0]


def delete_older_than(conn, table, time_col, cutoff):
    query = f"DELETE FROM {table} WHERE {time_col} < %s"
    with conn.cursor() as cur:
        cur.execute(query, (cutoff,))
        deleted = cur.rowcount
    conn.commit()
    return int(deleted)


def insert_retention_run(
    conn,
    model_name,
    source_database,
    source_table,
    source_time_col,
    rows_deleted,
    delete_cutoff,
    retention_days,
    safety_hours,
):
    query = """
    INSERT INTO retention_runs (
        model_name,
        source_database,
        source_table,
        source_time_col,
        rows_deleted,
        delete_cutoff,
        retention_days,
        safety_hours
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                model_name,
                source_database,
                source_table,
                source_time_col,
                rows_deleted,
                delete_cutoff,
                retention_days,
                safety_hours,
            ),
        )
    conn.commit()
