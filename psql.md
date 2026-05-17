# PostgreSQL 
PostgreSQL is the relational database used to store the sensor data. Postgres handles storing and querying the data in an efficient manner. In addition, timescaledb, an open source time-series data extension for postgres, is used to optimize the database for time-series data. 

# Connecting to the Database 
The temperature, pressure, and humidity are stored in the `bme` database while PMS/AQI data is stored in the `pms` database. Raw sensor rows are in `pi`. Forecast/model outputs are in:
- `predictions` (standard yhat forecasts)
- `garch_forecasts` (mean/variance/volatility forecasts)
- `anomaly_events` (anomaly score + threshold + boolean flag)

From the raspberry pi, these can be accessed by running `psql pms` or `psql bme`. You can switch databases using the connect function in postgres as `\c pms` or `\c bme`. Within a database you can see the tables and their properties using `\d` and `\d+` for additional information.

# Common Queries 
* `select * from pi;`: lists all the data in the table 
* `select * from pi where t >= now() - '7 days'::interval`: show all the data in the past 7 days 
* `select avg(temperature) where t >= now() - '1 days'::interval;`: get the average temperature over the past day 
* `select * from pi order by t desc;`: get all data displaying the most recent entry first
* `select model_name, count(*) from predictions group by 1 order by 2 desc;`: standard forecast row counts
* `select model_name, count(*) from garch_forecasts group by 1 order by 2 desc;`: GARCH forecast row counts
* `select model_name, count(*) from anomaly_events where is_anomaly group by 1 order by 2 desc;`: anomaly event counts

# Timescaledb Queries 
* `select time_bucket('1 hour', t) as time, avg(temperature) from pi group by time order by time desc;`: get average temperature in 1 hour intervals 
