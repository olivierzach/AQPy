import datetime as dt
import re
import logging

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value):
    if not IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return value


def compute_delete_cutoff(now_utc, min_last_seen_ts, retention_days, safety_hours):
    retention_cutoff = now_utc - dt.timedelta(days=retention_days)
    safe_cutoff = min_last_seen_ts - dt.timedelta(hours=safety_hours)
    return min(retention_cutoff, safe_cutoff)


def run_retention(
    database,
    table,
    time_col,
    model_name=None,
    retention_days=365,
    safety_hours=12,
    use_training_watermark=True,
):
    from aqpy.common.db import connect_db
    from aqpy.forecast.online_repository import (
        ensure_online_tables,
        get_min_last_seen_ts,
        insert_retention_run,
    )

    if retention_days <= 0 or safety_hours < 0:
        raise ValueError("Retention days must be positive and safety hours nonnegative")
    table = _validate_identifier(table)
    time_col = _validate_identifier(time_col)
    conn = connect_db(database)
    try:
        ensure_online_tables(conn)
        now_utc = dt.datetime.now(dt.timezone.utc)
        if use_training_watermark:
            min_last_seen_ts = get_min_last_seen_ts(conn, model_name=model_name)
            if min_last_seen_ts is None:
                return {
                    "status": "skipped",
                    "reason": "no training state found",
                    "rows_deleted": 0,
                }

            delete_cutoff = compute_delete_cutoff(
                now_utc=now_utc,
                min_last_seen_ts=min_last_seen_ts,
                retention_days=retention_days,
                safety_hours=safety_hours,
            )
        else:
            delete_cutoff = now_utc - dt.timedelta(days=retention_days)
        rows_deleted = delete_in_batches(conn, table, f"{time_col} < %s", (delete_cutoff,), order_by=time_col)
        insert_retention_run(
            conn=conn,
            model_name=model_name or "__all_models__",
            source_database=database,
            source_table=table,
            source_time_col=time_col,
            rows_deleted=rows_deleted,
            delete_cutoff=delete_cutoff,
            retention_days=retention_days,
            safety_hours=safety_hours,
        )
        return {
            "status": "ok",
            "rows_deleted": rows_deleted,
            "delete_cutoff": delete_cutoff.isoformat(),
        }
    finally:
        conn.close()


def delete_in_batches(conn, table, predicate, params=(), order_by="id", batch_size=10000):
    """Internal SQL predicates only; commit small batches to bound row locks/WAL."""
    table = _validate_identifier(table)
    order_by = _validate_identifier(order_by)
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    deleted = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {table} WHERE ctid IN ("
                f"SELECT ctid FROM {table} WHERE {predicate} "
                f"ORDER BY {order_by} LIMIT %s)",
                (*params, batch_size),
            )
            count = cur.rowcount
        conn.commit()
        deleted += count
        if count:
            logging.info("Retention %s: deleted %d rows (%d this pass)", table, deleted, count)
        if count < batch_size:
            return deleted


def run_history_retention(database, prediction_days=180, training_days=365):
    """Retain substantial forecast/metric history independently of raw watermarks."""
    from aqpy.common.db import connect_db
    from aqpy.forecast.online_repository import ensure_online_tables, insert_retention_run
    from aqpy.forecast.repository import ensure_predictions_table, ensure_registry_table

    if prediction_days <= 0 or training_days <= 0:
        raise ValueError("History retention days must be positive")
    conn = connect_db(database)
    try:
        ensure_online_tables(conn)
        ensure_predictions_table(conn)
        ensure_registry_table(conn)
        # Concurrent creation permits ingestion and dashboard reads during first run.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET lock_timeout = '5s'")
            cur.execute("SET maintenance_work_mem = '16MB'")
            cur.execute("SET max_parallel_maintenance_workers = 0")
            cur.execute("SET work_mem = '4MB'")
            for name, table, columns, predicate in (
                ("idx_predictions_retention_predicted_for", "predictions", "predicted_for", ""),
                ("idx_predictions_invalid", "predictions", "id",
                 " WHERE yhat IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)"),
                ("idx_training_metrics_retention", "online_training_metrics", "recorded_at", ""),
                ("idx_model_registry_retention", "model_registry", "trained_at", ""),
            ):
                cur.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({columns}){predicate}")
                cur.execute("SELECT indisvalid FROM pg_index WHERE indexrelid = %s::regclass", (name,))
                if not cur.fetchone()[0]:
                    raise RuntimeError(f"Retention index {name} is invalid; rebuild it concurrently")
            cur.execute("SET statement_timeout = '120s'")
        conn.autocommit = False
        now = dt.datetime.now(dt.timezone.utc)
        results = {}
        invalid = delete_in_batches(conn, "predictions",
            "yhat IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)")
        results["invalid_predictions_deleted"] = invalid
        for table, column, days, extra in (
            ("predictions", "predicted_for", prediction_days, ""),
            ("online_training_metrics", "recorded_at", training_days, ""),
            ("model_registry", "trained_at", training_days,
             " AND NOT EXISTS (SELECT 1 FROM online_training_state s "
             "WHERE s.model_name = model_registry.model_name AND s.model_version = model_registry.model_version)"),
        ):
            cutoff = now - dt.timedelta(days=days)
            count = delete_in_batches(conn, table, f"{column} < %s{extra}", (cutoff,), order_by=column)
            insert_retention_run(conn, "__history__", database, table, column,
                                 count + (invalid if table == "predictions" else 0), cutoff, days, 0)
            results[table] = {"rows_deleted": count, "cutoff": cutoff.isoformat()}
        # Recordkeeping itself is small, but should not grow forever either.
        results["retention_logs_deleted"] = delete_in_batches(
            conn, "retention_runs", "ran_at < %s", (now - dt.timedelta(days=training_days),))
        return {"status": "ok", **results}
    finally:
        conn.close()
