import json
import unittest
from collections import defaultdict
from pathlib import Path


MODEL_TYPES = {"nn_mlp", "adaptive_ar", "rnn_lite_gru"}
MODEL_PREFIX = {
    "nn_mlp": "aqpy_nn_",
    "adaptive_ar": "aqpy_ar_",
    "rnn_lite_gru": "aqpy_rnn_",
}
MODEL_PATH_SUFFIX = {
    "nn_mlp": "_nn.json",
    "adaptive_ar": "_ar.json",
    "rnn_lite_gru": "_rnn.json",
}


def parse_schema_targets(schema_path):
    targets = []
    in_table = False
    for raw in schema_path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("CREATE TABLE"):
            in_table = True
            continue
        if in_table and line.startswith(");"):
            break
        if not in_table:
            continue
        col = line.split()[0].rstrip(",")
        if col == "t":
            continue
        targets.append(col)
    return targets


class TestModelCoverageMatrix(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.specs = json.loads((self.repo_root / "configs" / "model_specs.json").read_text())

    def test_schema_targets_have_full_model_family_coverage(self):
        db_to_schema = {
            "bme": self.repo_root / "sql" / "raw_schema_bme.sql",
            "pms": self.repo_root / "sql" / "raw_schema_pms.sql",
        }

        for database, schema in db_to_schema.items():
            expected_targets = set(parse_schema_targets(schema))
            seen = defaultdict(set)
            for spec in self.specs:
                if spec["database"] == database and spec["table"] == "pi":
                    seen[spec["target"]].add(spec["model_type"])

            self.assertEqual(
                set(seen.keys()),
                expected_targets,
                msg=f"{database}: spec targets do not match schema targets",
            )
            for target in expected_targets:
                self.assertEqual(
                    seen[target],
                    MODEL_TYPES,
                    msg=f"{database}.{target}: incomplete model-family coverage",
                )

    def test_derived_aqi_metric_has_full_family_coverage(self):
        seen = defaultdict(set)
        for spec in self.specs:
            if spec["database"] == "pms" and spec["table"] == "pms_aqi":
                seen[spec["target"]].add(spec["model_type"])

        self.assertEqual(set(seen.keys()), {"aqi_pm"})
        self.assertEqual(
            seen["aqi_pm"],
            MODEL_TYPES,
            msg="pms_aqi.aqi_pm: incomplete model-family coverage",
        )

    def test_model_naming_and_paths_follow_convention(self):
        for spec in self.specs:
            model_type = spec["model_type"]
            target = spec["target"]
            database = spec["database"]

            expected_name = f"{MODEL_PREFIX[model_type]}{target}"
            self.assertEqual(
                spec["model_name"],
                expected_name,
                msg=f"Bad model_name for {database}.{target}/{model_type}",
            )

            expected_path = f"models/{database}_{target}{MODEL_PATH_SUFFIX[model_type]}"
            self.assertEqual(
                spec["model_path"],
                expected_path,
                msg=f"Bad model_path for {database}.{target}/{model_type}",
            )


if __name__ == "__main__":
    unittest.main()
