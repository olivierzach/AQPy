import os

import psycopg2 as psql

from aqpy.common.env import env_int


def connect_db(database):
    return psql.connect(
        dbname=database,
        user=os.getenv("AQPY_DB_USER", "pi"),
        password=os.getenv("AQPY_DB_PASSWORD", "rpi4"),
        host=os.getenv("AQPY_DB_HOST", "localhost"),
        port=env_int("AQPY_DB_PORT", 5432),
    )
