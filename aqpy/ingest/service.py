import logging
import time
from dataclasses import dataclass

from aqpy.ingest.config import load_config
from aqpy.ingest.interfaces import ClimateSensor, IngestRepository, ParticleSensor
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
class AQIngestService:
    particle_sensor: ParticleSensor
    climate_sensor: ClimateSensor
    repository: IngestRepository
    pms_avg_time: int
    sleep_seconds: int

    def run_cycle(self):
        pms_data = self.particle_sensor.averaged_read(self.pms_avg_time)
        self.repository.insert_pms_sample(pms_data)

        bme_data = self.climate_sensor.read()
        self.repository.insert_bme_sample(bme_data)

    def run_forever(self, max_cycles=None):
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            try:
                self.run_cycle()
                logger.info("Recorded sensor sample")
            except Exception:
                logger.exception(
                    "Sample cycle failed; retrying in %ss",
                    self.sleep_seconds,
                )
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
        particle_sensor=pms,
        climate_sensor=bme_sensor,
        repository=repository,
        pms_avg_time=config.pms_avg_time,
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
