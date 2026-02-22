import numpy as np

from aqpy.forecast.features import build_single_feature


def _relu(x):
    return np.maximum(0.0, x)


def _relu_grad(x):
    return (x > 0.0).astype(float)


def init_params(input_dim, hidden_dim, seed=42):
    rng = np.random.default_rng(seed)
    w1 = rng.normal(0.0, 0.1, size=(input_dim, hidden_dim))
    b1 = np.zeros(hidden_dim)
    w2 = rng.normal(0.0, 0.1, size=(hidden_dim, 1))
    b2 = np.zeros(1)
    return {"w1": w1, "b1": b1, "w2": w2, "b2": b2}


def forward(params, X):
    z1 = X @ params["w1"] + params["b1"]
    a1 = _relu(z1)
    yhat = a1 @ params["w2"] + params["b2"]
    cache = {"X": X, "z1": z1, "a1": a1}
    return yhat, cache


def _mse_loss(yhat, y):
    return float(np.mean((yhat - y) ** 2))


def _backward(params, cache, yhat, y):
    n = len(y)
    dy = (2.0 / n) * (yhat - y)
    dw2 = cache["a1"].T @ dy
    db2 = np.sum(dy, axis=0)
    da1 = dy @ params["w2"].T
    dz1 = da1 * _relu_grad(cache["z1"])
    dw1 = cache["X"].T @ dz1
    db1 = np.sum(dz1, axis=0)
    return {"dw1": dw1, "db1": db1, "dw2": dw2, "db2": db2}


def train_mlp_regressor(
    X_train,
    y_train,
    hidden_dim=8,
    learning_rate=0.01,
    epochs=40,
    batch_size=64,
    seed=42,
    init=None,
):
    x_mean = np.mean(X_train, axis=0)
    x_std = np.std(X_train, axis=0)
    x_std = np.where(x_std < 1e-8, 1.0, x_std)
    Xs = (X_train - x_mean) / x_std

    y_mean = float(np.mean(y_train))
    y_std = float(np.std(y_train))
    if y_std < 1e-8:
        y_std = 1.0
    ys = ((y_train - y_mean) / y_std).reshape(-1, 1)

    input_dim = X_train.shape[1]
    params = init if init is not None else init_params(input_dim, hidden_dim, seed=seed)
    n = len(Xs)
    losses = []

    for _ in range(max(1, epochs)):
        idx = np.random.permutation(n)
        X_ep = Xs[idx]
        y_ep = ys[idx]
        for start in range(0, n, max(1, batch_size)):
            end = min(n, start + max(1, batch_size))
            xb = X_ep[start:end]
            yb = y_ep[start:end]
            yhat, cache = forward(params, xb)
            grads = _backward(params, cache, yhat, yb)
            params["w1"] -= learning_rate * grads["dw1"]
            params["b1"] -= learning_rate * grads["db1"]
            params["w2"] -= learning_rate * grads["dw2"]
            params["b2"] -= learning_rate * grads["db2"]
        yhat_full, _ = forward(params, Xs)
        losses.append(_mse_loss(yhat_full, ys))

    model = {
        "w1": params["w1"].tolist(),
        "b1": params["b1"].tolist(),
        "w2": params["w2"].tolist(),
        "b2": params["b2"].tolist(),
        "x_mean": x_mean.tolist(),
        "x_std": x_std.tolist(),
        "y_mean": y_mean,
        "y_std": y_std,
        "hidden_dim": hidden_dim,
        "input_dim": input_dim,
        "train_loss": losses[-1] if losses else None,
    }
    return model


def _predict_one(model, feature_row):
    X = np.array([feature_row], dtype=float)
    x_mean = np.array(model["x_mean"], dtype=float)
    x_std = np.array(model["x_std"], dtype=float)
    Xs = (X - x_mean) / x_std

    params = {
        "w1": np.array(model["w1"], dtype=float),
        "b1": np.array(model["b1"], dtype=float),
        "w2": np.array(model["w2"], dtype=float),
        "b2": np.array(model["b2"], dtype=float),
    }
    yhat_scaled, _ = forward(params, Xs)
    return float(yhat_scaled[0, 0] * model["y_std"] + model["y_mean"])


def predict_batch(model, X):
    return np.array([_predict_one(model, row) for row in X], dtype=float)


def recursive_predict(model, values, lags, horizon_steps):
    history = list(values)
    preds = []
    for _ in range(horizon_steps):
        feat = build_single_feature(history, lags)
        pred = _predict_one(model, feat)
        history.append(pred)
        preds.append(pred)
    return preds
