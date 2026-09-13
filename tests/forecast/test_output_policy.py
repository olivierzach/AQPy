import unittest
from unittest.mock import MagicMock
from aqpy.forecast.output_policy import correct_output,in_domain


class OutputPolicyTests(unittest.TestCase):
    def test_watchdog_rejects_latest_physical_violation(self):
        import datetime as dt
        from aqpy.forecast.health import check_recent_predictions
        now=dt.datetime.now(dt.timezone.utc)
        with self.assertRaisesRegex(ValueError,'physical'):
            check_recent_predictions([(160.,now)],now,300,'humidity')
        check_recent_predictions([(160.,now-dt.timedelta(minutes=1)),(52.,now)],now,300,'humidity')

    def test_database_writer_preserves_raw_value_and_reason(self):
        from aqpy.forecast.repository import insert_predictions
        conn=MagicMock();cur=conn.cursor.return_value.__enter__.return_value
        row=(None,'pms','pi','pm25_st','model','version',1,0.,-.6,'nonnegative_projection_v1')
        insert_predictions(conn,[row])
        sql,rows=cur.executemany.call_args.args
        self.assertIn('raw_yhat',sql);self.assertEqual(rows,[row])

    def test_negative_particle_projection_preserves_valid_values(self):
        for target in ['pm25_st','pm100_en','p6']:
            self.assertEqual(correct_output(target,-.6,2),(0.,'nonnegative_projection_v1'))
            self.assertEqual(correct_output(target,3,2),(3.,'unchanged'))
            # Projection cannot increase absolute error for a nonnegative actual.
            for actual in [0,1,100]:self.assertLessEqual(abs(0-actual),abs(-.6-actual))

    def test_impossible_humidity_uses_observed_baseline_not_boundary(self):
        self.assertEqual(correct_output('humidity',160.8,52),(52.,'physical_persistence_v1'))
        self.assertEqual(correct_output('humidity',-2,52),(52.,'physical_persistence_v1'))
        self.assertEqual(correct_output('humidity',60,52),(60.,'unchanged'))

    def test_invalid_baseline_and_nonfinite_forecasts_fail(self):
        for value in [float('nan'),float('inf'),-float('inf')]:
            with self.assertRaises(ValueError):correct_output('pm25_st',value,0)
        with self.assertRaises(ValueError):correct_output('humidity',160,101)

    def test_zero_bounds_and_temperature_are_not_confused(self):
        self.assertTrue(in_domain('humidity',0));self.assertTrue(in_domain('humidity',100))
        self.assertFalse(in_domain('humidity',100.1));self.assertFalse(in_domain('p1',-.0001))
        self.assertEqual(correct_output('temperature',-10,-9),(-10.,'unchanged'))
