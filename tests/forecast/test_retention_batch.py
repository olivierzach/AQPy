import unittest
import os
from unittest.mock import patch
import run_data_retention_batch as batch

from run_data_retention_batch import collect_retention_sources


class TestRetentionBatchSourceSelection(unittest.TestCase):
    def test_collect_retention_sources_includes_raw_and_predictions(self):
        specs = [
            {"database": "bme", "table": "pi", "time_col": "t"},
            {"database": "pms", "table": "pi", "time_col": "t"},
            {"database": "pms", "table": "pms_aqi", "time_col": "t"},
        ]

        sources, skipped = collect_retention_sources(
            specs=specs,
            raw_retention_days=180,
            raw_safety_hours=24,
            pred_retention_days=180,
            pred_safety_hours=0,
        )

        source_keys = {(s["database"], s["table"], s["time_col"]) for s in sources}
        self.assertEqual(
            source_keys,
            {
                ("bme", "pi", "t"),
                ("pms", "pi", "t"),
                ("bme", "predictions", "predicted_for"),
                ("pms", "predictions", "predicted_for"),
            },
        )
        for source in sources:
            if source["table"] == "pi":
                self.assertTrue(source["use_training_watermark"])
                self.assertEqual(source["retention_days"], 180)
                self.assertEqual(source["safety_hours"], 24)
            if source["table"] == "predictions":
                self.assertFalse(source["use_training_watermark"])
                self.assertEqual(source["retention_days"], 180)
                self.assertEqual(source["safety_hours"], 0)

        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["table"], "pms_aqi")
        self.assertIn("raw retention skipped", skipped[0]["reason"])


class TestReconciledRetention(unittest.TestCase):
    def test_source_failure_continues_history_cleanup_and_returns_failure(self):
        specs = [{"database": "pms", "table": "pi", "time_col": "t"},
                 {"database": "pms", "table": "pms_aqi", "time_col": "t"}]
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", ["retention"]):
            args = batch.parse_args()
        with patch.object(batch, "parse_args", return_value=args), \
             patch.object(batch, "load_model_specs", return_value=specs), \
             patch.object(batch, "filter_specs", return_value=specs), \
             patch.object(batch, "run_retention", side_effect=RuntimeError("database unavailable")) as raw, \
             patch.object(batch, "run_history_retention", return_value={"status": "ok"}) as history, \
             patch("builtins.print"), self.assertLogs(level="ERROR"):
            self.assertEqual(batch.main(), 1)
        self.assertEqual(raw.call_count, 1)
        self.assertEqual(raw.call_args.kwargs["table"], "pi")
        history.assert_called_once_with("pms", 180, 365)

    def test_upstream_settings_and_repair_aliases(self):
        with patch.dict(os.environ, {"AQPY_RAW_RETENTION_DAYS": "400",
                                    "AQPY_RETENTION_DAYS_RAW": "500",
                                    "AQPY_PREDICTION_RETENTION_DAYS": "200"}, clear=True), \
             patch("sys.argv", ["retention"]):
            args = batch.parse_args()
        self.assertEqual(args.raw_retention_days, 500)
        self.assertEqual(args.pred_retention_days, 200)
        with patch.dict(os.environ, {}, clear=True), \
             patch("sys.argv", ["retention", "--retention-days", "450", "--prediction-days", "210"]):
            args = batch.parse_args()
        self.assertEqual(args.raw_retention_days, 450)
        self.assertEqual(args.pred_retention_days, 210)


if __name__ == "__main__":
    unittest.main()
