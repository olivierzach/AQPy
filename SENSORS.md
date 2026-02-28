# Sensors Reference

This page summarizes the two hardware sensors used in AQPy, with wiring context and primary reference links.

## 1) PMS5003 (Plantower)

Digital laser particle sensor used for PM measurements over UART.

### Key Specs
- Interface: UART (3.3V logic on data pins)
- Supply voltage: 5.0V typical (4.5V to 5.5V)
- Active current: `<=100 mA`
- Standby current: `<=10 mA`
- Minimum distinguishable particle diameter: `0.3 µm`
- PM2.5 standard effective range: `0 to 500 µg/m³`
- PM2.5 standard maximum range: `>=1000 µg/m³`
- Resolution: `1 µg/m³`
- Single response time: `<1 s`
- Total response time: `<10 s`
- Operating temperature: `-10 to +60 °C`
- Operating humidity: `0 to 99% RH`

### AQPy Wiring Assumption
- Connected via `/dev/serial0` on Raspberry Pi
- Pins used in this repo:
  - Pi pin 8 (TXD) <-> PMS RX
  - Pi pin 10 (RXD) <-> PMS TX
  - Pi pin 2 (5V) / pin 6 (GND)

### Primary References
- Plantower product page (PMS5003):
  - https://www.plantower.com/en/products_33/74.html
- PMS5003 series manual (V2.3, mirrored by AQMD):
  - https://www.aqmd.gov/docs/default-source/aq-spec/resources-page/plantower-pms5003-manual_v2-3.pdf

### AQPy Derived AQI (from PMS)
AQPy derives a PM-based AQI metric using PMS standard channels:
- Inputs: `pm25_st`, `pm10_st`
- Method: EPA breakpoint linear interpolation per pollutant
- Final index: `max(AQI_pm25, AQI_pm10)`

Data path:
- Raw PMS rows remain in `pms.pi`
- Derived AQI is exposed via SQL view `derived.pms_aqi` and convenience view `pms_aqi`

Operational implication:
- Historical AQI is immediately available without backfill jobs
- No ETL timer needed unless you later materialize AQI for performance reasons

## 2) BME280 (Bosch Sensortec)

Combined environmental sensor for temperature, humidity, and pressure over I2C/SPI.

### Key Specs
- Interfaces: I2C and SPI
- Pressure range: `300 to 1100 hPa`
- Temperature operating range: `-40 to +85 °C`
- Supply voltage (`VDD`): `1.71 to 3.6 V`
- Interface supply (`VDDIO`): `1.2 to 3.6 V`
- Typical current at 1 Hz:
  - `1.8 µA` (humidity + temperature)
  - `2.8 µA` (pressure + temperature)
  - `3.6 µA` (humidity + pressure + temperature)

### AQPy Wiring Assumption
- Connected via I2C bus 1
- Typical address in this repo: `0x76`
- Pins used:
  - Pi pin 3 (SDA), pin 5 (SCL), pin 1 (3V3), pin 9 (GND)

### Primary References
- Bosch product page:
  - https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/
- Bosch datasheet PDF:
  - https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf

## Raspberry Pi Interface References
- Raspberry Pi UART docs:
  - https://www.raspberrypi.com/documentation/hardware/raspberrypi/uart/README.md
- Raspberry Pi pinout helper:
  - Run `pinout` directly on the Pi
