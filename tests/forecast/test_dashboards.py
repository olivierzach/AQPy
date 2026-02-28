import json
import unittest
from pathlib import Path


class TestDashboardCoverage(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]

    def _load_dashboard(self, name):
        path = self.repo_root / "grafana" / "dashboards" / name
        return json.loads(path.read_text())

    def test_raw_dashboard_includes_all_pms_raw_series(self):
        raw = self._load_dashboard("aqpy-raw-sensors.json")
        by_title = {panel["title"]: panel for panel in raw["panels"]}

        pm_panel = by_title["Raw PM Mass (ug/m3)"]
        pm_sql = pm_panel["targets"][0]["rawSql"]
        for col in ("pm10_st", "pm25_st", "pm100_st", "pm10_en", "pm25_en", "pm100_en"):
            self.assertIn(col, pm_sql)

        count_panel = by_title["Raw Particle Counts (p1..p6)"]
        count_sql = count_panel["targets"][0]["rawSql"]
        for col in ("p1", "p2", "p3", "p4", "p5", "p6"):
            self.assertIn(f"{col} AS", count_sql)

        aqi_panel = by_title["Derived AQI (PM2.5/PM10)"]
        aqi_sql = aqi_panel["targets"][0]["rawSql"]
        self.assertIn("aqi_pm", aqi_sql)
        self.assertIn("FROM pms_aqi", aqi_sql)

    def test_overview_dashboard_has_pms_prediction_panels_for_all_targets(self):
        overview = self._load_dashboard("aqpy-overview.json")
        panels = overview["panels"]

        expected_targets = {
            "pm10_st",
            "pm25_st",
            "pm100_st",
            "pm10_en",
            "pm25_en",
            "pm100_en",
            "aqi_pm",
            "p1",
            "p2",
            "p3",
            "p4",
            "p5",
            "p6",
        }

        pms_panels = {
            panel["title"]: panel
            for panel in panels
            if panel["title"].startswith("PMS ") and "Actual vs All Models" in panel["title"]
        }
        self.assertEqual(len(pms_panels), len(expected_targets))

        for target in expected_targets:
            title = f"PMS {target}: Actual vs All Models"
            self.assertIn(title, pms_panels)
            sql_blob = "\n".join(t["rawSql"] for t in pms_panels[title]["targets"])
            self.assertIn(f"aqpy_nn_{target}", sql_blob)
            self.assertIn(f"aqpy_ar_{target}", sql_blob)
            self.assertIn(f"aqpy_rnn_{target}", sql_blob)
            if target == "aqi_pm":
                self.assertIn("FROM pms_aqi", sql_blob)


if __name__ == "__main__":
    unittest.main()
