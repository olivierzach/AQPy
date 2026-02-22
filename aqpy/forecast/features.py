import statistics

import numpy as np


def build_feature_matrix(values, lags):
    max_lag = max(lags)
    if len(values) <= max_lag:
        raise ValueError(
            f"Not enough rows ({len(values)}) for max lag {max_lag}. Collect more data."
        )

    features = []
    targets = []
    for idx in range(max_lag, len(values)):
        row = [values[idx - lag] for lag in lags]
        row.append(float(np.mean(values[idx - min(3, idx) : idx])))
        row.append(float(np.mean(values[max(0, idx - 12) : idx])))
        features.append(row)
        targets.append(values[idx])
    return np.array(features, dtype=float), np.array(targets, dtype=float)


def build_single_feature(values, lags):
    idx = len(values)
    row = [values[idx - lag] for lag in lags]
    row.append(float(np.mean(values[idx - min(3, idx) : idx])))
    row.append(float(np.mean(values[max(0, idx - 12) : idx])))
    return np.array(row, dtype=float)


def build_ar_feature_matrix(values, lags):
    max_lag = max(lags)
    if len(values) <= max_lag:
        raise ValueError(
            f"Not enough rows ({len(values)}) for max lag {max_lag}. Collect more data."
        )

    features = []
    targets = []
    for idx in range(max_lag, len(values)):
        row = [values[idx - lag] for lag in lags]
        features.append(row)
        targets.append(values[idx])
    return np.array(features, dtype=float), np.array(targets, dtype=float)


def build_ar_single_feature(values, lags):
    idx = len(values)
    row = [values[idx - lag] for lag in lags]
    return np.array(row, dtype=float)


def estimate_cadence_seconds(timestamps):
    if len(timestamps) < 3:
        return 60
    diffs = []
    for i in range(1, len(timestamps)):
        d = int((timestamps[i] - timestamps[i - 1]).total_seconds())
        if d > 0:
            diffs.append(d)
    if not diffs:
        return 60
    return int(statistics.median(diffs))
