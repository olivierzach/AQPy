import datetime as dt
import re

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
    retention_days=14,
    safety_hours=12,
    use_training_watermark=True,
):
    from aqpy.common.db import connect_db
    from aqpy.forecast.online_repository import (
        delete_older_than,
        ensure_online_tables,
        get_min_last_seen_ts,
        insert_retention_run,
    )

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
        rows_deleted = delete_older_than(conn, table, time_col, delete_cutoff)
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
