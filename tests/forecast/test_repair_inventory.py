import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from aqpy.forecast.repair_inventory import analyze


class InventoryTests(unittest.TestCase):
    def test_profiles_specific_defects_and_gaps_without_mutating_forecasts(self):
        with tempfile.TemporaryDirectory() as d:
            conn=sqlite3.connect(Path(d)/'inventory.sqlite')
            conn.executescript('''CREATE TABLE models(model TEXT,spec TEXT);
                CREATE TABLE samples(source TEXT,ts REAL,y REAL);
                CREATE TABLE forecasts(model TEXT,id INTEGER,generated REAL,target_ts REAL,horizon INTEGER,yhat REAL,trained_at REAL);''')
            spec={'database':'pms','table':'pi','target':'p1'}
            conn.execute('INSERT INTO models VALUES (?,?)',('m',json.dumps(spec)))
            conn.executemany('INSERT INTO samples VALUES (?,?,?)',[('pms.pi.p1',i*60,10+i%3) for i in range(60)])
            records=[('m',1,600.,660.,1,11.,500.),('m',2,600.,720.,2,-.1,500.),
                     ('m',3,2400.,2399.,1,11.,2200.),('m',4,2400.,2460.,2,None,2200.)]
            conn.executemany('INSERT INTO forecasts VALUES (?,?,?,?,?,?,?)',records);conn.commit();conn.close()
            report=analyze(d);m=report['models'][0]
            self.assertEqual(m['counts']['physical_domain'],1)
            self.assertEqual(m['counts']['late'],1)
            self.assertEqual(m['counts']['nonfinite'],1)
            self.assertEqual(m['gaps'],[{'start':600.,'end':2400.,'seconds':1800.}])
            conn=sqlite3.connect(Path(d)/'inventory.sqlite')
            self.assertEqual(conn.execute('SELECT * FROM forecasts ORDER BY id').fetchall(),records)
            conn.close()

