"""Optional PostgreSQL integration test against a dedicated disposable database."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aqpy.common.db import connect_db
from aqpy.forecast.repair_publish import publish,timestamp
from aqpy.forecast.repair_export import finalize
from aqpy.forecast.repair_validation import audit
from aqpy.forecast.targeted_repair import run
from tests.forecast.test_targeted_repair import fixture


@unittest.skipUnless(os.getenv('AQPY_TEST_REPAIR_DATABASE'),'Dedicated PostgreSQL test database required')
class PublishIntegrationTests(unittest.TestCase):
    def test_publication_is_exact_idempotent_and_preserves_originals(self):
        database=os.environ['AQPY_TEST_REPAIR_DATABASE']
        if not database.startswith('aqpy_repair_test_'):raise ValueError('Refusing a non-test database')
        pg=connect_db(database)
        try:
            with pg.cursor() as cur:
                cur.execute('DROP VIEW IF EXISTS predictions_repaired; DROP SCHEMA IF EXISTS history_repair CASCADE; DROP TABLE IF EXISTS predictions CASCADE; DROP TABLE IF EXISTS model_registry CASCADE')
                schema=Path('sql/forecast_schema.sql').read_text()
                cur.execute('\n'.join(line for line in schema.splitlines() if not line.startswith('\\')))
                cur.execute(Path('sql/repair_history.sql').read_text())
                for pid,issue,target,h,y in [(1,1800,1860,1,10),(2,1800,1920,2,-.5),(3,2750,2700,1,10),(4,5100,5160,1,10)]:
                    cur.execute('''INSERT INTO predictions(id,generated_at,predicted_for,source_database,source_table,target,
                        model_name,model_version,horizon_step,yhat) VALUES (%s,%s,%s,'pms','pi','p1','test','v',%s,%s)''',
                        (pid,timestamp(issue),timestamp(target),h,y))
            pg.commit()
            with tempfile.TemporaryDirectory() as d,patch('aqpy.forecast.repair_publish.connect_db',lambda _:connect_db(database)):
                fixture(d);run(d,60,check_resources=False);finalize(d)
                self.assertEqual(audit(d)['status'],'PASS')
                with self.assertRaises(RuntimeError):publish(d,max_rows=1)
                result=publish(d);again=publish(d)
                self.assertEqual(result,again)
                self.assertEqual(result['databases'][0]['rows'],14)
                with pg.cursor() as cur:
                    cur.execute('SELECT yhat FROM predictions WHERE id=2');self.assertEqual(cur.fetchone()[0],-.5)
                    cur.execute('SELECT yhat FROM predictions_repaired WHERE original_id=2');self.assertEqual(cur.fetchone()[0],0.)
                    cur.execute('SELECT count(*) FROM predictions_repaired');self.assertEqual(cur.fetchone()[0],16)
                    # A corrupted staged import must never become visible.
                    cur.execute('UPDATE history_repair.runs SET published_at=NULL')
                    cur.execute('UPDATE history_repair.predictions SET yhat=yhat+1')
                pg.commit()
                with self.assertRaises(ValueError):publish(d)
                with pg.cursor() as cur:
                    cur.execute('SELECT count(*) FROM predictions_repaired WHERE repair_run IS NOT NULL');self.assertEqual(cur.fetchone()[0],0)
                csv=Path(d)/'repaired.csv';csv.write_text(csv.read_text()+'tampered\n')
                with self.assertRaises(ValueError):publish(d)
        finally:pg.close()
