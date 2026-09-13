import unittest
from aqpy.common.pm_index import particle_index,component,PM25,PM10


class ParticleIndexTests(unittest.TestCase):
    def test_epa_breakpoints_and_truncation(self):
        for bands,precision in [(PM25,'0.1'),(PM10,'1')]:
            for low,high,ilo,ihi in bands:
                self.assertEqual(component(low,bands,precision),ilo)
                self.assertEqual(component(high,bands,precision),ihi)
        self.assertEqual(particle_index(9.09,0),50)
        self.assertEqual(particle_index(9.1,0),51)

    def test_correct_pm10_can_dominate_and_missing_is_not_zero(self):
        self.assertEqual(particle_index(0,154),100)
        self.assertEqual(particle_index(None,54),50)
        self.assertIsNone(particle_index(None,None))
        self.assertIsNone(particle_index(float('nan'),-1))
        self.assertEqual(particle_index(10000,0),500)
