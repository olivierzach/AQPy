import datetime as dt
import json
import pathlib
import logging
import os
import tempfile

import numpy as np

from aqpy.common.db import connect_db
from aqpy.forecast.adaptive_ar import (
    fit_weighted_ar,
    predict_batch as ar_predict_batch,
)
from aqpy.forecast.features import (
    build_ar_single_feature,
    build_ar_feature_matrix,
    build_single_feature,
    build_feature_matrix,
    estimate_cadence_seconds,
)
from aqpy.forecast.model import mae, rmse, split_train_val
from aqpy.forecast.nn_model import predict_batch, train_mlp_regressor
from aqpy.forecast.rnn_lite import (
    build_sequence_dataset,
    fit_gru_lite_head,
    predict_batch as rnn_predict_batch,
)
from aqpy.forecast.online_repository import (
    count_new_rows,
    ensure_online_tables,
    get_training_state,
    insert_or_update_model_registry,
    insert_training_metric,
    upsert_training_state,
)
from aqpy.forecast.repository import ensure_registry_table, fetch_series, validate_identifier
from aqpy.forecast.validation import require_finite

logger = logging.getLogger(__name__)


def _timestamp_version():
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace(":", "")
        .replace("-", "")
        .replace(".", "")
    )


def _baseline_from_features(X, lags):
    try:
        idx = lags.index(1)
    except ValueError:
        idx = 0
    return X[:, idx]


def _baseline_from_sequences(X_seq):
    return X_seq[:, -1]


def _improvement_pct(baseline_metric, model_metric):
    if baseline_metric == 0:
        return 0.0
    return float((baseline_metric - model_metric) / baseline_metric * 100.0)


def run_online_training_step(
    database,
    table,
    time_col,
    target,
    model_name,
    model_path,
    history_hours=24 * 14,
    lags=None,
    holdout_ratio=0.2,
    min_new_rows=30,
    learning_rate=0.01,
    epochs=40,
    batch_size=64,
    hidden_dim=8,
    model_type="nn_mlp",
    forgetting_factor=0.995,
    ar_delta=100.0,
    seq_len=24,
    burn_in_rows=200,
    max_train_rows=None,
    rnn_ridge=1e-3,
    random_seed=42,
):
    table = validate_identifier(table)
    time_col = validate_identifier(time_col)
    target = validate_identifier(target)
    lags = sorted(set(lags or [1, 2, 3, 6, 12]))

    conn = connect_db(database)
    staged_path = None
    try:
        ensure_online_tables(conn)
        ensure_registry_table(conn)
        state = get_training_state(conn, model_name)
        model_file = pathlib.Path(model_path)
        prior = None
        if model_file.exists():
            try:
                prior = json.loads(model_file.read_text())
                require_finite(prior, "prior model")
            except (ValueError, OSError) as exc:
                logger.warning("%s: rebuilding invalid artifact: %s", model_name, exc)
                prior = None

        if state is not None:
            new_rows = count_new_rows(conn, table, time_col, state["last_seen_ts"])
            artifact_current = prior is not None and prior.get("model_version") == state["model_version"]
            solver_current = model_type != "adaptive_ar" or (prior or {}).get("solver") == "windowed_weighted_ridge_v1"
            if new_rows < min_new_rows and artifact_current and solver_current:
                return {
                    "status": "skipped",
                    "reason": f"only {new_rows} new rows (min {min_new_rows})",
                    "new_rows": new_rows,
                }
        else:
            new_rows = -1

        timestamps, values = fetch_series(conn, table, time_col, target, history_hours)
        if not np.isfinite(values).all():
            raise ValueError(f"{model_name}: source readings contain non-finite numbers")
        if max_train_rows is not None and max_train_rows > 0 and len(values) > max_train_rows:
            timestamps = timestamps[-max_train_rows:]
            values = values[-max_train_rows:]
        if len(values) < burn_in_rows:
            return {
                "status": "skipped",
                "reason": f"burn-in not reached ({len(values)} < {burn_in_rows})",
                "new_rows": new_rows,
            }

        if len(values) <= max(lags) + 5:
            return {
                "status": "skipped",
                "reason": f"not enough rows ({len(values)})",
                "new_rows": new_rows,
            }

        if model_type == "adaptive_ar":
            X, y = build_ar_feature_matrix(values, lags)
        elif model_type == "rnn_lite_gru":
            X_seq, y = build_sequence_dataset(np.array(values, dtype=float), seq_len=seq_len)
        else:
            X, y = build_feature_matrix(values, lags)
        if model_type == "rnn_lite_gru":
            split_idx = max(1, int(len(X_seq) * (1.0 - holdout_ratio)))
            if split_idx >= len(X_seq):
                split_idx = len(X_seq) - 1
            X_train_seq = X_seq[:split_idx]
            X_holdout_seq = X_seq[split_idx:]
            y_train = y[:split_idx]
            y_holdout = y[split_idx:]
            if len(X_holdout_seq) < 5:
                return {
                    "status": "skipped",
                    "reason": "holdout set too small",
                    "new_rows": new_rows,
                }
            train_rows = len(X_train_seq)
            holdout_rows = len(X_holdout_seq)
        else:
            X_train, X_holdout, y_train, y_holdout = split_train_val(X, y, train_ratio=1.0 - holdout_ratio)
            if len(X_holdout) < 5:
                return {
                    "status": "skipped",
                    "reason": "holdout set too small",
                    "new_rows": new_rows,
                }
            train_rows = len(X_train)
            holdout_rows = len(X_holdout)

        init = None
        if prior is not None:
            if model_type == "nn_mlp":
                if (
                    prior.get("model_type") == "nn_mlp"
                    and prior.get("hidden_dim") == hidden_dim
                    and prior.get("input_dim") == X_train.shape[1]
                ):
                    init = prior

        if model_type == "adaptive_ar":
            ar_model = fit_weighted_ar(
                X_train=X_train,
                y_train=y_train,
                forgetting_factor=forgetting_factor,
                delta=ar_delta,
            )
            holdout_pred = ar_predict_batch(ar_model, X_holdout)
            train_loss = float(np.mean((ar_predict_batch(ar_model, X_train) - y_train) ** 2))
            baseline_pred = _baseline_from_features(X_holdout, lags)
            model_payload = ar_model
        elif model_type == "rnn_lite_gru":
            encoder_init = None
            if prior is not None:
                if (
                    prior.get("model_type") == "rnn_lite_gru"
                    and int(prior.get("seq_len", -1)) == int(seq_len)
                    and int(prior.get("hidden_dim", -1)) == int(hidden_dim)
                ):
                    encoder_init = {
                        "hidden_dim": int(prior["encoder"]["hidden_dim"]),
                        "Wz": np.array(prior["encoder"]["Wz"], dtype=float),
                        "Uz": np.array(prior["encoder"]["Uz"], dtype=float),
                        "bz": np.array(prior["encoder"]["bz"], dtype=float),
                        "Wr": np.array(prior["encoder"]["Wr"], dtype=float),
                        "Ur": np.array(prior["encoder"]["Ur"], dtype=float),
                        "br": np.array(prior["encoder"]["br"], dtype=float),
                        "Wh": np.array(prior["encoder"]["Wh"], dtype=float),
                        "Uh": np.array(prior["encoder"]["Uh"], dtype=float),
                        "bh": np.array(prior["encoder"]["bh"], dtype=float),
                    }
            rnn_model = fit_gru_lite_head(
                values=np.array(values[:split_idx + seq_len], dtype=float),
                seq_len=seq_len,
                hidden_dim=hidden_dim,
                ridge=rnn_ridge,
                seed=random_seed,
                init=encoder_init,
            )
            holdout_pred = rnn_predict_batch(rnn_model, X_holdout_seq)
            train_loss = float(rnn_model.get("train_loss"))
            baseline_pred = _baseline_from_sequences(X_holdout_seq)
            model_payload = rnn_model
        else:
            nn_model = train_mlp_regressor(
                X_train=X_train,
                y_train=y_train,
                hidden_dim=hidden_dim,
                learning_rate=learning_rate,
                epochs=epochs,
                batch_size=batch_size,
                init_model=init,
            )
            holdout_pred = predict_batch(nn_model, X_holdout)
            train_loss = nn_model.get("train_loss")
            baseline_pred = _baseline_from_features(X_holdout, lags)
            model_payload = nn_model

        holdout_mae = mae(y_holdout, holdout_pred)
        holdout_rmse = rmse(y_holdout, holdout_pred)
        baseline_mae = mae(y_holdout, baseline_pred)
        baseline_rmse = rmse(y_holdout, baseline_pred)
        mae_improvement_pct = _improvement_pct(baseline_mae, holdout_mae)
        rmse_improvement_pct = _improvement_pct(baseline_rmse, holdout_rmse)

        trained_at = dt.datetime.now(dt.timezone.utc).isoformat()
        model_version = _timestamp_version()
        artifact = {
            "model_type": model_type,
            "model_name": model_name,
            "model_version": model_version,
            "trained_at": trained_at,
            "database": database,
            "table": table,
            "time_col": time_col,
            "target": target,
            "lags": lags,
            "cadence_seconds": estimate_cadence_seconds(timestamps),
            "metrics": {
                "holdout_mae": holdout_mae,
                "holdout_rmse": holdout_rmse,
                "baseline_mae": baseline_mae,
                "baseline_rmse": baseline_rmse,
                "mae_improvement_pct": mae_improvement_pct,
                "rmse_improvement_pct": rmse_improvement_pct,
                "train_rows": int(train_rows),
                "holdout_rows": int(holdout_rows),
                "train_loss": train_loss,
            },
            "online_training": {
                "learning_rate": learning_rate,
                "batch_size": batch_size,
                "epochs": epochs,
                "forgetting_factor": forgetting_factor,
                "ar_delta": ar_delta,
                "seq_len": seq_len,
                "burn_in_rows": burn_in_rows,
                "max_train_rows": max_train_rows,
                "rnn_ridge": rnn_ridge,
                "random_seed": random_seed,
                "min_new_rows": min_new_rows,
                "history_hours": history_hours,
            },
            **model_payload,
        }

        require_finite(artifact, model_name)
        serialized = json.dumps(artifact, indent=2, allow_nan=False)
        model_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=model_file.parent, delete=False) as staged:
            staged_path = staged.name
            staged.write(serialized)
            staged.flush()
            os.fsync(staged.fileno())

        last_seen_ts = timestamps[-1]
        update_from = state["last_seen_ts"] if state is not None else None
        effective_new_rows = max(0, new_rows) if state is not None else len(values)

        upsert_training_state(
            conn=conn,
            model_name=model_name,
            model_version=model_version,
            artifact_path=str(model_file.resolve()),
            last_seen_ts=last_seen_ts,
            source_database=database,
            source_table=table,
            source_time_col=time_col,
            source_target_col=target,
            commit=False,
        )
        insert_training_metric(
            conn,
            {
                "model_name": model_name,
                "model_version": model_version,
                "source_database": database,
                "source_table": table,
                "source_target_col": target,
                "train_rows": int(train_rows),
                "holdout_rows": int(holdout_rows),
                "holdout_mae": holdout_mae,
                "holdout_rmse": holdout_rmse,
                "baseline_mae": baseline_mae,
                "baseline_rmse": baseline_rmse,
                "mae_improvement_pct": mae_improvement_pct,
                "rmse_improvement_pct": rmse_improvement_pct,
                "learning_rate": learning_rate,
                "batch_size": int(batch_size),
                "epochs": int(epochs),
                "new_rows_since_last": int(effective_new_rows),
                "update_from_ts": update_from,
                "update_to_ts": last_seen_ts,
            },
            commit=False,
        )
        insert_or_update_model_registry(
            conn,
            {
                "model_name": model_name,
                "model_version": model_version,
                "trained_at": trained_at,
                "database": database,
                "table": table,
                "target": target,
                "metrics": artifact["metrics"],
                "artifact_path": str(model_file.resolve()),
            },
            commit=False,
        )
        # State, metrics and registry succeed together. Publish only complete JSON.
        # A publication failure leaves a version mismatch that triggers a retry.
        conn.commit()
        os.replace(staged_path, model_file)
        staged_path = None

        return {
            "status": "trained",
            "model_version": model_version,
            "artifact_path": str(model_file),
            "holdout_mae": holdout_mae,
            "holdout_rmse": holdout_rmse,
            "baseline_mae": baseline_mae,
            "baseline_rmse": baseline_rmse,
            "mae_improvement_pct": mae_improvement_pct,
            "rmse_improvement_pct": rmse_improvement_pct,
            "new_rows": int(effective_new_rows),
        }
    finally:
        if staged_path is not None:
            pathlib.Path(staged_path).unlink(missing_ok=True)
        conn.close()
