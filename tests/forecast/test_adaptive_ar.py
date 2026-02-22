import unittest

import numpy as np

from aqpy.forecast.adaptive_ar import (
    fit_recursive_least_squares,
    predict_batch,
    recursive_predict,
)
from aqpy.forecast.features import build_ar_feature_matrix


class TestAdaptiveAR(unittest.TestCase):
    def test_fit_and_predict_shapes(self):
        series = np.linspace(10.0, 30.0, 150)
        lags = [1, 2, 3]
        X, y = build_ar_feature_matrix(series, lags)
        model = fit_recursive_least_squares(X, y, forgetting_factor=0.995, delta=100.0)
        yhat = predict_batch(model, X[:20])
        self.assertEqual(len(yhat), 20)
        self.assertTrue(np.isfinite(yhat).all())

    def test_recursive_predict_horizon(self):
        series = np.linspace(0.0, 50.0, 200)
        lags = [1, 2, 4]
        X, y = build_ar_feature_matrix(series, lags)
        model = fit_recursive_least_squares(X, y)
        preds = recursive_predict(model, values=series.tolist(), lags=lags, horizon_steps=7)
        self.assertEqual(len(preds), 7)
        self.assertTrue(all(isinstance(v, float) for v in preds))


if __name__ == "__main__":
    unittest.main()
