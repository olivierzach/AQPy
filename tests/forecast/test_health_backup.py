import contextlib
import datetime as dt
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

from aqpy.forecast.health import assess_artifact,check_recent_predictions
from aqpy.forecast.online_repository import insert_training_metric
from aqpy.ingest.repository import PostgresIngestRepository
from aqpy.ingest.service import AQIngestService
from aqpy.common.sensor_backup import backup,rotate


class HealthTests(unittest.TestCase):
    def test_missing_stale_and_nonfinite_forecasts_fail(self):
        now=dt.datetime.now(dt.timezone.utc)
        for rows in ([],[(float('nan'),now)],[(float('inf'),now)],[(1,now-dt.timedelta(hours=2))]):
            with self.assertRaises(ValueError):check_recent_predictions(rows,now,1800)
        check_recent_predictions([(0.,now)],now,1800)

    def test_latest_raw_model_instability_fails_even_when_served_value_is_safe(self):
        now=dt.datetime.now(dt.timezone.utc)
        check_recent_predictions([(0.,now,-.01,'physical_output_v2:nonnegative_projection_v1')],now,1800,'p1')
        for row in [
            (50.,now,160.,'physical_output_v2:physical_persistence_v1'),
            (1.,now,1000.,'physical_output_v2:causal_stability_persistence_v1'),
            (0.,now,-2.,'physical_output_v2:nonnegative_projection_v1'),
            (0.,now,float('nan'),'physical_output_v2:unchanged'),
        ]:
            with self.subTest(row=row),self.assertRaises(ValueError):
                check_recent_predictions([row],now,1800,'p1')

    def test_corrupt_model_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model.json';p.write_text('{"theta":[NaN]}')
            with self.assertRaises(ValueError):assess_artifact({'model_path':p,'model_name':'bad'})

    def test_metric_write_rejects_nonfinite_before_sql(self):
        conn=MagicMock()
        with self.assertRaises(ValueError):insert_training_metric(conn,{'holdout_mae':float('nan')})
        conn.cursor.assert_not_called()

    def test_ingest_rejects_bad_numbers_before_sql(self):
        repo=PostgresIngestRepository.__new__(PostgresIngestRepository)
        repo.cur_pms=MagicMock();repo.cur_bme=MagicMock()
        with self.assertRaises(ValueError):repo.insert_pms_sample({'pm_st':[float('inf')]})
        reading=MagicMock(temperature=float('nan'),humidity=50.,pressure=1000.)
        with self.assertRaises(ValueError):repo.insert_bme_sample(reading)
        repo.cur_pms.execute.assert_not_called();repo.cur_bme.execute.assert_not_called()

    def test_repeated_partial_sensor_failures_fail_service(self):
        task=MagicMock();task.name='bme';task.run_once.side_effect=RuntimeError('bad sample')
        service=AQIngestService([task],MagicMock(),0)
        with self.assertRaisesRegex(RuntimeError,'five consecutive'),self.assertLogs(level='ERROR'):
            service.run_forever(max_cycles=5)


class BackupTests(unittest.TestCase):
    def test_rotation_enforces_age_and_disk_limits(self):
        with tempfile.TemporaryDirectory() as d:
            for day in (1,2,3):Path(d,f'bme-2026-09-0{day}.jsonl.gz').write_bytes(b'x'*100)
            deleted=rotate(d,2,150,today=dt.date(2026,9,3))
            self.assertEqual(len(deleted),2)
            self.assertEqual([p.name for p in Path(d).iterdir()],['bme-2026-09-03.jsonl.gz'])

    def test_protected_partition_budget_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as d:
            name='bme-2026-09-03.jsonl.gz';Path(d,name).write_bytes(b'x'*200)
            with self.assertRaises(RuntimeError):rotate(d,365,100,today=dt.date(2026,9,3),protected=(name,))
            self.assertTrue(Path(d,name).exists())

    def test_snapshot_round_trip(self):
        now=dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=10)
        conn=MagicMock();regular=MagicMock();stream=MagicMock()
        regular.__enter__.return_value=regular;stream.__enter__.return_value=stream
        regular.fetchone.return_value=(now,now)
        stream.description=[('t',),('temperature',)]
        stream.fetchmany.side_effect=[[(now,23.5)],[]]
        conn.cursor.side_effect=[regular,stream]
        with tempfile.TemporaryDirectory() as d,patch('aqpy.common.sensor_backup.connect_db',return_value=conn), \
             patch('aqpy.common.sensor_backup.shutil.disk_usage',return_value=MagicMock(free=10*1024**3)):
            result=backup(d,databases=('bme',))
            file=next(Path(d).glob('*.jsonl.gz'))
            with gzip.open(file,'rt') as f:lines=[json.loads(line) for line in f]
            self.assertEqual(lines[0]['columns'],['t','temperature'])
            self.assertEqual(lines[1],[now.isoformat(),23.5])
            self.assertEqual(result['rows'],1)
            conn.set_session.assert_called_once_with(readonly=True,isolation_level='REPEATABLE READ')

class HoldoutBoundaryTests(unittest.TestCase):
    def test_rnn_fit_excludes_holdout_targets(self):
        import numpy as np
        from aqpy.forecast import online_training as ot
        from aqpy.forecast.rnn_lite import fit_gru_lite_head
        n=240;seq_len=4;ratio=.2
        times=[dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=i) for i in range(n)]
        values=np.linspace(1.,2.,n)
        with tempfile.TemporaryDirectory() as d,contextlib.ExitStack() as stack:
            conn=MagicMock()
            stack.enter_context(patch.object(ot,'connect_db',return_value=conn))
            for name in ('ensure_online_tables','ensure_registry_table','upsert_training_state','insert_training_metric','insert_or_update_model_registry'):
                stack.enter_context(patch.object(ot,name))
            stack.enter_context(patch.object(ot,'get_training_state',return_value=None))
            stack.enter_context(patch.object(ot,'fetch_series',return_value=(times,values)))
            fit=stack.enter_context(patch.object(ot,'fit_gru_lite_head',wraps=fit_gru_lite_head))
            ot.run_online_training_step('db','pi','t','x','model',Path(d)/'model.json',
                model_type='rnn_lite_gru',seq_len=seq_len,hidden_dim=3,holdout_ratio=ratio)
            expected=int((n-seq_len)*(1-ratio))+seq_len
            self.assertEqual(len(fit.call_args.kwargs['values']),expected)
            self.assertLess(expected,n)

class ProcessMemoryLimitTests(unittest.TestCase):
    def test_address_space_limit_rejects_oversized_allocation(self):
        import subprocess,sys
        code='''from aqpy.common.resources import limit_address_space
limit_address_space(128)
try:
    data=bytearray(256*1024**2)
except MemoryError:
    print("bounded")
else:
    raise AssertionError("memory allocation was not capped")
'''
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'bounded')
