from typing import Protocol, TypedDict


class PMSData(TypedDict):
    pm_st: list[int]
    pm_en: list[int]
    hist: list[int]


class ClimateReading(Protocol):
    temperature: float
    humidity: float
    pressure: float


class ParticleSensor(Protocol):
    def averaged_read(self, avg_time: int = 10) -> PMSData:
        ...

    def sleep(self) -> None:
        ...

    def close(self) -> None:
        ...


class ClimateSensor(Protocol):
    def read(self) -> ClimateReading:
        ...

    def close(self) -> None:
        ...


class IngestRepository(Protocol):
    def insert_pms_sample(self, pms_data: PMSData) -> None:
        ...

    def insert_bme_sample(self, bme_data: ClimateReading) -> None:
        ...

    def close(self) -> None:
        ...
