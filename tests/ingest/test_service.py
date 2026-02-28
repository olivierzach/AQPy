import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aqpy.ingest.service import AQIngestService, build_default_service


class FakeRepository:
    def __init__(self):
        self.close_called = 0

    def close(self):
        self.close_called += 1


class FakeTask:
    def __init__(self, name, fail_first=False):
        self.name = name
        self.fail_first = fail_first
        self.calls = 0
        self.successes = 0
        self.close_called = 0

    def run_once(self):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("simulated task failure")
        self.successes += 1
        return True

    def close(self):
        self.close_called += 1


class TestAQIngestService(unittest.TestCase):
    def test_run_cycle_runs_all_tasks(self):
        t1 = FakeTask("pms")
        t2 = FakeTask("bme")
        repo = FakeRepository()
        svc = AQIngestService(
            tasks=[t1, t2],
            repository=repo,
            sleep_seconds=30,
        )

        result = svc.run_cycle()
        self.assertEqual(result, {"pms": True, "bme": True})
        self.assertEqual(t1.calls, 1)
        self.assertEqual(t2.calls, 1)

    @patch("aqpy.ingest.service.time.sleep", return_value=None)
    def test_run_forever_continues_when_one_task_fails(self, _sleep):
        t1 = FakeTask("pms", fail_first=True)
        t2 = FakeTask("bme", fail_first=False)
        repo = FakeRepository()
        svc = AQIngestService(
            tasks=[t1, t2],
            repository=repo,
            sleep_seconds=1,
        )

        svc.run_forever(max_cycles=2)

        self.assertEqual(t1.calls, 2)
        self.assertEqual(t1.successes, 1)
        self.assertEqual(t2.calls, 2)
        self.assertEqual(t2.successes, 2)
        _sleep.assert_called_once_with(1)

    def test_shutdown_closes_all_dependencies(self):
        t1 = FakeTask("pms")
        t2 = FakeTask("bme")
        repo = FakeRepository()
        svc = AQIngestService(
            tasks=[t1, t2],
            repository=repo,
            sleep_seconds=1,
        )

        svc.shutdown()

        self.assertEqual(t1.close_called, 1)
        self.assertEqual(t2.close_called, 1)
        self.assertEqual(repo.close_called, 1)

    @patch("aqpy.ingest.service.load_config")
    @patch("aqpy.ingest.service._open_serial")
    @patch("aqpy.ingest.service.PMS5003")
    @patch("aqpy.ingest.service._build_repository")
    @patch("aqpy.ingest.service.BME280Sensor")
    def test_build_default_service_skips_bme_on_init_failure(
        self,
        bme_cls,
        repo_cls,
        pms_cls,
        serial_cls,
        load_config_fn,
    ):
        load_config_fn.return_value = SimpleNamespace(
            serial_port="/dev/serial0",
            serial_baud=9600,
            pms_startup_delay=1,
            pms_avg_time=10,
            sleep_seconds=30,
            bme_i2c_port=1,
            bme_i2c_addr=0x76,
            db_name_pms="pms",
            db_name_bme="bme",
        )
        serial_cls.return_value = object()
        pms = MagicMock()
        pms_cls.return_value = pms
        repo = MagicMock()
        repo_cls.return_value = repo
        bme_cls.side_effect = RuntimeError("i2c device not found")

        with self.assertLogs("aqpy.ingest.service", level="ERROR") as logs:
            svc = build_default_service()

        self.assertEqual(len(svc.tasks), 1)
        self.assertEqual(svc.tasks[0].name, "pms")
        pms.sleep.assert_called_once()
        self.assertTrue(
            any("BME280 init failed; continuing with PMS-only ingest" in msg for msg in logs.output)
        )

    @patch("aqpy.ingest.service.load_config")
    @patch("aqpy.ingest.service._open_serial")
    @patch("aqpy.ingest.service.PMS5003")
    @patch("aqpy.ingest.service._build_repository")
    @patch("aqpy.ingest.service.BME280Sensor")
    def test_build_default_service_includes_bme_when_available(
        self,
        bme_cls,
        repo_cls,
        pms_cls,
        serial_cls,
        load_config_fn,
    ):
        load_config_fn.return_value = SimpleNamespace(
            serial_port="/dev/serial0",
            serial_baud=9600,
            pms_startup_delay=1,
            pms_avg_time=10,
            sleep_seconds=30,
            bme_i2c_port=1,
            bme_i2c_addr=0x76,
            db_name_pms="pms",
            db_name_bme="bme",
        )
        serial_cls.return_value = object()
        pms = MagicMock()
        pms_cls.return_value = pms
        repo = MagicMock()
        repo_cls.return_value = repo
        bme_cls.return_value = MagicMock()

        svc = build_default_service()

        self.assertEqual(len(svc.tasks), 2)
        self.assertEqual([t.name for t in svc.tasks], ["pms", "bme"])

    @patch("aqpy.ingest.service.load_config")
    @patch("aqpy.ingest.service._open_serial")
    @patch("aqpy.ingest.service.PMS5003")
    @patch("aqpy.ingest.service._build_repository")
    @patch("aqpy.ingest.service.BME280Sensor")
    def test_build_default_service_skips_pms_on_init_failure(
        self,
        bme_cls,
        repo_cls,
        pms_cls,
        serial_cls,
        load_config_fn,
    ):
        load_config_fn.return_value = SimpleNamespace(
            serial_port="/dev/serial0",
            serial_baud=9600,
            pms_startup_delay=1,
            pms_avg_time=10,
            sleep_seconds=30,
            bme_i2c_port=1,
            bme_i2c_addr=0x76,
            db_name_pms="pms",
            db_name_bme="bme",
        )
        serial_conn = MagicMock()
        serial_cls.return_value = serial_conn
        pms_cls.side_effect = RuntimeError("serial init failed")
        repo = MagicMock()
        repo_cls.return_value = repo
        bme_cls.return_value = MagicMock()

        with self.assertLogs("aqpy.ingest.service", level="ERROR") as logs:
            svc = build_default_service()

        self.assertEqual(len(svc.tasks), 1)
        self.assertEqual(svc.tasks[0].name, "bme")
        serial_conn.close.assert_called_once()
        self.assertTrue(
            any("PMS5003 init failed; continuing with BME-only ingest" in msg for msg in logs.output)
        )

    @patch("aqpy.ingest.service.load_config")
    @patch("aqpy.ingest.service._open_serial")
    @patch("aqpy.ingest.service.PMS5003")
    @patch("aqpy.ingest.service._build_repository")
    @patch("aqpy.ingest.service.BME280Sensor")
    def test_build_default_service_raises_when_no_sensors_available(
        self,
        bme_cls,
        repo_cls,
        pms_cls,
        serial_cls,
        load_config_fn,
    ):
        load_config_fn.return_value = SimpleNamespace(
            serial_port="/dev/serial0",
            serial_baud=9600,
            pms_startup_delay=1,
            pms_avg_time=10,
            sleep_seconds=30,
            bme_i2c_port=1,
            bme_i2c_addr=0x76,
            db_name_pms="pms",
            db_name_bme="bme",
        )
        serial_conn = MagicMock()
        serial_cls.return_value = serial_conn
        pms_cls.side_effect = RuntimeError("serial init failed")
        repo = MagicMock()
        repo_cls.return_value = repo
        bme_cls.side_effect = RuntimeError("i2c device not found")

        with self.assertRaisesRegex(RuntimeError, "No sensors initialized"):
            build_default_service()

        repo.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
