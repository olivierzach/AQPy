import unittest

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


if __name__ == "__main__":
    unittest.main()
