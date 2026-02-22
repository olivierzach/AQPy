import unittest

import numpy as np

from aqpy.forecast.features import build_feature_matrix
from aqpy.forecast.model import fit_linear_regression, recursive_predict, split_train_val


class TestForecastFeaturesModel(unittest.TestCase):
    def test_build_feature_matrix_shape(self):
        values = np.array([10, 11, 12, 13, 14, 15, 16], dtype=float)
        lags = [1, 2, 3]
        X, y = build_feature_matrix(values, lags)

        self.assertEqual(X.shape[0], len(values) - max(lags))
        self.assertEqual(X.shape[1], len(lags) + 2)
        self.assertEqual(y.shape[0], X.shape[0])

    def test_recursive_predict_returns_requested_horizon(self):
        values = np.array([1, 2, 3, 4, 5, 6, 7], dtype=float)
        lags = [1, 2, 3]
        X, y = build_feature_matrix(values, lags)
        X_train, _, y_train, _ = split_train_val(X, y)
        intercept, weights = fit_linear_regression(X_train, y_train)
        preds = recursive_predict(values.tolist(), lags, intercept, weights, horizon_steps=5)

        self.assertEqual(len(preds), 5)
        self.assertTrue(all(isinstance(p, float) for p in preds))


if __name__ == "__main__":
    unittest.main()
