import unittest
from unittest.mock import patch

from aqpy.ingest.config import load_config


class TestIngestConfig(unittest.TestCase):
    def test_load_config_from_environment(self):
        env = {
            "AQPY_SERIAL_PORT": "/dev/ttyUSB0",
            "AQPY_SERIAL_BAUD": "115200",
            "AQPY_PMS_STARTUP_DELAY": "12",
            "AQPY_PMS_AVG_TIME": "7",
            "AQPY_SLEEP_SECONDS": "22",
            "AQPY_BME_I2C_PORT": "3",
            "AQPY_BME_I2C_ADDR": "0x77",
            "AQPY_DB_NAME_PMS": "pmsdb",
            "AQPY_DB_NAME_BME": "bmedb",
            "AQPY_LOG_LEVEL": "debug",
        }
        with patch.dict("os.environ", env, clear=False):
            cfg = load_config()

        self.assertEqual(cfg.serial_port, "/dev/ttyUSB0")
        self.assertEqual(cfg.serial_baud, 115200)
        self.assertEqual(cfg.pms_startup_delay, 12)
        self.assertEqual(cfg.pms_avg_time, 7)
        self.assertEqual(cfg.sleep_seconds, 22)
        self.assertEqual(cfg.bme_i2c_port, 3)
        self.assertEqual(cfg.bme_i2c_addr, 0x77)
        self.assertEqual(cfg.db_name_pms, "pmsdb")
        self.assertEqual(cfg.db_name_bme, "bmedb")
        self.assertEqual(cfg.log_level, "DEBUG")


if __name__ == "__main__":
    unittest.main()
