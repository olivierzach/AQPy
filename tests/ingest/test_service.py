import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aqpy.ingest.service import AQIngestService


class FakeParticleSensor:
    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.calls = 0
        self.sleep_called = 0
        self.close_called = 0

    def averaged_read(self, avg_time=10):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("simulated sensor read failure")
        return {
            "pm_st": [1, 2, 3],
            "pm_en": [4, 5, 6],
            "hist": [7, 8, 9, 10, 11, 12],
        }

    def sleep(self):
        self.sleep_called += 1

    def close(self):
        self.close_called += 1


class FakeClimateSensor:
    def __init__(self):
        self.close_called = 0

    def read(self):
        return SimpleNamespace(temperature=70.0, humidity=40.0, pressure=1010.0)

    def close(self):
        self.close_called += 1


class FakeRepository:
    def __init__(self):
        self.pms_inserts = []
        self.bme_inserts = []
        self.close_called = 0

    def insert_pms_sample(self, pms_data):
        self.pms_inserts.append(pms_data)

    def insert_bme_sample(self, bme_data):
        self.bme_inserts.append(bme_data)

    def close(self):
        self.close_called += 1


class TestAQIngestService(unittest.TestCase):
    def test_run_cycle_writes_both_sensor_samples(self):
        particle = FakeParticleSensor()
        climate = FakeClimateSensor()
        repo = FakeRepository()
        svc = AQIngestService(
            particle_sensor=particle,
            climate_sensor=climate,
            repository=repo,
            pms_avg_time=10,
            sleep_seconds=30,
        )

        svc.run_cycle()

        self.assertEqual(len(repo.pms_inserts), 1)
        self.assertEqual(len(repo.bme_inserts), 1)
        self.assertEqual(particle.calls, 1)

    @patch("aqpy.ingest.service.time.sleep", return_value=None)
    def test_run_forever_retries_after_cycle_failure(self, _sleep):
        particle = FakeParticleSensor(fail_first=True)
        climate = FakeClimateSensor()
        repo = FakeRepository()
        svc = AQIngestService(
            particle_sensor=particle,
            climate_sensor=climate,
            repository=repo,
            pms_avg_time=10,
            sleep_seconds=1,
        )

        svc.run_forever(max_cycles=2)

        self.assertEqual(particle.calls, 2)
        self.assertEqual(len(repo.pms_inserts), 1)
        self.assertEqual(len(repo.bme_inserts), 1)
        _sleep.assert_called_once_with(1)

    def test_shutdown_closes_all_dependencies(self):
        particle = FakeParticleSensor()
        climate = FakeClimateSensor()
        repo = FakeRepository()
        svc = AQIngestService(
            particle_sensor=particle,
            climate_sensor=climate,
            repository=repo,
            pms_avg_time=10,
            sleep_seconds=1,
        )

        svc.shutdown()

        self.assertEqual(particle.sleep_called, 1)
        self.assertEqual(particle.close_called, 1)
        self.assertEqual(climate.close_called, 1)
        self.assertEqual(repo.close_called, 1)


if __name__ == "__main__":
    unittest.main()
