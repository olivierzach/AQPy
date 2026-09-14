import contextlib
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from aqpy.forecast.stability import assess
from aqpy.forecast.inference import run_inference
from aqpy.forecast.online_training import run_online_training_step
from tests.forecast import test_operational_safety as safety


class StabilityTests(unittest.TestCase):
    model = {'model_type': 'nn_mlp', 'lags': [1, 2], 'target': 'pm10_en'}

    def test_late_recursive_failure_rejected_even_if_first_step_small(self):
        with patch('aqpy.forecast.stability.nn_model.recursive_predict', return_value=[-.003] * 11 + [-2.08]):
            with self.assertRaisesRegex(ValueError, 'step=12'):
                assess(self.model, [0.] * 200, 160)

    def test_zero_readings_are_valid_and_scores_are_unclipped(self):
        with patch('aqpy.forecast.stability.nn_model.recursive_predict', return_value=[-.01] * 12):
            result = assess(self.model, [0.] * 200, 160)
        self.assertEqual(result['status'], 'PASS')
        self.assertAlmostEqual(result['sampled_recursive_mae'], .01)
        self.assertEqual(result['sampled_persistence_mae'], 0.)

    def test_nonfinite_and_large_positive_excursions_rejected(self):
        for value in [float('nan'), float('inf'), 1000.]:
            with self.subTest(value=value), patch('aqpy.forecast.stability.nn_model.recursive_predict', return_value=[value] * 12):
                with self.assertRaises(ValueError):
                    assess(self.model, [0.] * 200, 160)

    def test_missing_and_stale_inference_does_not_write_predictions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'model.json'
            p.write_text(json.dumps({**self.model, 'database': 'pms', 'table': 'pi', 'time_col': 't'}))
            for readings in [([], []), ([dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)], [0.])]:
                with patch('aqpy.forecast.inference.connect_db', return_value=MagicMock()), patch('aqpy.forecast.inference.ensure_predictions_table'), patch('aqpy.forecast.inference.fetch_recent_series', return_value=readings), patch('aqpy.forecast.inference.insert_predictions') as write:
                    self.assertEqual(run_inference(p)['status'], 'skipped')
                    write.assert_not_called()

    def test_rejection_leaves_old_model_and_training_state_intact(self):
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            p = Path(d) / 'model.json';p.write_text('{"model_version":"old"}')
            conn = safety.OperationalSafetyTests().training_context(stack, p)
            writes = [stack.enter_context(patch('aqpy.forecast.online_training.' + name)) for name in ['upsert_training_state', 'insert_training_metric', 'insert_or_update_model_registry']]
            stack.enter_context(patch('aqpy.forecast.online_training.assess_stability', side_effect=ValueError('unstable')))
            with self.assertRaisesRegex(ValueError, 'unstable'):
                run_online_training_step('db','pi','t','x','m',p,model_type='adaptive_ar')
            for write in writes:write.assert_not_called()
            conn.commit.assert_not_called()
            self.assertEqual(json.loads(p.read_text()), {'model_version':'old'})

    def test_missing_training_readings_skip_without_publishing(self):
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            p = Path(d) / 'model.json'
            conn = safety.OperationalSafetyTests().training_context(stack, p)
            stack.enter_context(patch('aqpy.forecast.online_training.fetch_series', return_value=([], [])))
            self.assertEqual(run_online_training_step('db','pi','t','x','m',p)['status'], 'skipped')
            conn.commit.assert_not_called();self.assertFalse(p.exists())

    def test_training_all_zero_observations_is_valid(self):
        from aqpy.forecast.features import build_feature_matrix
        from aqpy.forecast.nn_model import train_mlp_regressor
        values = np.zeros(200)
        X, y = build_feature_matrix(values, [1, 2])
        model = {**train_mlp_regressor(X[:150], y[:150], epochs=5), **self.model}
        result = assess(model, values, 152)
        self.assertEqual(result['status'], 'PASS')
        self.assertLess(abs(result['raw_max']), .01)

    def test_stale_training_readings_skip_without_publishing(self):
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            p = Path(d) / 'model.json'
            conn = safety.OperationalSafetyTests().training_context(stack, p)
            old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)
            stack.enter_context(patch('aqpy.forecast.online_training.fetch_series', return_value=([old] * 300, [0.] * 300)))
            self.assertEqual(run_online_training_step('db','pi','t','x','m',p)['status'], 'skipped')
            conn.commit.assert_not_called();self.assertFalse(p.exists())

    def test_fresh_retry_rescores_the_accepted_candidate(self):
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            p = Path(d) / 'model.json'
            p.write_text(json.dumps({'database':'db','table':'pi','target':'x',
                                    'model_type':'nn_mlp','hidden_dim':8,'input_dim':7}))
            conn = safety.OperationalSafetyTests().training_context(stack, p)
            stack.enter_context(patch('aqpy.forecast.online_training.insert_or_update_model_registry'))
            fit = stack.enter_context(patch('aqpy.forecast.online_training.train_mlp_regressor',
                side_effect=[{'tag':'continued','train_loss':100.}, {'tag':'fresh','train_loss':1.}]))
            stack.enter_context(patch('aqpy.forecast.online_training.predict_batch',
                side_effect=lambda m, X: np.full(len(X), 20. if m['tag']=='continued' else 2.)))
            gate = stack.enter_context(patch('aqpy.forecast.online_training.assess_stability',
                side_effect=[ValueError('unstable rollout'), {'status':'PASS'}]))
            result = run_online_training_step('db','pi','t','x','m',p)
            artifact = json.loads(p.read_text())
            self.assertEqual(fit.call_count, 2)
            self.assertEqual(gate.call_count, 2)
            self.assertEqual(artifact['tag'], 'fresh')
            self.assertEqual(artifact['metrics']['train_loss'], 1.)
            self.assertLess(result['holdout_mae'], 1.)
            self.assertEqual(artifact['stability']['initialization'], 'fresh_after_unstable_continuation')
            conn.commit.assert_called_once()
