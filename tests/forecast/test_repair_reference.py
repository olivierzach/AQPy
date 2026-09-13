import unittest
import numpy as np
from aqpy.forecast.replay import fit,predict
from aqpy.forecast.repair_reference import fit_reference,predict_reference


class ReferenceTests(unittest.TestCase):
    def test_independent_fits_and_rollouts_agree_all_families(self):
        for family in ['adaptive_ar','nn_mlp','rnn_lite_gru']:
            for values in [np.sin(np.arange(240)/8)+10,np.zeros(240),1000+np.arange(240)*.001]:
                with self.subTest(family=family):
                    spec={'model_type':family,'lags':[1,2,3,6,12],'seq_len':8,'hidden_dim':4,'epochs':3}
                    production=fit(spec,values,42);reference=fit_reference(spec,values,42)
                    np.testing.assert_allclose(predict(production,values,12),predict_reference(reference,values,12),rtol=1e-8,atol=1e-8)
                    np.testing.assert_allclose(predict(production,values,12),predict_reference(production,values,12),rtol=1e-8,atol=1e-8)
