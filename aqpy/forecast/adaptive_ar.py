import numpy as np

from aqpy.forecast.features import build_ar_single_feature


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
