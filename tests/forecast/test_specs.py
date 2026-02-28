import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from aqpy.forecast.specs import filter_specs, load_model_specs


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

    def test_filter_specs_by_target_and_family(self):
        specs = [
            {
                "model_name": "aqpy_nn_temperature",
                "model_type": "nn_mlp",
                "database": "bme",
                "table": "pi",
                "time_col": "t",
                "target": "temperature",
                "model_path": "models/bme_temperature_nn.json",
            },
            {
                "model_name": "aqpy_ar_humidity",
                "model_type": "adaptive_ar",
                "database": "bme",
                "table": "pi",
                "time_col": "t",
                "target": "humidity",
                "model_path": "models/bme_humidity_ar.json",
            },
            {
                "model_name": "aqpy_rnn_pressure",
                "model_type": "rnn_lite_gru",
                "database": "bme",
                "table": "pi",
                "time_col": "t",
                "target": "pressure",
                "model_path": "models/bme_pressure_rnn.json",
            },
        ]
        filtered = filter_specs(
            specs,
            targets=["pressure", "temperature"],
            families=["rnn", "nn"],
        )
        self.assertEqual({s["model_name"] for s in filtered}, {"aqpy_nn_temperature", "aqpy_rnn_pressure"})

    def test_repo_specs_cover_all_pms_targets_for_all_families(self):
        repo_root = Path(__file__).resolve().parents[2]
        specs = load_model_specs(repo_root / "configs" / "model_specs.json")

        expected_targets = {
            "pm10_st",
            "pm25_st",
            "pm100_st",
            "pm10_en",
            "pm25_en",
            "pm100_en",
            "p1",
            "p2",
            "p3",
            "p4",
            "p5",
            "p6",
        }
        expected_model_types = {"nn_mlp", "adaptive_ar", "rnn_lite_gru"}

        coverage = defaultdict(set)
        for spec in specs:
            if spec["database"] == "pms":
                coverage[spec["target"]].add(spec["model_type"])

        self.assertEqual(set(coverage.keys()), expected_targets)
        for target in expected_targets:
            self.assertEqual(
                coverage[target],
                expected_model_types,
                msg=f"Incomplete PMS model coverage for target '{target}'",
            )


if __name__ == "__main__":
    unittest.main()
