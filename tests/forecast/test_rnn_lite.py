import unittest

import numpy as np

from aqpy.forecast.rnn_lite import (
    build_sequence_dataset,
    fit_gru_lite_head,
    recursive_predict,
)


class TestRNNLiteGRU(unittest.TestCase):
    def test_build_sequence_dataset_shapes(self):
        vals = np.arange(40, dtype=float)
        X_seq, y = build_sequence_dataset(vals, seq_len=8)
        self.assertEqual(X_seq.shape[0], len(vals) - 8)
        self.assertEqual(X_seq.shape[1], 8)
        self.assertEqual(y.shape[0], X_seq.shape[0])

    def test_fit_and_recursive_predict(self):
        x = np.linspace(0, 8 * np.pi, 240)
        vals = np.sin(x) + 0.05 * np.cos(2 * x)
        model = fit_gru_lite_head(vals, seq_len=24, hidden_dim=8, seed=11)
        preds = recursive_predict(model, values=vals.tolist(), horizon_steps=6)
        self.assertEqual(len(preds), 6)
        self.assertTrue(np.isfinite(np.array(preds)).all())


if __name__ == "__main__":
    unittest.main()
