"""Instantaneous, capped particle index proxy; not daily AQI or NowCast."""
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
import math

DEFINITION='instant_pm_index_epa2024_v2'
PM25=[(0,9,0,50),(9.1,35.4,51,100),(35.5,55.4,101,150),
      (55.5,125.4,151,200),(125.5,225.4,201,300),(225.5,325.4,301,500)]
PM10=[(0,54,0,50),(55,154,51,100),(155,254,101,150),
      (255,354,151,200),(355,424,201,300),(425,604,301,500)]


def component(value,bands,precision):
    if value is None or not math.isfinite(float(value)) or value<0:return None
    value=Decimal(str(value)).quantize(Decimal(precision),rounding=ROUND_FLOOR)
    for low,high,ilo,ihi in bands:
        low,high=Decimal(str(low)),Decimal(str(high))
        if low<=value<=high:
            return int((Decimal(ilo)+(value-low)*Decimal(ihi-ilo)/(high-low)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    return 500


def particle_index(pm25,pm10):
    valid=[x for x in (component(pm25,PM25,'0.1'),component(pm10,PM10,'1')) if x is not None]
    return max(valid) if valid else None
