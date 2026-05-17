import unittest

from aqpy.forecast.anomaly_model import (
    fit_bocpd_proxy,
    fit_cusum,
    fit_ewma,
    score_bocpd_proxy,
    score_cusum,
    score_ewma,
)
from aqpy.forecast.garch_model import fit_garch_11, forecast_garch_11


class TestAnomalyAndGarchModels(unittest.TestCase):
    def test_garch_fit_and_forecast(self):
        values = [100.0 + (i * 0.2) for i in range(60)]
        model = fit_garch_11(values, alpha=0.1, beta=0.85)
        forecasts = forecast_garch_11(model, last_value=values[-1], horizon_steps=5)
        self.assertEqual(len(forecasts), 5)
        for row in forecasts:
            self.assertGreaterEqual(row["variance_forecast"], 0.0)
            self.assertGreaterEqual(row["volatility_forecast"], 0.0)

    def test_cusum_detects_large_jump(self):
        values = [10.0] * 40 + [50.0]
        model = fit_cusum(values[:40], drift=0.1, threshold=2.0)
        scored = score_cusum(values, model)
        self.assertEqual(len(scored), len(values))
        self.assertTrue(scored[-1]["is_anomaly"])

    def test_ewma_detects_large_jump(self):
        values = [20.0] * 40 + [45.0]
        model = fit_ewma(values[:40], alpha=0.2, threshold=3.0)
        scored = score_ewma(values, model)
        self.assertEqual(len(scored), len(values))
        self.assertTrue(scored[-1]["is_anomaly"])

    def test_bocpd_proxy_detects_large_jump(self):
        values = [15.0] * 50 + [40.0]
        model = fit_bocpd_proxy(values[:50], hazard=0.1, window=20, threshold=0.5)
        scored = score_bocpd_proxy(values, model)
        self.assertEqual(len(scored), len(values))
        self.assertTrue(scored[-1]["is_anomaly"])


if __name__ == "__main__":
    unittest.main()

