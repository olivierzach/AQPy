import datetime as dt
import unittest

import numpy as np

from aqpy.forecast.nn_model import predict_batch, train_mlp_regressor,rebase_params
from aqpy.forecast.retention import compute_delete_cutoff


class TestNNOnline(unittest.TestCase):
    def test_rebase_preserves_predictions_under_changed_normalization(self):
        rng=np.random.default_rng(23)
        X=rng.normal(size=(100,4));y=2*X[:,0]+10
        old=train_mlp_regressor(X,y,epochs=3,seed=23)
        original=predict_batch(old,X)
        new_mean=np.array([3.,-5.,1.,10.]);new_std=np.array([.2,5.,2.,7.])
        params=rebase_params(old,new_mean,new_std,30.,4.)
        rebased={**old,**{k:v.tolist() for k,v in params.items()},'x_mean':new_mean.tolist(),
                 'x_std':new_std.tolist(),'y_mean':30.,'y_std':4.}
        np.testing.assert_allclose(predict_batch(rebased,X),original,rtol=1e-10,atol=1e-10)
        # The source artifact is unchanged by rebasing.
        np.testing.assert_array_equal(predict_batch(old,X),original)

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
