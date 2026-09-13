# Grafana
Grafana is a dashboard frontend for the postgres database. Queries can be entered in the graphical interface and plotted. The raspberry pi hosts the grafana server. 

## Turnkey Setup
From `/home/pi/AQPy`:
```bash
sudo ./scripts/install_from_fresh_clone.sh --with-grafana
sudo ./scripts/provision_grafana.sh
```

Dashboards:
- Overview: `http://<pi-ip>:3000/d/aqpy-overview`
- Raw sensors: `http://<pi-ip>:3000/d/aqpy-raw`

## Reload the AQPy UI
To restore the repository's datasource and dashboard configuration:
```bash
cd /home/pi/AQPy
sudo ./scripts/provision_grafana.sh
sudo systemctl status grafana-server --no-pager
```
The script installs the dashboard JSON files and restarts Grafana. It overwrites
the provisioned AQPy dashboards, including edits made to them through the UI.
It does not reset login credentials or delete sensor/model data.

If only a service restart is needed:
```bash
sudo systemctl restart grafana-server
```
Then hard-refresh the browser (Ctrl+Shift+R or Cmd+Shift+R) and open
`http://aqpi.local:3000/d/aqpy-overview` (or use the Pi's IP address).

# Accessing Grafana 
Find the raspberry pi's local ip address. You could check your router's list of connect devices. The raspberry pi should show up as aqpi. Alternatively, plug the raspberry pi into a monitor and using a keyboard open the terminal application and run `ip addr show`. If connected over wifi, use the ip address listed under `wlan0`. If over ethernet, use `eth0`. Enter the IP address into your browser while connected to the same network the raspberry pi is on. 

# Dashboard Setup
I have added four plots and three statistics to the grafana dashboard. The plots of temperature, humidity, and AQI use the timescaledb function `time_bucket` to plot averages over a window dependent interval. The width of the interval is determined by the `PPI` (points per interval) variable accessed by clicking the gear icon in top right corner of the dashboard. The default is to plot 50 points. Some amount of averaging is required to smooth the sensor data. The fourth plot, "Sensor Readings per Hour", should reliably read 60. This indicates the raspberry pi is reading the sensors once per minute without errors. This frequency is defined in `read_sensors.py`. 

## Derived AQI Source
AQI panels use derived PMS view data:
- `pms_aqi` (backed by `derived.pms_aqi`)
- Derived from `pms.pi.pm25_st` and `pms.pi.pm10_st` with EPA breakpoint interpolation

Why view-based:
- No raw-table mutation
- Historical backfill is automatic (all past rows are queryable as AQI)
- No dedicated ETL timer required

When to switch to ETL/materialized:
- If AQI queries become heavy enough that on-read computation becomes a bottleneck
- In that case, schedule a refresh/upsert timer and keep raw + derived data paths separate
