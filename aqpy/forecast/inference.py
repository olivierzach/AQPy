import datetime as dt
import json
import pathlib

from aqpy.forecast.adaptive_ar import recursive_predict as ar_recursive_predict
from aqpy.common.db import connect_db
from aqpy.forecast.model import recursive_predict as linear_recursive_predict
from aqpy.forecast.nn_model import recursive_predict as nn_recursive_predict
from aqpy.forecast.rnn_lite import recursive_predict as rnn_recursive_predict
from aqpy.forecast.repository import (
    ensure_predictions_table,
    fetch_recent_series,
    insert_predictions,
    validate_identifier,
)


def run_inference(model_path, horizon_steps=12, database_override=None):
    model_file = pathlib.Path(model_path)
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found: {model_file}")

    model = json.loads(model_file.read_text())
    database = database_override or model["database"]
    table = validate_identifier(model["table"])
    time_col = validate_identifier(model["time_col"])
    target = validate_identifier(model["target"])
    lags = [int(v) for v in model["lags"]]
    max_lag = max(lags)
    n_rows = max(max_lag + 20, 50)

    conn = connect_db(database)
    try:
        ensure_predictions_table(conn)
        timestamps, values = fetch_recent_series(conn, table, time_col, target, n_rows)
        if len(values) <= max_lag:
            raise RuntimeError(
                f"Not enough source rows for inference. Need > {max_lag}, got {len(values)}."
            )

        model_type = model.get("model_type", "linear_lag")
        if model_type == "nn_mlp":
            preds = nn_recursive_predict(
                model=model,
                values=values,
                lags=lags,
                horizon_steps=horizon_steps,
            )
        elif model_type == "rnn_lite_gru":
            preds = rnn_recursive_predict(
                model=model,
                values=values,
                horizon_steps=horizon_steps,
            )
        elif model_type == "adaptive_ar":
            preds = ar_recursive_predict(
                model=model,
                values=values,
                lags=lags,
                horizon_steps=horizon_steps,
            )
        else:
            preds = linear_recursive_predict(
                values=values,
                lags=lags,
                intercept=float(model["intercept"]),
                weights=[float(w) for w in model["weights"]],
                horizon_steps=horizon_steps,
            )

        last_ts = timestamps[-1]
        cadence_seconds = int(model.get("cadence_seconds", 60))
        rows = []
        for step, pred in enumerate(preds, start=1):
            pred_for = last_ts + dt.timedelta(seconds=cadence_seconds * step)
            rows.append(
                (
                    pred_for,
                    database,
                    table,
                    target,
                    model["model_name"],
                    model["model_version"],
                    step,
                    pred,
                )
            )

        insert_predictions(conn, rows)
        return {
            "inserted": len(rows),
            "target": target,
            "model_name": model["model_name"],
            "model_version": model["model_version"],
        }
    finally:
        conn.close()
