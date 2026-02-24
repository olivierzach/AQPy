import datetime as dt
import json
import pathlib

import numpy as np

from aqpy.common.db import connect_db
from aqpy.forecast.adaptive_ar import predict_batch as ar_predict_batch
from aqpy.forecast.features import build_ar_single_feature, build_single_feature
from aqpy.forecast.nn_model import predict_batch as nn_predict_batch
from aqpy.forecast.repository import (
    delete_predictions_window,
    ensure_predictions_table,
    insert_predictions,
    validate_identifier,
)
from aqpy.forecast.rnn_lite import predict_batch as rnn_predict_batch


def _fetch_series_for_window(conn, table, time_col, target_col, start_ts, end_ts):
    query = f"""
    SELECT {time_col}, {target_col}
    FROM {table}
    WHERE {time_col} <= %s
      AND {target_col} IS NOT NULL
    ORDER BY {time_col} ASC
    """
    with conn.cursor() as cur:
        cur.execute(query, (end_ts,))
        rows = cur.fetchall()
    timestamps = [r[0] for r in rows]
    values = [float(r[1]) for r in rows]
    start_idx = 0
    for i, ts in enumerate(timestamps):
        if ts >= start_ts:
            start_idx = i
            break
    return timestamps, values, start_idx


def _build_backfill_rows_nn_ar(model, timestamps, values, start_idx):
    model_type = model.get("model_type", "nn_mlp")
    lags = [int(v) for v in model["lags"]]
    max_lag = max(lags)
    use_nn = model_type == "nn_mlp"

    pred_times = []
    feature_rows = []
    for i in range(max_lag, len(values)):
        if i < start_idx:
            continue
        history = values[:i]
        if use_nn:
            feat = build_single_feature(history, lags)
        else:
            feat = build_ar_single_feature(history, lags)
        feature_rows.append(feat)
        pred_times.append(timestamps[i])

    if not feature_rows:
        return [], np.array([], dtype=float)

    X = np.array(feature_rows, dtype=float)
    if use_nn:
        preds = nn_predict_batch(model, X)
    else:
        preds = ar_predict_batch(model, X)
    return pred_times, preds


def _build_backfill_rows_rnn(model, timestamps, values, start_idx):
    seq_len = int(model.get("seq_len", 24))
    pred_times = []
    seqs = []
    for i in range(seq_len, len(values)):
        if i < start_idx:
            continue
        seqs.append(values[i - seq_len : i])
        pred_times.append(timestamps[i])
    if not seqs:
        return [], np.array([], dtype=float)
    preds = rnn_predict_batch(model, np.array(seqs, dtype=float))
    return pred_times, preds


def run_backfill(
    model_path,
    backfill_hours=48,
    database_override=None,
    replace_existing=True,
):
    model_file = pathlib.Path(model_path)
    if not model_file.exists():
        return {"status": "skipped", "reason": f"model not found: {model_file}"}

    model = json.loads(model_file.read_text())
    database = database_override or model["database"]
    table = validate_identifier(model["table"])
    time_col = validate_identifier(model["time_col"])
    target = validate_identifier(model["target"])
    model_name = model["model_name"]
    model_version = model["model_version"]
    model_type = model.get("model_type", "nn_mlp")

    end_ts = dt.datetime.now(dt.timezone.utc)
    start_ts = end_ts - dt.timedelta(hours=int(backfill_hours))

    conn = connect_db(database)
    try:
        ensure_predictions_table(conn)
        timestamps, values, start_idx = _fetch_series_for_window(
            conn, table, time_col, target, start_ts, end_ts
        )
        if len(values) < 5:
            return {"status": "skipped", "reason": f"not enough source rows ({len(values)})"}

        if model_type == "rnn_lite_gru":
            pred_times, preds = _build_backfill_rows_rnn(model, timestamps, values, start_idx)
        else:
            pred_times, preds = _build_backfill_rows_nn_ar(model, timestamps, values, start_idx)

        if len(pred_times) == 0:
            return {"status": "skipped", "reason": "no eligible rows in backfill window"}

        deleted = 0
        if replace_existing:
            deleted = delete_predictions_window(
                conn=conn,
                model_name=model_name,
                model_version=model_version,
                source_database=database,
                source_table=table,
                target=target,
                start_ts=start_ts,
                end_ts=end_ts,
                horizon_step=1,
            )

        rows = []
        for pred_for, yhat in zip(pred_times, preds):
            rows.append(
                (
                    pred_for,
                    database,
                    table,
                    target,
                    model_name,
                    model_version,
                    1,
                    float(yhat),
                )
            )
        insert_predictions(conn, rows)
        return {
            "status": "ok",
            "inserted": int(len(rows)),
            "deleted_existing": int(deleted),
            "model_name": model_name,
            "target": target,
            "window_hours": int(backfill_hours),
        }
    finally:
        conn.close()
