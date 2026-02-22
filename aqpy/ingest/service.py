import logging
import time
from dataclasses import dataclass
from typing import Sequence

from aqpy.ingest.config import load_config
from aqpy.ingest.interfaces import (
    ClimateSensor,
    IngestRepository,
    IngestTask,
    ParticleSensor,
)
from aqpy.ingest.pms5003 import PMS5003


logger = logging.getLogger(__name__)


class BME280Sensor:
    def __init__(self, i2c_port, i2c_addr):
        import bme280
        import smbus2

        self.i2c_addr = i2c_addr
        self.bme280 = bme280
        self.bus = smbus2.SMBus(i2c_port)
        self.calibration = self.bme280.load_calibration_params(self.bus, i2c_addr)

    def read(self):
        return self.bme280.sample(self.bus, self.i2c_addr, self.calibration)

    def close(self):
        self.bus.close()


@dataclass
class PMSIngestTask:
    name: str
    particle_sensor: ParticleSensor
    repository: IngestRepository
    pms_avg_time: int

    def run_once(self):
        data = self.particle_sensor.averaged_read(self.pms_avg_time)
        self.repository.insert_pms_sample(data)
        return True

    def close(self):
        try:
            self.particle_sensor.sleep()
        except Exception:
            logger.exception("Failed to put PMS5003 to sleep on shutdown")
        try:
            self.particle_sensor.close()
        except Exception:
            pass


@dataclass
class BMEIngestTask:
    name: str
    climate_sensor: ClimateSensor
    repository: IngestRepository

    def run_once(self):
        data = self.climate_sensor.read()
        self.repository.insert_bme_sample(data)
        return True

    def close(self):
        try:
            self.climate_sensor.close()
        except Exception:
            pass


@dataclass
class AQIngestService:
    tasks: Sequence[IngestTask]
    repository: IngestRepository
    sleep_seconds: int

    def run_cycle(self):
        result = {}
        for task in self.tasks:
            try:
                result[task.name] = task.run_once()
            except Exception:
                logger.exception("%s sample failed", task.name.upper())
                result[task.name] = False
        return result

    def run_forever(self, max_cycles=None):
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycle_result = self.run_cycle()
            ok_count = sum(1 for v in cycle_result.values() if v)
            if ok_count > 0:
                logger.info("Recorded sensor sample %s", cycle_result)
            else:
                logger.error("All sensor samples failed; retrying in %ss", self.sleep_seconds)
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                time.sleep(self.sleep_seconds)

    def shutdown(self):
        for task in self.tasks:
            try:
                task.close()
            except Exception:
                pass
        try:
            self.repository.close()
        except Exception:
            pass


@dataclass
class LegacyAQIngestService:
    particle_sensor: ParticleSensor
    climate_sensor: ClimateSensor
    repository: IngestRepository
    pms_avg_time: int
    sleep_seconds: int

    def run_cycle(self):
        result = {"pms": False, "bme": False}

        try:
            pms_data = self.particle_sensor.averaged_read(self.pms_avg_time)
            self.repository.insert_pms_sample(pms_data)
            result["pms"] = True
        except Exception:
            logger.exception("PMS sample failed")

        try:
            bme_data = self.climate_sensor.read()
            self.repository.insert_bme_sample(bme_data)
            result["bme"] = True
        except Exception:
            logger.exception("BME sample failed")

        return result

    def run_forever(self, max_cycles=None):
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycle_result = self.run_cycle()
            if cycle_result["pms"] or cycle_result["bme"]:
                logger.info(
                    "Recorded sensor sample (pms=%s, bme=%s)",
                    cycle_result["pms"],
                    cycle_result["bme"],
                )
            else:
                logger.error("Both sensor samples failed; retrying in %ss", self.sleep_seconds)
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                time.sleep(self.sleep_seconds)

    def shutdown(self):
        try:
            self.particle_sensor.sleep()
        except Exception:
            logger.exception("Failed to put PMS5003 to sleep on shutdown")

        try:
            self.particle_sensor.close()
        except Exception:
            pass

        try:
            self.climate_sensor.close()
        except Exception:
            pass

        try:
            self.repository.close()
        except Exception:
            pass


def build_default_service():
    import serial
    from aqpy.ingest.repository import PostgresIngestRepository

    config = load_config()
    serial_conn = serial.Serial(
        port=config.serial_port,
        baudrate=config.serial_baud,
        timeout=1,
    )
    pms = PMS5003(serial_conn, startup_delay=config.pms_startup_delay)
    pms.sleep()

    bme_sensor = BME280Sensor(config.bme_i2c_port, config.bme_i2c_addr)
    repository = PostgresIngestRepository(config.db_name_pms, config.db_name_bme)
    return AQIngestService(
        tasks=[
            PMSIngestTask(
                name="pms",
                particle_sensor=pms,
                repository=repository,
                pms_avg_time=config.pms_avg_time,
            ),
            BMEIngestTask(
                name="bme",
                climate_sensor=bme_sensor,
                repository=repository,
            ),
        ],
        repository=repository,
        sleep_seconds=config.sleep_seconds,
    )


def run_ingest_loop():
    service = None

    try:
        logger.info("Starting AQPy sensor reader")
        service = build_default_service()
        service.run_forever()
    finally:
        if service is not None:
            service.shutdown()
