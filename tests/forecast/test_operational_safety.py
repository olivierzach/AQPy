import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from aqpy.common.batch import finish_batch
from aqpy.forecast.adaptive_ar import fit_weighted_ar, predict_batch
from aqpy.forecast.features import build_ar_feature_matrix
from aqpy.forecast.repository import insert_predictions
from aqpy.forecast.retention import compute_delete_cutoff, delete_in_batches, run_history_retention
from aqpy.forecast.online_training import run_online_training_step


class OperationalSafetyTests(unittest.TestCase):
    def test_ar_handles_constant_zero_and_collinear_windows(self):
        for values in (np.zeros(5000), np.full(5000, 12.), np.linspace(1000., 1001., 5000)):
            X, y = build_ar_feature_matrix(values, [1, 2, 3, 6, 12])
            model = fit_weighted_ar(X, y)
            pred = predict_batch(model, X)
            self.assertTrue(np.isfinite(pred).all())
            self.assertLess(float(np.mean(abs(pred - y))), 0.1)
            self.assertEqual(model, fit_weighted_ar(X, y))

    def test_ar_rejects_invalid_inputs(self):
        for bad in (float("nan"), float("inf"), -float("inf")):
            with self.assertRaises(ValueError):
                fit_weighted_ar([[1.], [bad]], [1., 2.])

    def test_predictions_rejected_before_any_database_write(self):
        conn = MagicMock()
        for bad in (float("nan"), float("inf"), -float("inf")):
            with self.assertRaisesRegex(ValueError, "prediction.yhat"):
                insert_predictions(conn, [(None, "db", "pi", "x", "m", "v", 1, 1.),
                                          (None, "db", "pi", "x", "m", "v", 2, bad)])
        conn.cursor.assert_not_called()

    def test_batch_failure_is_reported_and_nonzero(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertLogs(level="ERROR"):
            self.assertEqual(finish_batch([{"result": {"status": "trained"}},
                                           {"status": "failed", "error": "broken model"}]), 1)
        self.assertIn("broken model", output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(finish_batch([{"result": {"status": "skipped"}}]), 0)

    def test_raw_retention_protects_untrained_history(self):
        now = dt.datetime.now(dt.timezone.utc)
        watermark = now - dt.timedelta(days=400)
        self.assertEqual(compute_delete_cutoff(now, watermark, 365, 12),
                         watermark - dt.timedelta(hours=12))

    def test_history_retention_rejects_dangerous_cutoffs(self):
        for days in (0, -1):
            with self.assertRaises(ValueError):
                run_history_retention("unused", prediction_days=days)

    def test_retention_commits_bounded_batches(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        type(cur).rowcount = unittest.mock.PropertyMock(side_effect=[3, 3, 1])
        self.assertEqual(delete_in_batches(conn, "predictions", "generated_at < %s", ("cutoff",), batch_size=3), 7)
        self.assertEqual(conn.commit.call_count, 3)

    def training_context(self, stack, path):
        module = "aqpy.forecast.online_training."
        conn = MagicMock()
        stack.enter_context(patch(module + "connect_db", return_value=conn))
        for name in ("ensure_online_tables", "ensure_registry_table", "upsert_training_state", "insert_training_metric"):
            stack.enter_context(patch(module + name))
        stack.enter_context(patch(module + "get_training_state", return_value=None))
        now = dt.datetime.now(dt.timezone.utc)
        values = np.linspace(1., 3., 300)
        stack.enter_context(patch(module + "fetch_series", return_value=(
            [now + dt.timedelta(minutes=i) for i in range(len(values))], values)))
        return conn

    def test_registry_failure_does_not_publish_or_commit_state(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            path = Path(directory) / "model.json"
            original = '{"model_version": "old"}'
            path.write_text(original)
            conn = self.training_context(stack, path)
            stack.enter_context(patch("aqpy.forecast.online_training.insert_or_update_model_registry", side_effect=RuntimeError("registry unavailable")))
            with self.assertRaisesRegex(RuntimeError, "registry unavailable"):
                run_online_training_step("db", "pi", "t", "x", "model", path, model_type="adaptive_ar")
            conn.commit.assert_not_called()
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_corrupt_model_recovers_even_with_no_new_rows(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            path = Path(directory) / "model.json"
            path.write_text('{"theta": [NaN], "model_version": "old"}')
            conn = self.training_context(stack, path)
            stack.enter_context(patch("aqpy.forecast.online_training.get_training_state", return_value={"model_version": "old", "last_seen_ts": dt.datetime.now(dt.timezone.utc)}))
            stack.enter_context(patch("aqpy.forecast.online_training.count_new_rows", return_value=0))
            stack.enter_context(patch("aqpy.forecast.online_training.insert_or_update_model_registry"))
            with self.assertLogs(level="WARNING"):
                result = run_online_training_step("db", "pi", "t", "x", "model", path, model_type="adaptive_ar")
            self.assertEqual(result["status"], "trained")
            artifact = json.loads(path.read_text(), parse_constant=lambda v: self.fail(v))
            self.assertEqual(artifact["solver"], "windowed_weighted_ridge_v1")
            conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
