# AQPy Troubleshooting

This guide covers the most common issues seen during Raspberry Pi bring-up and operation.

## 1) Cannot Find Pi On Network

### Symptom
- `ping aqpi.local` fails
- `nc -vz aqpi.local 22` fails
- Pi does not appear in DHCP client list

### Checks
```bash
arp -a
nmap -sn 192.168.1.0/24
```

### Fix
1. Reflash with Raspberry Pi Imager and set advanced options (`Cmd+Shift+X`):
   - hostname (`aqpi`)
   - SSH enabled
   - username/password
   - Wi-Fi SSID/password/country
2. Boot Pi and wait 1-2 minutes.
3. SSH by IP first (more reliable than mDNS):
```bash
ssh pi@<pi-ip>
```

## 2) SSH Asks For Password You Do Not Know

### Symptom
- SSH connects but login fails.

### Fix
Reflash and explicitly set username/password in Imager advanced options. Do not rely on defaults.

## 3) `raspi-config` Wireless Error

### Symptom
`Error: 802-11-wireless-security.key-mgmt: property is missing.`

### Fix
Use NetworkManager CLI directly:
```bash
nmcli connection show
nmcli dev wifi list
nmcli dev wifi connect "<SSID>" password "<PASSWORD>" ifname wlan0
```

## 4) Bring-up Fails With `role "root" does not exist`

### Symptom
`psql` tries local auth as root.

### Fix
Run schema commands as `postgres` OS user (already handled by `scripts/bringup_edge_stack.sh`):
```bash
sudo ./scripts/bringup_edge_stack.sh --wait
```

## 5) `aqi.service` Fails With `No module named psycopg2`

### Symptom
Systemd service starts with system Python instead of `.venv`.

### Fix
Reinstall units from repo and reload:
```bash
cd ~/AQPy
sudo ./scripts/bringup_edge_stack.sh --wait
sudo systemctl daemon-reload
sudo systemctl restart aqi
```

Then verify:
```bash
systemctl status aqi --no-pager
```

## 6) DB Auth Fails For User `pi`

### Symptom
`password authentication failed for user "pi"`

### Fix
Create/update role and set `.env` credentials:
```bash
sudo -u postgres psql <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='pi') THEN
    CREATE ROLE pi LOGIN PASSWORD 'raspberry';
  END IF;
END
$$;
ALTER ROLE pi WITH LOGIN PASSWORD 'raspberry';
SQL
```

Set `.env`:
```dotenv
AQPY_DB_USER=pi
AQPY_DB_PASSWORD=raspberry
AQPY_DB_HOST=localhost
AQPY_DB_PORT=5432
```

## 7) Online Training Fails With `must be owner of table ...`

### Symptom
`psycopg2.errors.InsufficientPrivilege: must be owner of table online_training_metrics`

### Fix
Reassign ownership and privileges:
```bash
sudo -u postgres psql -d bme <<'SQL'
ALTER DATABASE bme OWNER TO pi;
ALTER TABLE IF EXISTS predictions OWNER TO pi;
ALTER TABLE IF EXISTS model_registry OWNER TO pi;
ALTER TABLE IF EXISTS online_training_state OWNER TO pi;
ALTER TABLE IF EXISTS online_training_metrics OWNER TO pi;
ALTER TABLE IF EXISTS retention_runs OWNER TO pi;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO pi;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO pi;
GRANT CREATE ON SCHEMA public TO pi;
SQL

sudo -u postgres psql -d pms <<'SQL'
ALTER DATABASE pms OWNER TO pi;
ALTER TABLE IF EXISTS predictions OWNER TO pi;
ALTER TABLE IF EXISTS model_registry OWNER TO pi;
ALTER TABLE IF EXISTS online_training_state OWNER TO pi;
ALTER TABLE IF EXISTS online_training_metrics OWNER TO pi;
ALTER TABLE IF EXISTS retention_runs OWNER TO pi;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO pi;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO pi;
GRANT CREATE ON SCHEMA public TO pi;
SQL
```

## 8) Online Training Fails With `relation "pi" does not exist`

### Symptom
`psycopg2.errors.UndefinedTable: relation "pi" does not exist`

### Fix
Raw sensor tables were missing. Re-run bring-up (new scripts create raw + forecast schemas in both DBs):
```bash
sudo ./scripts/bringup_edge_stack.sh --wait
```

## 9) Ingestion Logs `RuntimeError: start byte not found`

### Symptom
PMS5003 serial frame is not being parsed.

### Meaning
BME can still ingest; PMS path is failing (expected if PMS wiring/data line is wrong).

### Checks
```bash
ls -l /dev/serial0
sudo raspi-config nonint get_serial_hw
sudo raspi-config nonint get_serial_cons
```
Expected:
- `/dev/serial0` exists
- serial hardware enabled (`0`)
- serial login console disabled (`1`)

Read-test:
```bash
./scripts/probe_pms_serial.sh --iterations 30
```

If all reads are zero bytes, recheck PMS wiring/power/TX-RX mapping.

## 10) Grafana Package Not Found

### Symptom
`E: Unable to locate package grafana`

### Fix
Use installer with Grafana option:
```bash
sudo ./scripts/install_from_fresh_clone.sh --with-grafana
```

If needed, verify repo:
```bash
apt-cache policy grafana
```

## 11) Grafana Provision Script Says Service Not Installed

### Symptom
`grafana-server.service is not installed. Install Grafana first.`

### Fix
Install Grafana first, then provision:
```bash
sudo ./scripts/install_from_fresh_clone.sh --with-grafana
sudo ./scripts/provision_grafana.sh
```

## 12) Dashboard Shows Ingestion But No Predictions

### Symptom
Raw sensor rows exist, `predictions` is empty.

### Cause
Models have not trained yet (burn-in/min-new-rows not met).

### Checks
```bash
PGPASSWORD='raspberry' psql -h localhost -U pi -d bme -c "select count(*), max(t) from pi;"
PGPASSWORD='raspberry' psql -h localhost -U pi -d bme -c "select model_name, count(*) from predictions group by 1 order by 1;"
```

### Force one run
```bash
sudo systemctl start aqi-train-online.service
sudo systemctl start aqi-forecast.service
journalctl -u aqi-train-online.service -n 120 --no-pager
journalctl -u aqi-forecast.service -n 120 --no-pager
```

If still in burn-in, either wait for more data or temporarily lower thresholds in `configs/model_specs.json`.

## 13) Useful Status Commands

```bash
systemctl status aqi --no-pager
systemctl status aqi-train-online.timer --no-pager
systemctl status aqi-forecast.timer --no-pager
systemctl status aqi-retention.timer --no-pager

journalctl -u aqi -n 120 --no-pager
journalctl -u aqi-train-online.service -n 120 --no-pager
journalctl -u aqi-forecast.service -n 120 --no-pager
journalctl -u aqi-retention.service -n 120 --no-pager
```

## 14) SSH Profiling Shortcuts

Run one-shot profile:
```bash
cd ~/AQPy
./scripts/profile_snapshot.sh
```

Profile with logs and serial probe:
```bash
./scripts/profile_snapshot.sh --with-logs --serial-probe
```

Live watch mode:
```bash
./scripts/profile_watch.sh --interval 30
```

## 15) Model Spec Validation Fails

### Symptom
Batch services fail immediately after spec edits.

### Fix
Run spec validation locally/on Pi and resolve the reported key/model/type issue:
```bash
cd ~/AQPy
python3 validate_model_specs.py --spec-file configs/model_specs.json
```
