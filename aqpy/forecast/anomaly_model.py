import math

import numpy as np


def _mean_std(values):
    arr = np.array(values, dtype=float)
    if len(arr) == 0:
        raise ValueError("cannot fit anomaly model on empty series")
    mu = float(np.mean(arr))
    sigma = float(np.std(arr))
    return mu, max(sigma, 1e-9)


def fit_cusum(values, drift=0.25, threshold=8.0):
    mu, sigma = _mean_std(values)
    return {
        "method": "anomaly_cusum",
        "mean": mu,
        "std": sigma,
        "drift": float(drift) * sigma,
        "threshold": float(threshold) * sigma,
    }


def score_cusum(values, model):
    mu = float(model["mean"])
    drift = float(model["drift"])
    threshold = float(model["threshold"])

    pos = 0.0
    neg = 0.0
    rows = []
    for value in values:
        x = float(value)
        pos = max(0.0, pos + (x - mu - drift))
        neg = max(0.0, neg + (mu - x - drift))
        score = max(pos, neg)
        rows.append({"score": score, "is_anomaly": score >= threshold, "threshold": threshold})
    return rows


def fit_ewma(values, alpha=0.2, threshold=3.0):
    mu, sigma = _mean_std(values)
    return {
        "method": "anomaly_ewma",
        "alpha": float(alpha),
        "ewma_init": mu,
        "var_init": sigma * sigma,
        "threshold": float(threshold),
    }


def score_ewma(values, model):
    alpha = float(model["alpha"])
    threshold = float(model["threshold"])
    ewma = float(model["ewma_init"])
    var = max(float(model["var_init"]), 1e-9)

    rows = []
    for value in values:
        x = float(value)
        residual = x - ewma
        score = abs(residual) / math.sqrt(max(var, 1e-9))
        rows.append({"score": score, "is_anomaly": score >= threshold, "threshold": threshold})
        ewma = alpha * x + (1.0 - alpha) * ewma
        var = alpha * (residual**2) + (1.0 - alpha) * var
    return rows


def fit_bocpd_proxy(values, hazard=0.05, window=30, threshold=0.6):
    mu, sigma = _mean_std(values)
    return {
        "method": "anomaly_bocpd",
        "hazard": float(hazard),
        "window": int(window),
        "threshold": float(threshold),
        "global_mean": mu,
        "global_std": sigma,
    }


def score_bocpd_proxy(values, model):
    hazard = float(model["hazard"])
    window = max(5, int(model["window"]))
    threshold = float(model["threshold"])
    global_mean = float(model["global_mean"])
    global_std = max(float(model["global_std"]), 1e-9)

    data = list(float(v) for v in values)
    rows = []
    for idx, x in enumerate(data):
        if idx < window:
            mu = global_mean
            sigma = global_std
        else:
            local = np.array(data[idx - window : idx], dtype=float)
            mu = float(np.mean(local))
            sigma = max(float(np.std(local)), 1e-9)
        z = abs(x - mu) / sigma
        cp_prob = 1.0 - math.exp(-hazard * (z**2))
        cp_prob = min(max(cp_prob, 0.0), 1.0)
        rows.append({"score": cp_prob, "is_anomaly": cp_prob >= threshold, "threshold": threshold})
    return rows

