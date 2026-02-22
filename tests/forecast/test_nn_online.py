import datetime as dt
import unittest

import numpy as np

from aqpy.forecast.nn_model import predict_batch, train_mlp_regressor
from aqpy.forecast.retention import compute_delete_cutoff


class TestNNOnline(unittest.TestCase):
    def test_train_mlp_and_predict_batch(self):
        rng = np.random.default_rng(7)
        X = rng.normal(size=(120, 4))
        y = 0.5 * X[:, 0] - 0.2 * X[:, 1] + 0.1 * X[:, 2] + 2.0
        model = train_mlp_regressor(
            X_train=X,
            y_train=y,
            hidden_dim=6,
            learning_rate=0.02,
            epochs=25,
            batch_size=32,
            seed=7,
        )
        preds = predict_batch(model, X[:10])
        self.assertEqual(len(preds), 10)
        self.assertTrue(np.isfinite(preds).all())

    def test_compute_delete_cutoff_uses_retention_and_training_watermark(self):
        now_utc = dt.datetime(2026, 2, 22, tzinfo=dt.timezone.utc)
        min_last_seen = now_utc - dt.timedelta(days=9)
        cutoff = compute_delete_cutoff(
            now_utc=now_utc,
            min_last_seen_ts=min_last_seen,
            retention_days=14,
            safety_hours=12,
        )
        expected = min(
            now_utc - dt.timedelta(days=14),
            min_last_seen - dt.timedelta(hours=12),
        )
        self.assertEqual(cutoff, expected)


if __name__ == "__main__":
    unittest.main()
