import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from aqpy.forecast.repair_report import build,metrics


class RepairReportTests(unittest.TestCase):
    def test_metrics_keep_raw_and_served_quality_separate(self):
        rows=[{'actual':10.,'yhat':10.,'raw_yhat':20.,'baseline':12.},
              {'actual':None,'yhat':3.,'raw_yhat':30.,'baseline':4.}]
        self.assertEqual(metrics(rows),{'scored':1,'served_mae':0.,'raw_mae':10.,'persistence_mae':2.})

    def test_build_requires_and_reports_verified_published_run(self):
        with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as output:
            root=Path(d);c=sqlite3.connect(root/'inventory.sqlite')
            c.executescript('''CREATE TABLE meta(key TEXT,value TEXT);
                CREATE TABLE repair_models(model TEXT,spec TEXT);
                CREATE TABLE forecasts(model TEXT);
                CREATE TABLE repaired(model TEXT,original_id INTEGER,provenance TEXT,actual REAL,yhat REAL,raw_yhat REAL,baseline REAL);
                CREATE TABLE unresolved(model TEXT);''')
            spec={'database':'pms','table':'pi','target':'p1','model_type':'adaptive_ar'}
            c.execute('INSERT INTO meta VALUES (?,?)',('config',json.dumps({'end':'2026-01-01T00:00:00+00:00'})))
            c.execute('INSERT INTO repair_models VALUES (?,?)',('model',json.dumps(spec)))
            c.execute('INSERT INTO forecasts VALUES (?)',('model',))
            c.execute('INSERT INTO repaired VALUES (?,?,?,?,?,?,?)',('model',1,'corrected_original',10,11,12,9))
            c.commit();c.close()
            (root/'repair-validation.json').write_text(json.dumps({'status':'PASS','finalized':True,'auditor_sha256':'abc','models':[{'model':'model','status':'PASS'}]}))
            (root/'publication.json').write_text(json.dumps({'databases':[{'status':'PASS'}]}))
            result=build([root],output)
            self.assertEqual(result['models'][0]['disposition'],'verified repair')
            self.assertTrue((Path(output)/'MODEL_DISPOSITIONS.md').exists())
            (root/'publication.json').write_text(json.dumps({'databases':[{'status':'FAIL'}]}))
            with self.assertRaises(ValueError):build([root],output)
