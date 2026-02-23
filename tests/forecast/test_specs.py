import tempfile
import unittest
from pathlib import Path

from aqpy.forecast.specs import load_model_specs


def write_specs(payload):
    td = tempfile.TemporaryDirectory()
    path = Path(td.name) / "specs.json"
    path.write_text(payload)
    return td, path


class TestModelSpecsValidation(unittest.TestCase):
    def test_valid_specs_load(self):
        td, path = write_specs(
            """
[
  {
    "model_name": "aqpy_nn_temperature",
    "model_type": "nn_mlp",
    "database": "bme",
    "table": "pi",
    "time_col": "t",
    "target": "temperature",
    "model_path": "models/bme_temperature_nn.json",
    "history_hours": 24,
    "burn_in_rows": 10,
    "max_train_rows": 100,
    "lags": [1, 2, 3],
    "holdout_ratio": 0.2,
    "min_new_rows": 5,
    "learning_rate": 0.01,
    "epochs": 10,
    "batch_size": 16,
    "hidden_dim": 8,
    "forecast_horizon_steps": 12
  }
]
"""
        )
        try:
            specs = load_model_specs(path)
            self.assertEqual(len(specs), 1)
        finally:
            td.cleanup()

    def test_duplicate_model_name_rejected(self):
        td, path = write_specs(
            """
[
  {
    "model_name": "dup",
    "model_type": "nn_mlp",
    "database": "bme",
    "table": "pi",
    "time_col": "t",
    "target": "temperature",
    "model_path": "models/a.json",
    "lags": [1]
  },
  {
    "model_name": "dup",
    "model_type": "adaptive_ar",
    "database": "bme",
    "table": "pi",
    "time_col": "t",
    "target": "humidity",
    "model_path": "models/b.json",
    "lags": [1]
  }
]
"""
        )
        try:
            with self.assertRaises(ValueError):
                load_model_specs(path)
        finally:
            td.cleanup()

    def test_nn_without_lags_rejected(self):
        td, path = write_specs(
            """
[
  {
    "model_name": "bad_nn",
    "model_type": "nn_mlp",
    "database": "bme",
    "table": "pi",
    "time_col": "t",
    "target": "temperature",
    "model_path": "models/bad.json"
  }
]
"""
        )
        try:
            with self.assertRaises(ValueError):
                load_model_specs(path)
        finally:
            td.cleanup()

    def test_rnn_without_seq_len_rejected(self):
        td, path = write_specs(
            """
[
  {
    "model_name": "bad_rnn",
    "model_type": "rnn_lite_gru",
    "database": "bme",
    "table": "pi",
    "time_col": "t",
    "target": "temperature",
    "model_path": "models/bad_rnn.json"
  }
]
"""
        )
        try:
            with self.assertRaises(ValueError):
                load_model_specs(path)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
