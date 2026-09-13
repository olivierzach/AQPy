import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aqpy.forecast import replay


def spec(family='adaptive_ar'):
    return {'model_name':'test','model_type':family,'database':'unused','table':'pi','time_col':'t','target':'x',
            'burn_in_rows':30,'max_train_rows':60,'min_new_rows':10,'seq_len':4,'lags':[1,2,3],
            'epochs':2,'hidden_dim':3,'forecast_horizon_steps':4,'random_seed':42}


def init(directory,family='adaptive_ar',rows=None):
    path=Path(directory)/'replay.sqlite';conn=replay.open_run(path);replay.schema(conn)
    conn.execute('INSERT INTO meta VALUES (?,?)',('config',replay.dumps({'version':replay.VERSION,
        'interval':300,'max_bytes':10**8,'code_sha256':replay.code_hash()})))
    replay.add_tape(conn,spec(family), rows if rows is not None else [(i*60,10+i%7) for i in range(100)],300)
    conn.commit();conn.close()


def predictions(directory):
    conn=replay.open_run(Path(directory)/'replay.sqlite')
    try:return [tuple(r) for r in conn.execute('SELECT * FROM predictions ORDER BY issued_at,horizon')]
    finally:conn.close()


class ReplayTests(unittest.TestCase):
    def test_future_values_do_not_change_earlier_predictions_for_any_family(self):
        for family in replay.FAMILIES:
            with self.subTest(family=family), tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
                init(a,family)
                init(b,family,[(i*60,10+i%7 if i<60 else 10000+i) for i in range(100)])
                replay.run(a,seconds=60,check_resources=False)
                replay.run(b,seconds=60,check_resources=False)
                # Compare forecasts issued strictly before the changed future, not their revealed outcomes.
                before=lambda d:[r[:7] for r in predictions(d) if r[1]<60*60]
                self.assertEqual(before(a),before(b))
                for r in predictions(a):
                    self.assertLessEqual(r[4],r[1])
                    if r[8] is not None:self.assertGreater(r[8],r[1])

    def test_resume_exactly_matches_uninterrupted_all_families(self):
        for family in replay.FAMILIES:
            with self.subTest(family=family), tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
                init(a,family);init(b,family)
                replay.run(a,seconds=60,check_resources=False)
                replay.run(b,seconds=60,max_events=3,check_resources=False)
                replay.run(b,seconds=60,check_resources=False)
                self.assertEqual(predictions(a),predictions(b))
                self.assertTrue(replay.status(b)['complete'])

    def test_fit_and_prediction_failure_leave_checkpoint_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            init(d)
            initial=replay.status(d)
            with patch.object(replay,'predict',side_effect=ValueError('non-finite model')):
                with self.assertRaises(ValueError):replay.run(d,check_resources=False)
            self.assertEqual(replay.status(d),initial)
            self.assertEqual(predictions(d),[])

    def test_failed_scoring_transaction_rolls_back_everything(self):
        with tempfile.TemporaryDirectory() as d:
            init(d);initial=replay.status(d)
            with patch.object(replay,'reveal',side_effect=RuntimeError('interrupted transaction')):
                with self.assertRaises(RuntimeError):replay.run(d,check_resources=False)
            self.assertEqual(replay.status(d),initial)
            self.assertEqual(predictions(d),[])

    def test_partial_run_has_no_scores_for_unrevealed_observations(self):
        with tempfile.TemporaryDirectory() as d:
            init(d,rows=[(i*60,10+i%7) for i in range(99)]);replay.run(d,max_events=1,check_resources=False)
            self.assertTrue(all(r[7] is None for r in predictions(d)))
            replay.run(d,seconds=60,check_resources=False)
            self.assertTrue(any(r[7] is None for r in predictions(d))) # beyond tape end remains unscored

    def test_invalid_and_duplicate_tapes_fail(self):
        for rows in ([(0,1),(0,2)],[(0,1),(60,float('nan'))],[(0,1),(60,None)]):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises((ValueError,TypeError)):init(d,rows=rows)

    def test_zero_series_exports_finite_scores_with_defined_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            init(d,rows=[(i*60,0) for i in range(100)])
            replay.run(d,seconds=60,check_resources=False)
            scores=replay.export(d)
            self.assertTrue(scores)
            self.assertTrue(all(s['mae']==0 and s['rmse']==0 and s['mae_improvement_pct'] is None for s in scores))

    def test_window_is_bounded_and_resource_pause_preserves_progress(self):
        with tempfile.TemporaryDirectory() as d:
            init(d)
            original=replay.fit
            sizes=[]
            def fit(s,values,seed):
                sizes.append(len(values));return original(s,values,seed)
            with patch.object(replay,'fit',side_effect=fit):replay.run(d,seconds=60,check_resources=False)
            self.assertLessEqual(max(sizes),60)
        with tempfile.TemporaryDirectory() as d:
            init(d);initial=replay.status(d)
            with patch.object(replay,'pause_reason',return_value='live service active'):
                replay.run(d)
            self.assertEqual(initial,replay.status(d))

    def test_code_change_requires_new_run(self):
        with tempfile.TemporaryDirectory() as d:
            init(d)
            with patch.object(replay,'code_hash',return_value='changed'):
                with self.assertRaisesRegex(RuntimeError,'implementation changed'):replay.run(d,check_resources=False)

    def test_export_budget_failure_keeps_database_and_no_partial_csv(self):
        with tempfile.TemporaryDirectory() as d:
            init(d);replay.run(d,seconds=60,check_resources=False)
            conn=replay.open_run(Path(d)/'replay.sqlite')
            cfg=json.loads(conn.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0]);cfg['max_bytes']=1
            conn.execute("UPDATE meta SET value=? WHERE key='config'",(json.dumps(cfg),));conn.commit();conn.close()
            with self.assertRaisesRegex(RuntimeError,'storage budget'):replay.export(d)
            self.assertTrue((Path(d)/'replay.sqlite').exists())
            self.assertFalse((Path(d)/'predictions.csv.partial').exists())

    def test_snapshot_initialization_is_readonly_and_publishes_complete_tape(self):
        from unittest.mock import MagicMock
        import datetime as dt
        conn=MagicMock();regular=MagicMock();stream=MagicMock()
        regular.__enter__.return_value=regular;stream.__enter__.return_value=stream
        stream.__iter__.return_value=iter([(dt.datetime.fromtimestamp(i*60,dt.timezone.utc),10+i%7) for i in range(100)])
        conn.cursor.side_effect=[regular,stream]
        with tempfile.TemporaryDirectory() as d,patch('aqpy.common.db.connect_db',return_value=conn), \
             patch('aqpy.forecast.replay.shutil.disk_usage',return_value=MagicMock(free=10*1024**3)), \
             patch('aqpy.forecast.replay.storage_bytes',return_value=0):
            result=replay.initialize(d,[spec()],max_bytes=10**7)
            self.assertFalse(result['complete'])
            self.assertEqual(result['predictions'],0)
            db=replay.open_run(Path(d)/'replay.sqlite')
            self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0],100)
            db.close()
            self.assertFalse((Path(d)/'snapshot.partial').exists())
            conn.set_session.assert_called_once_with(readonly=True,isolation_level='REPEATABLE READ')
