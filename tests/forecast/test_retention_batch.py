import unittest

from run_data_retention_batch import collect_retention_sources


class TestRetentionBatchSourceSelection(unittest.TestCase):
    def test_collect_retention_sources_skips_non_raw_tables(self):
        specs = [
            {"database": "bme", "table": "pi", "time_col": "t"},
            {"database": "pms", "table": "pi", "time_col": "t"},
            {"database": "pms", "table": "pms_aqi", "time_col": "t"},
        ]

        sources, skipped = collect_retention_sources(specs)

        self.assertEqual(set(sources), {("bme", "pi", "t"), ("pms", "pi", "t")})
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["table"], "pms_aqi")
        self.assertIn("skipped retention", skipped[0]["reason"])


if __name__ == "__main__":
    unittest.main()
