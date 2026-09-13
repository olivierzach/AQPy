import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from aqpy.forecast.repair_inventory import analyze,open_inventory
from aqpy.forecast import targeted_repair as repair


def fixture(directory,family='adaptive_ar',future_change=False,prepare=True):
    root=Path(directory);conn=open_inventory(root)
    conn.executescript('''CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
      CREATE TABLE sources(source TEXT PRIMARY KEY,rows INTEGER,first REAL,last REAL,sha256 TEXT);
      CREATE TABLE samples(source TEXT,seq INTEGER,ts REAL,y REAL,PRIMARY KEY(source,seq),UNIQUE(source,ts));
      CREATE TABLE models(model TEXT PRIMARY KEY,spec TEXT,rows INTEGER,sha256 TEXT);
      CREATE TABLE forecasts(model TEXT,id INTEGER,generated REAL,target_ts REAL,horizon INTEGER,yhat REAL,version TEXT,trained_at REAL);''')
    spec={'model_name':'test','model_type':family,'database':'pms','table':'pi','target':'p1','time_col':'t',
          'burn_in_rows':30,'max_train_rows':60,'min_new_rows':10,'lags':[1,2,3],'seq_len':4,'hidden_dim':3,
          'epochs':2,'forecast_horizon_steps':4,'random_seed':42}
    conn.execute('INSERT INTO models VALUES (?,?,?,?)',('test',json.dumps(spec),4,'fixture'))
    for source in ['pms.pi.p1','pms.pms_aqi_v2.aqi_pm']:
        conn.execute('INSERT INTO sources VALUES (?,?,?,?,?)',(source,100,0,5940,'fixture'))
        conn.executemany('INSERT INTO samples VALUES (?,?,?,?)',[(source,i,i*60,10+i%3+(100 if future_change and i*60>=4500 else 0)) for i in range(100)])
    conn.executemany('INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?)',[
        ('test',1,1800,1860,1,10,'v',1700),('test',2,1800,1920,2,-.5,'v',1700),
        ('test',3,2750,2700,1,10,'v',1700),('test',4,5100,5160,1,10,'v',5000)])
    for source, in conn.execute('SELECT source FROM sources').fetchall():
        digest=hashlib.sha256()
        for row in conn.execute('SELECT ts,y FROM samples WHERE source=? ORDER BY seq',(source,)):
            digest.update(json.dumps(list(row),sort_keys=True).encode())
        conn.execute('UPDATE sources SET sha256=? WHERE source=?',(digest.hexdigest(),source))
    digest=hashlib.sha256()
    for row in conn.execute('SELECT * FROM forecasts ORDER BY target_ts,id'):
        digest.update(json.dumps(tuple(row),sort_keys=True).encode())
    conn.execute('UPDATE models SET sha256=?',(digest.hexdigest(),))
    conn.commit();conn.close();(root/'snapshot-complete').touch();analyze(root)
    if prepare:repair.prepare(root)


class TargetedRepairTests(unittest.TestCase):
    def test_target_transition_only_rebuilds_old_definition(self):
        from aqpy.forecast.repair_validation import audit
        with tempfile.TemporaryDirectory() as d:
            fixture(d,prepare=False);c=open_inventory(d)
            spec=json.loads(c.execute('SELECT spec FROM models').fetchone()[0])
            spec.update(target='aqi_pm',table='pms_aqi_v2')
            c.execute('UPDATE models SET spec=?',(json.dumps(spec),))
            c.execute('CREATE TABLE forecast_sources(model TEXT,id INTEGER,source_table TEXT,PRIMARY KEY(model,id))')
            digest=hashlib.sha256()
            for pid in (1,2,3,4):
                row=('test',pid,'pms_aqi' if pid==1 else 'pms_aqi_v2')
                c.execute('INSERT INTO forecast_sources VALUES (?,?,?)',row)
                digest.update(json.dumps(row,sort_keys=True).encode())
            c.execute('INSERT INTO meta VALUES (?,?)',('forecast_sources_sha256:test',digest.hexdigest()))
            c.commit();c.close();analyze(d);repair.prepare(d);repair.run(d,60,check_resources=False)
            c=open_inventory(d)
            self.assertEqual(c.execute("SELECT provenance FROM repaired WHERE key='original:1'").fetchone()[0],'targeted_reconstruction:corrected_target')
            self.assertEqual(c.execute("SELECT provenance FROM repaired WHERE key='original:2'").fetchone()[0],'corrected_original')
            self.assertIsNone(c.execute("SELECT 1 FROM repaired WHERE key='original:4'").fetchone())
            c.close();result=audit(d);self.assertEqual(result['status'],'PASS',result['failures'])

    def test_only_defects_and_gaps_get_outputs_and_originals_stay_intact(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d);repair.run(d,seconds=60,check_resources=False)
            conn=open_inventory(d)
            self.assertEqual(conn.execute("SELECT yhat FROM forecasts WHERE id=2").fetchone()[0],-.5)
            self.assertEqual(conn.execute("SELECT yhat FROM repaired WHERE key='original:2'").fetchone()[0],0)
            self.assertIsNone(conn.execute("SELECT 1 FROM repaired WHERE key='original:1'").fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM repaired WHERE key='original:3'").fetchone())
            self.assertEqual(conn.execute('SELECT count(*) FROM repair_tasks WHERE complete=0').fetchone()[0],0)
            conn.close()

    def test_resume_and_future_independence_all_families(self):
        for family in ['adaptive_ar','nn_mlp','rnn_lite_gru']:
            with self.subTest(family=family),tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
                fixture(a,family);fixture(b,family,True)
                repair.run(a,seconds=.001,check_resources=False)
                repair.run(a,seconds=60,check_resources=False)
                repair.run(b,seconds=60,check_resources=False)
                def prior(d):
                    c=open_inventory(d);rows=[tuple(r) for r in c.execute('SELECT key,issued,raw_yhat,yhat,baseline,train_cutoff FROM repaired WHERE issued<4500 ORDER BY key')];c.close();return rows
                self.assertEqual(prior(a),prior(b))
                before=prior(a);repair.run(a,seconds=60,check_resources=False);self.assertEqual(before,prior(a))

    def test_failed_fit_rolls_back_task_and_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d)
            with patch('aqpy.forecast.replay.fit',side_effect=RuntimeError('fit failed')):
                with self.assertRaises(RuntimeError):repair.run(d,check_resources=False)
            c=open_inventory(d)
            self.assertEqual(c.execute('SELECT count(*) FROM repair_fits').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT sum(complete) FROM repair_tasks').fetchone()[0],0)
            c.close()
