import math

import numpy as np


def _safe_var(values):
    var = float(np.var(values))
    return max(var, 1e-12)


def fit_garch_11(values, alpha=0.1, beta=0.85):
    series = np.array(values, dtype=float)
    if len(series) < 10:
        raise ValueError(f"Need at least 10 rows for garch_11, got {len(series)}")

    returns = np.diff(series)
    mu = float(np.mean(returns))
    eps = returns - mu
    unconditional_var = _safe_var(eps)

    alpha = float(alpha)
    beta = float(beta)
    if alpha <= 0 or beta <= 0 or alpha + beta >= 1:
        raise ValueError("garch_11 requires alpha > 0, beta > 0, and alpha + beta < 1")

    omega = unconditional_var * (1.0 - alpha - beta)
    sigma2 = unconditional_var
    for shock in eps:
        sigma2 = omega + alpha * (float(shock) ** 2) + beta * sigma2
    sigma2 = max(float(sigma2), 1e-12)

    return {
        "omega": float(omega),
        "alpha": alpha,
        "beta": beta,
        "mean_return": mu,
        "last_sigma2": sigma2,
        "unconditional_var": unconditional_var,
    }


def forecast_garch_11(model, last_value, horizon_steps):
    omega = float(model["omega"])
    alpha = float(model["alpha"])
    beta = float(model["beta"])
    persistence = alpha + beta
    sigma2 = max(float(model.get("last_sigma2", model.get("unconditional_var", 1.0))), 1e-12)
    mean_return = float(model.get("mean_return", 0.0))
    level = float(last_value)

    rows = []
    for _ in range(int(horizon_steps)):
        sigma2 = omega + persistence * sigma2
        sigma2 = max(float(sigma2), 1e-12)
        level = level + mean_return
        rows.append(
            {
                "mean_forecast": float(level),
                "variance_forecast": sigma2,
                "volatility_forecast": math.sqrt(sigma2),
            }
        )
    return rows

