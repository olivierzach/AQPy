import re

import numpy as np
from psycopg2.extras import Json


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value):
    if not IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return value


def fetch_series(conn, table, time_col, target_col, history_hours):
    query = f"""
    SELECT {time_col}, {target_col}
    FROM {table}
    WHERE {time_col} >= now() - make_interval(hours => %s)
      AND {target_col} IS NOT NULL
    ORDER BY {time_col} ASC
    """
    with conn.cursor() as cur:
        cur.execute(query, (history_hours,))
        rows = cur.fetchall()
    timestamps = [r[0] for r in rows]
    values = np.array([float(r[1]) for r in rows], dtype=float)
    return timestamps, values


def fetch_recent_series(conn, table, time_col, target_col, n_rows):
    query = f"""
    SELECT {time_col}, {target_col}
    FROM {table}
    WHERE {target_col} IS NOT NULL
    ORDER BY {time_col} DESC
    LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (n_rows,))
        rows = cur.fetchall()
    rows.reverse()
    timestamps = [r[0] for r in rows]
    values = [float(r[1]) for r in rows]
    return timestamps, values


def ensure_registry_table(conn):
    ddl = """
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
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def ensure_predictions_table(conn):
    ddl = """
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
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def register_model(conn, payload):
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


def insert_predictions(conn, payload_rows):
    query = """
    INSERT INTO predictions (
        generated_at,
        predicted_for,
        source_database,
        source_table,
        target,
        model_name,
        model_version,
        horizon_step,
        yhat
    ) VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.executemany(query, payload_rows)
    conn.commit()
