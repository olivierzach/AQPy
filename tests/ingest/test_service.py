import unittest
from unittest.mock import patch

from aqpy.ingest.service import AQIngestService


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


if __name__ == "__main__":
    unittest.main()
