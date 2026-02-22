import os
from dataclasses import dataclass

from aqpy.common.env import env_int


def env_hex_int(name, default):
    raw = os.getenv(name, hex(default))
    try:
        return int(raw, 16)
    except ValueError:
        return default


@dataclass(frozen=True)
class IngestConfig:
    serial_port: str
    serial_baud: int
    pms_startup_delay: int
    pms_avg_time: int
    sleep_seconds: int
    bme_i2c_port: int
    bme_i2c_addr: int
    db_name_pms: str
    db_name_bme: str
    log_level: str


def load_config():
    return IngestConfig(
        serial_port=os.getenv("AQPY_SERIAL_PORT", "/dev/serial0"),
        serial_baud=env_int("AQPY_SERIAL_BAUD", 9600),
        pms_startup_delay=env_int("AQPY_PMS_STARTUP_DELAY", 20),
        pms_avg_time=env_int("AQPY_PMS_AVG_TIME", 10),
        sleep_seconds=env_int("AQPY_SLEEP_SECONDS", 30),
        bme_i2c_port=env_int("AQPY_BME_I2C_PORT", 1),
        bme_i2c_addr=env_hex_int("AQPY_BME_I2C_ADDR", 0x76),
        db_name_pms=os.getenv("AQPY_DB_NAME_PMS", "pms"),
        db_name_bme=os.getenv("AQPY_DB_NAME_BME", "bme"),
        log_level=os.getenv("AQPY_LOG_LEVEL", "INFO").upper(),
    )
