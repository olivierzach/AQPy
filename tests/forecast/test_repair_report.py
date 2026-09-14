import unittest
from aqpy.forecast.repair_report import metrics


class RepairReportTests(unittest.TestCase):
    def test_metrics_keep_raw_and_served_quality_separate(self):
        rows=[{'actual':10.,'yhat':10.,'raw_yhat':20.,'baseline':12.},
              {'actual':None,'yhat':3.,'raw_yhat':30.,'baseline':4.}]
        self.assertEqual(metrics(rows),{'scored':1,'served_mae':0.,'raw_mae':10.,'persistence_mae':2.})
