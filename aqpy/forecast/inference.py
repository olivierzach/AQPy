import datetime as dt
import json
import pathlib

from aqpy.forecast.anomaly_model import score_bocpd_proxy, score_cusum, score_ewma
from aqpy.forecast.garch_model import forecast_garch_11
from aqpy.forecast.adaptive_ar import recursive_predict as ar_recursive_predict
from aqpy.common.db import connect_db
from aqpy.forecast.model import recursive_predict as linear_recursive_predict
from aqpy.forecast.nn_model import recursive_predict as nn_recursive_predict
from aqpy.forecast.rnn_lite import recursive_predict as rnn_recursive_predict
from aqpy.forecast.repository import (
    ensure_anomaly_events_table,
    ensure_garch_forecasts_table,
    ensure_predictions_table,
    fetch_recent_series,
    insert_anomaly_events,
    insert_garch_forecasts,
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
    model_type = model.get("model_type", "linear_lag")
    lags = [int(v) for v in model.get("lags", [1, 2, 3, 6, 12])]
    max_lag = max(lags)
    seq_len = int(model.get("seq_len", 24))
    if model_type in {"nn_mlp", "adaptive_ar", "linear_lag"}:
        n_rows = max(max_lag + 20, 50)
    elif model_type == "rnn_lite_gru":
        n_rows = max(seq_len + 20, 50)
    elif model_type in {"anomaly_cusum", "anomaly_ewma", "anomaly_bocpd"}:
        n_rows = max(int(model.get("score_window", 120)), 1)
    else:
        n_rows = max(10, horizon_steps)

    conn = connect_db(database)
    try:
        ensure_predictions_table(conn)
        ensure_garch_forecasts_table(conn)
        ensure_anomaly_events_table(conn)
        timestamps, values = fetch_recent_series(conn, table, time_col, target, n_rows)
        if model_type in {"nn_mlp", "adaptive_ar", "linear_lag"} and len(values) <= max_lag:
            raise RuntimeError(
                f"Not enough source rows for inference. Need > {max_lag}, got {len(values)}."
            )
        if model_type == "rnn_lite_gru" and len(values) < seq_len:
            raise RuntimeError(
                f"Not enough source rows for inference. Need >= {seq_len}, got {len(values)}."
            )
        if model_type in {"garch_11", "anomaly_cusum", "anomaly_ewma", "anomaly_bocpd"} and not values:
            raise RuntimeError("Not enough source rows for inference. Need at least 1 row, got 0.")

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
        elif model_type == "garch_11":
            forecasts = forecast_garch_11(
                model=model,
                last_value=float(values[-1]),
                horizon_steps=horizon_steps,
            )
            last_ts = timestamps[-1]
            cadence_seconds = int(model.get("cadence_seconds", 60))
            rows = []
            for step, forecast in enumerate(forecasts, start=1):
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
                        float(forecast["mean_forecast"]),
                        float(forecast["variance_forecast"]),
                        float(forecast["volatility_forecast"]),
                    )
                )
            insert_garch_forecasts(conn, rows)
            return {
                "inserted": len(rows),
                "target": target,
                "model_name": model["model_name"],
                "model_version": model["model_version"],
                "output_table": "garch_forecasts",
            }
        elif model_type in {"anomaly_cusum", "anomaly_ewma", "anomaly_bocpd"}:
            score_window = int(model.get("score_window", max(max_lag + 20, 50)))
            score_values = values[-score_window:]
            score_times = timestamps[-score_window:]
            if model_type == "anomaly_cusum":
                scored = score_cusum(score_values, model)
                method = "cusum"
            elif model_type == "anomaly_ewma":
                scored = score_ewma(score_values, model)
                method = "ewma"
            else:
                scored = score_bocpd_proxy(score_values, model)
                method = "bocpd_proxy"

            if not scored:
                return {
                    "status": "skipped",
                    "reason": "no rows to score",
                    "model_name": model["model_name"],
                }
            latest = scored[-1]
            event_time = score_times[-1]
            rows = [
                (
                    event_time,
                    database,
                    table,
                    target,
                    model["model_name"],
                    model["model_version"],
                    float(latest["score"]),
                    float(latest["threshold"]),
                    bool(latest["is_anomaly"]),
                    method,
                    {"window": int(score_window), "points_scored": int(len(scored))},
                )
            ]
            insert_anomaly_events(conn, rows)
            return {
                "inserted": 1,
                "target": target,
                "model_name": model["model_name"],
                "model_version": model["model_version"],
                "output_table": "anomaly_events",
                "score": float(latest["score"]),
                "is_anomaly": bool(latest["is_anomaly"]),
            }
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
