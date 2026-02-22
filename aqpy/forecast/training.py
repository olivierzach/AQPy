import datetime as dt
import json
import pathlib

from aqpy.common.db import connect_db
from aqpy.forecast.features import build_feature_matrix, estimate_cadence_seconds
from aqpy.forecast.model import fit_linear_regression, mae, predict, rmse, split_train_val
from aqpy.forecast.repository import (
    ensure_registry_table,
    fetch_series,
    register_model,
    validate_identifier,
)


def train_model(
    database,
    table,
    time_col,
    target,
    history_hours,
    lags,
    model_name,
    model_path,
    register=False,
):
    table = validate_identifier(table)
    time_col = validate_identifier(time_col)
    target = validate_identifier(target)
    lags = sorted(set(lags))

    conn = connect_db(database)
    try:
        timestamps, values = fetch_series(conn, table, time_col, target, history_hours)
        X, y = build_feature_matrix(values, lags)
        X_train, X_val, y_train, y_val = split_train_val(X, y)
        intercept, weights = fit_linear_regression(X_train, y_train)
        y_pred = predict(intercept, weights, X_val)

        metrics = {
            "mae": mae(y_val, y_pred),
            "rmse": rmse(y_val, y_pred),
            "n_train": int(len(y_train)),
            "n_val": int(len(y_val)),
        }

        trained_at = dt.datetime.now(dt.timezone.utc).isoformat()
        model_version = trained_at.replace(":", "").replace("-", "")

        payload = {
            "model_type": "linear_lag",
            "model_name": model_name,
            "model_version": model_version,
            "trained_at": trained_at,
            "database": database,
            "table": table,
            "time_col": time_col,
            "target": target,
            "lags": lags,
            "intercept": intercept,
            "weights": weights,
            "cadence_seconds": estimate_cadence_seconds(timestamps),
            "metrics": metrics,
            "artifact_path": str(pathlib.Path(model_path).resolve()),
        }

        artifact = pathlib.Path(model_path)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(payload, indent=2))

        if register:
            ensure_registry_table(conn)
            register_model(conn, payload)

        return payload
    finally:
        conn.close()
