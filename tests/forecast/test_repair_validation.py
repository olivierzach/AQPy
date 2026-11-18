import tempfile
import unittest

from tests.forecast.test_targeted_repair import fixture
from aqpy.forecast.targeted_repair import run
from aqpy.forecast.repair_inventory import open_inventory
from aqpy.forecast.repair_validation import audit, reference_policy
from aqpy.forecast.repair_export import finalize


class RepairValidationTests(unittest.TestCase):
    def test_reference_aqi_policy_keeps_large_domain_errors_distinct(self):
        self.assertEqual(reference_policy('aqi_pm', -.5, [1.] * 50),
                         (0., 'aqi_zero_projection_v1'))
        for raw in (-.500001, 500.01):
            with self.subTest(raw=raw):
                self.assertEqual(reference_policy('aqi_pm', raw, [25.] * 50),
                                 (25., 'physical_persistence_v1'))
        self.assertEqual(reference_policy('aqi_pm', -.04, [25.] * 50),
                         (25., 'causal_stability_persistence_v1'))

    def test_independent_audit_all_families(self):
        for family in ('adaptive_ar','nn_mlp','rnn_lite_gru'):
            with self.subTest(family=family),tempfile.TemporaryDirectory() as d:
                fixture(d,family);run(d,60,check_resources=False)
                finalize(d)
                result=audit(d)
                self.assertEqual(result['status'],'PASS',result['failures'])
                self.assertTrue(result['finalized'])

    def test_detects_tampering_and_missing_outputs(self):
        mutations=[
            'UPDATE samples SET y=y+1 WHERE seq=50',
            'UPDATE forecasts SET yhat=99 WHERE id=1',
            "UPDATE repaired SET raw_yhat=raw_yhat+1 WHERE fit_id IS NOT NULL",
            'UPDATE repaired SET yhat=yhat+1',
            'UPDATE repaired SET baseline=baseline+1',
            'UPDATE repaired SET actual=actual+1',
            'UPDATE original_scores SET sum_abs=sum_abs+1',
            "DELETE FROM repaired WHERE key='original:2'",
            "UPDATE repair_fits SET artifact='{}'",
            'UPDATE repair_tasks SET complete=0',
            "INSERT INTO unresolved VALUES ('test','original:999','no source before issuance')",
        ]
        for sql in mutations:
            with self.subTest(sql=sql),tempfile.TemporaryDirectory() as d:
                fixture(d);run(d,60,check_resources=False)
                c=open_inventory(d);c.execute(sql);c.commit();c.close()
                self.assertEqual(audit(d)['status'],'FAIL')
