import numpy as np

from aqpy.forecast.features import build_ar_single_feature


def fit_weighted_ar(X_train, y_train, forgetting_factor=0.995, delta=100.0):
    """Fit the bounded window afresh, avoiding covariance drift on replayed rows.

    Exponential weights retain adaptation to recent samples. Column scaling and
    a fixed ridge floor keep constant/zero and collinear sensor data well posed.
    Solve the augmented least-squares system rather than forming normal equations.
    """
    X = np.asarray(X_train, dtype=float)
    y = np.asarray(y_train, dtype=float)
    if X.ndim != 2 or y.shape != (len(X),) or not len(X):
        raise ValueError("Expected nonempty feature matrix and matching targets")
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError("AR training data contains non-finite numbers")
    if not 0 < forgetting_factor <= 1 or not np.isfinite(delta) or delta <= 0:
        raise ValueError("Require 0 < forgetting_factor <= 1 and finite delta > 0")
    scale = np.maximum(np.max(np.abs(X), axis=0), 1.0)
    weights = forgetting_factor ** (np.arange(len(X) - 1, -1, -1) / 2.0)
    design = np.vstack((X / scale * weights[:, None], np.eye(X.shape[1]) / np.sqrt(delta)))
    response = np.concatenate((y * weights, np.zeros(X.shape[1])))
    theta = np.linalg.lstsq(design, response, rcond=None)[0] / scale
    if not np.isfinite(theta).all():
        raise ValueError("AR fit produced non-finite coefficients")
    return {
        "theta": theta.tolist(),
        "forgetting_factor": forgetting_factor,
        "delta": delta,
        "solver": "windowed_weighted_ridge_v1",
    }


def init_state(input_dim, delta=100.0):
    return {
        "theta": np.zeros(input_dim, dtype=float),
        "P": np.eye(input_dim, dtype=float) * float(delta),
    }


def fit_recursive_least_squares(
    X_train,
    y_train,
    forgetting_factor=0.995,
    delta=100.0,
    init=None,
):
    n_features = X_train.shape[1]
    if init is None:
        state = init_state(n_features, delta=delta)
    else:
        state = {
            "theta": np.array(init["theta"], dtype=float),
            "P": np.array(init["P"], dtype=float),
        }

    theta = state["theta"]
    P = state["P"]
    lam = float(forgetting_factor)
    for i in range(len(X_train)):
        x = X_train[i].reshape(-1, 1)
        y = float(y_train[i])
        denom = lam + float((x.T @ P @ x).item())
        k = (P @ x) / denom
        pred = float(theta @ x[:, 0])
        err = y - pred
        theta = theta + (k[:, 0] * err)
        P = (P - k @ x.T @ P) / lam

    return {
        "theta": theta.tolist(),
        "P": P.tolist(),
        "forgetting_factor": forgetting_factor,
        "delta": delta,
    }


def predict_batch(model, X):
    theta = np.array(model["theta"], dtype=float)
    return X @ theta


def recursive_predict(model, values, lags, horizon_steps):
    theta = np.array(model["theta"], dtype=float)
    history = list(values)
    preds = []
    for _ in range(horizon_steps):
        feat = build_ar_single_feature(history, lags)
        pred = float(feat @ theta)
        history.append(pred)
        preds.append(pred)
    return preds
