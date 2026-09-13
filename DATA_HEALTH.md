# Data health and bounded raw backups

## Fail visibly when current data is invalid

`aqi-health.timer` runs every five minutes. `aqi-health.service` exits nonzero when:
- sensor readings are older than five minutes, null, or non-finite;
- a model file is missing, invalid JSON, non-finite, or has the wrong identity;
- recent forecasts are missing, non-finite, or over 30 minutes old;
- training state/metrics are missing or over two hours old;
- recent training metrics contain NaN/infinity;
- ingestion is down or a scheduled job has failed;
- the daily raw backup is missing, incomplete, or over 30 hours old.

Queries use small indexed windows, 4 MB work_mem, one PostgreSQL worker and a
10-second statement timeout. Results are written atomically to `health/status.json`.
Historical invalid score rows are retained as evidence and excluded by the health
window; new invalid rows fail the check. This is a numerical/freshness check, not
a guarantee of model accuracy or physical plausibility of every finite value.

```bash
systemctl --failed
systemctl status aqi-health --no-pager
cat /home/pi/AQPy/health/status.json
journalctl -u aqi-health -n 80 --no-pager
```

There is no external notification destination configured. Failures are visible
locally through the failed unit, journal, and status file. This watchdog is read-only;
it does not restart models, delete bad data, or silently repair model state.

Prediction and score writes reject non-finite numbers before SQL. Sensor writes
also reject non-finite numbers; five consecutive failed cycles for a sensor cause
ingestion to fail so its existing systemd restart policy can recover it. Changes
inside the continuously running ingestion process require its next restart; the
independent watchdog is effective immediately after being enabled.
RNN training now fits only the training prefix before reporting holdout scores.
Chronological replay scores provide a separate future-only evaluation.

## Daily bounded sensor snapshots

`aqi-sensor-backup.timer` runs at 00:15 UTC daily, catching missed runs after boot.
The service streams `SELECT *` from each raw `pi` table in 512-row chunks into
UTC daily gzip JSONL partitions in `sensor-backups/`. Each file starts with a
header containing columns, table/database, and interval; subsequent lines contain
raw rows. `catalog.json` records counts and SHA-256 hashes of uncompressed content.
Non-finite raw values, if any, are preserved as strings for diagnosis, not silently
removed. The backup does not mark those readings as valid.

The job refreshes yesterday and today, retains closed-day files, and rotates by
both age (365 UTC calendar dates) and total disk budget (512 MiB). Under size
pressure, oldest partitions expire first, so a year of coverage is not guaranteed.
A current partition that cannot fit fails visibly. It also fails if disk free
falls below 3 GiB. Files publish atomically after compression/fsync. Failed partial
files are removed. Worker address space is capped at 128 MiB (LimitAS/RLIMIT_AS even without memory
cgroups), CPU at a quarter of one core,
with idle I/O priority. Snapshot queries are read-only and do not lock out ingestion.

```bash
sudo systemctl start aqi-sensor-backup.service
cat /home/pi/AQPy/sensor-backups/status.json
journalctl -u aqi-sensor-backup -n 50 --no-pager
```

These are sensor snapshots, not full PostgreSQL backups (no users, model state,
Grafana settings, or database schema). The header preserves column names, and rows
can be streamed back into a staging table/replay tape with explicit type checks.
A restore should be validated in isolation; do not blindly append it to live `pi`.
Tests exercise gzip/JSON round trips and bounded rotation.

They protect against future database pruning on this Pi, but not SD-card loss.
Copy completed files/catalog to another device for independent protection. No
remote backup destination is configured. No older raw-data backup was found in
the local locations inspected during recovery; external/offline backups remain
unverified. Model archives do not contain sensor readings.
