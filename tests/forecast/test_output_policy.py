import math
import unittest
from aqpy.forecast.output_policy import correct_output,in_domain


class OutputPolicyTests(unittest.TestCase):
    def test_aqi_zero_projection_is_limited_to_half_an_index_point(self):
        for raw in (-.5, -.0444344635, math.nextafter(0., -math.inf)):
            with self.subTest(raw=raw):
                self.assertEqual(correct_output('aqi_pm', raw, 25., [25.] * 50),
                                 (0., 'aqi_zero_projection_v1'))
        for raw in (math.nextafter(-.5, -math.inf), -1., math.nextafter(500., math.inf)):
            with self.subTest(raw=raw):
                self.assertEqual(correct_output('aqi_pm', raw, 25.),
                                 (25., 'physical_persistence_v1'))
        for raw in (0., .25, 500.):
            with self.subTest(raw=raw):
                self.assertEqual(correct_output('aqi_pm', raw, 25.), (raw, 'unchanged'))
        self.assertFalse(in_domain('aqi_pm', -.01))
        self.assertFalse(in_domain('aqi_pm', 500.01))

    def test_aqi_tolerance_does_not_relax_other_target_bounds(self):
        for target in ('humidity', 'pressure'):
            with self.subTest(target=target):
                self.assertEqual(correct_output(target, -.04, 25.),
                                 (25., 'physical_persistence_v1'))

    def test_aqi_projection_still_rejects_invalid_inputs(self):
        for raw in (math.nan, math.inf, -math.inf):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                correct_output('aqi_pm', raw, 0.)
        for baseline in (-1., 501., math.nan):
            with self.subTest(baseline=baseline), self.assertRaises(ValueError):
                correct_output('aqi_pm', -.04, baseline)

    def test_stability_guard_rejects_explosive_rollout_using_only_past(self):
        history=[0.,1.,2.,3.,1.]*10
        self.assertEqual(correct_output('pm25_st',20000,1,history),(1.,'causal_stability_persistence_v1'))
        self.assertEqual(correct_output('pm25_st',5,1,history),(5.,'unchanged'))
        self.assertEqual(correct_output('p1',100,100,[100.]*50),(100.,'unchanged'))
        self.assertEqual(correct_output('pm10_st',2,0,[0.]*50),(2.,'unchanged'))

    def test_watchdog_rejects_latest_physical_violation(self):
        import datetime as dt
        from aqpy.forecast.health import check_recent_predictions
        now=dt.datetime.now(dt.timezone.utc)
        with self.assertRaisesRegex(ValueError,'physical'):
            check_recent_predictions([(160.,now)],now,300,'humidity')
        check_recent_predictions([(160.,now-dt.timedelta(minutes=1)),(52.,now)],now,300,'humidity')

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
