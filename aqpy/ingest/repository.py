from aqpy.common.db import connect_db
from aqpy.ingest.interfaces import ClimateReading, PMSData


INSERT_PMS = """
INSERT INTO pi (
    t, pm10_st, pm25_st, pm100_st,
    pm10_en, pm25_en, pm100_en,
    p1, p2, p3, p4, p5, p6
) VALUES (
    now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""

INSERT_BME = """
INSERT INTO pi (t, temperature, humidity, pressure)
VALUES (now(), %s, %s, %s)
"""


class PostgresIngestRepository:
    def __init__(self, pms_database, bme_database):
        self.conn_pms = connect_db(pms_database)
        self.conn_pms.autocommit = True
        self.cur_pms = self.conn_pms.cursor()

        self.conn_bme = connect_db(bme_database)
        self.conn_bme.autocommit = True
        self.cur_bme = self.conn_bme.cursor()

    def insert_pms_sample(self, pms_data: PMSData):
        self.cur_pms.execute(
            INSERT_PMS,
            (
                pms_data["pm_st"][0],
                pms_data["pm_st"][1],
                pms_data["pm_st"][2],
                pms_data["pm_en"][0],
                pms_data["pm_en"][1],
                pms_data["pm_en"][2],
                pms_data["hist"][0],
                pms_data["hist"][1],
                pms_data["hist"][2],
                pms_data["hist"][3],
                pms_data["hist"][4],
                pms_data["hist"][5],
            ),
        )

    def insert_bme_sample(self, bme_data: ClimateReading):
        self.cur_bme.execute(
            INSERT_BME,
            (
                bme_data.temperature * 9 / 5 + 32,
                bme_data.humidity,
                bme_data.pressure,
            ),
        )

    def close(self):
        for cur in (self.cur_pms, self.cur_bme):
            try:
                cur.close()
            except Exception:
                pass

        for conn in (self.conn_pms, self.conn_bme):
            try:
                conn.close()
            except Exception:
                pass
