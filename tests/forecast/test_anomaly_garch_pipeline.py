import datetime as dt
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

psycopg2 = types.ModuleType("psycopg2")
extras = types.ModuleType("psycopg2.extras")
extras.Json = lambda value: value
psycopg2.extras = extras
sys.modules.setdefault("psycopg2", psycopg2)
sys.modules.setdefault("psycopg2.extras", extras)

from aqpy.forecast.backfill import run_backfill
from aqpy.forecast.inference import run_inference
from aqpy.forecast.online_training import run_online_training_step


class _DummyConn:
    def close(self):
        return None


class TestAnomalyGarchPipeline(unittest.TestCase):
    def _write_model(self, payload):
        td = tempfile.TemporaryDirectory()
        path = Path(td.name) / "model.json"
        path.write_text(json.dumps(payload))
        return td, path

    @patch("aqpy.forecast.inference.insert_garch_forecasts")
    @patch("aqpy.forecast.inference.fetch_recent_series")
    @patch("aqpy.forecast.inference.ensure_anomaly_events_table")
    @patch("aqpy.forecast.inference.ensure_garch_forecasts_table")
    @patch("aqpy.forecast.inference.ensure_predictions_table")
    @patch("aqpy.forecast.inference.connect_db", return_value=_DummyConn())
    def test_run_inference_garch_does_not_require_lag_history(
        self,
        _connect_db,
        _ensure_predictions,
        _ensure_garch,
        _ensure_anomaly,
        fetch_recent_series,
        insert_garch_forecasts,
    ):
        fetch_recent_series.return_value = (
            [
                dt.datetime(2026, 3, 28, 12, 0, tzinfo=dt.timezone.utc),
                dt.datetime(2026, 3, 28, 12, 1, tzinfo=dt.timezone.utc),
            ],
            [101.0, 101.5],
        )
        td, model_path = self._write_model(
            {
                "model_type": "garch_11",
                "model_name": "aqpy_garch_temperature",
                "model_version": "v1",
                "database": "bme",
                "table": "pi",
                "time_col": "t",
                "target": "temperature",
                "lags": [1, 2, 3, 6, 12],
                "cadence_seconds": 60,
                "omega": 0.05,
                "alpha": 0.1,
                "beta": 0.85,
                "mean_return": 0.2,
                "last_sigma2": 0.4,
            }
        )
        try:
            result = run_inference(str(model_path), horizon_steps=2)
        finally:
            td.cleanup()

        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["output_table"], "garch_forecasts")
        rows = insert_garch_forecasts.call_args.args[1]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], dt.datetime(2026, 3, 28, 12, 2, tzinfo=dt.timezone.utc))

    @patch("aqpy.forecast.backfill.insert_anomaly_events")
    @patch("aqpy.forecast.backfill.ensure_anomaly_events_table")
    @patch("aqpy.forecast.backfill.ensure_garch_forecasts_table")
    @patch("aqpy.forecast.backfill.ensure_predictions_table")
    @patch("aqpy.forecast.backfill._fetch_series_for_window")
    @patch("aqpy.forecast.backfill.connect_db", return_value=_DummyConn())
    def test_run_backfill_anomaly_accepts_small_scoring_window(
        self,
        _connect_db,
        fetch_series,
        _ensure_predictions,
        _ensure_garch,
        _ensure_anomaly,
        insert_anomaly_events,
    ):
        fetch_series.return_value = (
            [
                dt.datetime(2026, 3, 28, 12, 0, tzinfo=dt.timezone.utc),
                dt.datetime(2026, 3, 28, 12, 1, tzinfo=dt.timezone.utc),
            ],
            [10.0, 25.0],
            1,
        )
        td, model_path = self._write_model(
            {
                "model_type": "anomaly_ewma",
                "model_name": "aqpy_anom_ewma_temperature",
                "model_version": "v1",
                "database": "bme",
                "table": "pi",
                "time_col": "t",
                "target": "temperature",
                "score_window": 2,
                "alpha": 0.2,
                "ewma_init": 10.0,
                "var_init": 1.0,
                "threshold": 3.0,
            }
        )
        try:
            result = run_backfill(str(model_path), backfill_hours=1, replace_existing=False)
        finally:
            td.cleanup()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["output_table"], "anomaly_events")
        rows = insert_anomaly_events.call_args.args[1]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], dt.datetime(2026, 3, 28, 12, 1, tzinfo=dt.timezone.utc))

    @patch("aqpy.forecast.online_training.insert_or_update_model_registry")
    @patch("aqpy.forecast.online_training.insert_training_metric")
    @patch("aqpy.forecast.online_training.upsert_training_state")
    @patch("aqpy.forecast.online_training.ensure_registry_table")
    @patch("aqpy.forecast.online_training.ensure_online_tables")
    @patch("aqpy.forecast.online_training.get_training_state", return_value=None)
    @patch("aqpy.forecast.online_training.fetch_series")
    @patch("aqpy.forecast.online_training.connect_db", return_value=_DummyConn())
    def test_run_online_training_garch_uses_garch_minimum_not_lag_minimum(
        self,
        _connect_db,
        fetch_series,
        _get_training_state,
        _ensure_online,
        _ensure_registry,
        _upsert_training_state,
        _insert_training_metric,
        _insert_registry,
    ):
        timestamps = [
            dt.datetime(2026, 3, 28, 12, 0, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=i)
            for i in range(20)
        ]
        values = [100.0 + (i * 0.1) for i in range(20)]
        fetch_series.return_value = (timestamps, values)
        with tempfile.TemporaryDirectory() as td:
            model_path = Path(td) / "garch.json"
            result = run_online_training_step(
                database="bme",
                table="pi",
                time_col="t",
                target="temperature",
                model_name="aqpy_garch_temperature",
                model_path=str(model_path),
                model_type="garch_11",
                burn_in_rows=10,
                holdout_ratio=0.25,
                lags=[1, 2, 3, 6, 12],
                garch_alpha=0.1,
                garch_beta=0.85,
            )

        self.assertEqual(result["status"], "trained")


if __name__ == "__main__":
    unittest.main()
