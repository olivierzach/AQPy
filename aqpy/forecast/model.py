import numpy as np

from aqpy.forecast.features import build_single_feature


def split_train_val(X, y, train_ratio=0.8):
    split_idx = max(1, int(len(X) * train_ratio))
    if split_idx >= len(X):
        split_idx = len(X) - 1
    return X[:split_idx], X[split_idx:], y[:split_idx], y[split_idx:]


def fit_linear_regression(X_train, y_train):
    X_aug = np.column_stack([np.ones(len(X_train)), X_train])
    coef = np.linalg.lstsq(X_aug, y_train, rcond=None)[0]
    intercept = float(coef[0])
    weights = [float(v) for v in coef[1:]]
    return intercept, weights


def predict(intercept, weights, X):
    return intercept + np.dot(X, np.array(weights))


def recursive_predict(values, lags, intercept, weights, horizon_steps):
    history = list(values)
    preds = []
    for _ in range(horizon_steps):
        feat = build_single_feature(history, lags)
        pred = float(intercept + np.dot(np.array(weights), feat))
        history.append(pred)
        preds.append(pred)
    return preds


def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
