# AQPy 
Repository for scripts and files to read the PMS5003 air quality index sensor and the BME280 temperature/pressure/humidity sensor from a Raspberry Pi. `systemctl` is used to manage the `read_sensors.py` python script. The data is stored into a postgresql database with the timescaledb extension. From there, Grafana is used to plot the data over time. 

# Hardware 
## PMS5003 
The PMS5003 is assumed to be connected over serial in the `/dev/serial0` position. See the [PMS5003 manual](https://www.aqmd.gov/docs/default-source/aq-spec/resources-page/plantower-pms5003-manual_v2-3.pdf) for wiring diagram of the PMS5003. The `pinout` command on the Raspberry Pi OS will show the function of the GPIO pins. 

| PMS Wire No. | Raspberry Pi Pin No. |
| ------------ | -------------------- |
| VCC (1) | 2 | 
| GND (2) | 6 | 
| SET (3) | unused | 
| RX (4) | 8 | 
| TX (5) | 10 |
| RESET (6) | unused | 

## BME280 
The BME280 is assumed to be connected with I2C. 
| BME280 Terminal | Raspberry Pi Pin No. |
| --------------- | -------------------- |
| 3V3 | 1 | 
| GND | 9 | 
| SCL | 5 | 
| SDA | 3 | 

# Installation
1. install python dependencies:
   * `python3 -m pip install -r requirements.txt`
2. copy `.env.example` to `.env` and set database credentials:
   * `cp .env.example .env`
3. copy `aqi.service` to `/etc/systemd/system` with `sudo cp aqi.service /etc/systemd/system`
4. run `sudo systemctl daemon-reload`
5. run `sudo systemctl enable aqi` to start `aqi.service` at boot
6. either `sudo reboot` or `sudo systemctl start aqi` to start the service
7. make sure its running with `systemctl status aqi`. It will say "active (running)" if things are working properly.

## Grafana (Turnkey Provisioning)
This repo can provision Grafana automatically with:
* datasource `AQPy BME` (database `bme`)
* datasource `AQPy PMS` (database `pms`)
* dashboard `AQPy Edge Sensors + Forecasts` (`uid=aqpy-overview`)

From Pi:
```bash
cd /home/pi/AQPy
sudo ./scripts/provision_grafana.sh
```

Open:
```text
http://<pi-ip>:3000/d/aqpy-overview
```

Notes:
* `scripts/provision_grafana.sh` reads DB credentials from `.env`
* make sure `.env` has real `AQPY_DB_PASSWORD` (not `change_me`)
* first login is typically `admin` / `admin` and Grafana prompts password reset

# Configuration
The script reads configuration from environment variables (typically from `.env` when run with `aqi.service`):

* `AQPY_DB_USER`, `AQPY_DB_PASSWORD`, `AQPY_DB_HOST`, `AQPY_DB_PORT`
* `AQPY_DB_NAME_PMS`, `AQPY_DB_NAME_BME`
* `AQPY_SERIAL_PORT`, `AQPY_SERIAL_BAUD`
* `AQPY_PMS_STARTUP_DELAY`, `AQPY_PMS_AVG_TIME`, `AQPY_SLEEP_SECONDS`
* `AQPY_BME_I2C_PORT`, `AQPY_BME_I2C_ADDR`
* `AQPY_LOG_LEVEL`

# Ingestion Architecture
Sensor ingestion is separated into its own package:
* `aqpy/ingest/config.py`: ingestion runtime config from environment
* `aqpy/ingest/interfaces.py`: ingestion contracts (sensor + repository protocols)
* `aqpy/ingest/pms5003.py`: PMS5003 sensor protocol implementation
* `aqpy/ingest/repository.py`: SQL insert logic for PMS/BME readings
* `aqpy/ingest/service.py`: ingestion orchestration loop and lifecycle
* `read_sensors.py`: thin entrypoint that configures logging and runs ingestion

# Service Hardening
`aqi.service` includes a sandboxing profile (`NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, namespace and syscall restrictions, private temp/mounts, and tight `UMask`) to reduce blast radius.

After updating the unit file:
1. run `sudo systemctl daemon-reload`
2. run `sudo systemctl restart aqi`
3. verify with `systemctl status aqi` and `journalctl -u aqi -n 100`

If `systemd` reports an unknown lvalue, comment out only the unsupported directive in `aqi.service` and reload/restart again.

# Edge ML Forecasting
This repo includes a modular edge-ML forecasting pipeline.

## Edge ML Layout
* `read_sensors.py`: ingestion service (sensor read + DB writes only)
* `aqpy/common/db.py`: shared DB connection logic
* `aqpy/forecast/features.py`: feature engineering
* `aqpy/forecast/model.py`: model fit/predict logic
* `aqpy/forecast/nn_model.py`: small neural network model (MLP) for online updates
* `aqpy/forecast/adaptive_ar.py`: adaptive autoregressive model (RLS with forgetting)
* `aqpy/forecast/rnn_lite.py`: lightweight GRU-style latent model with trained linear head
* `aqpy/forecast/repository.py`: SQL data access for forecast pipeline
* `aqpy/forecast/training.py`: orchestration for training and artifact export
* `aqpy/forecast/inference.py`: orchestration for forecast generation and inserts
* `aqpy/forecast/online_repository.py`: training-state, holdout metrics, and retention run logs
* `aqpy/forecast/online_training.py`: online retraining step with holdout evaluation logging
* `aqpy/forecast/retention.py`: training-aware retention policy
* `aqpy/forecast/specs.py`: model spec loader/filter for multi-sensor orchestration
* `train_forecast_model.py`: thin CLI wrapper for training
* `run_forecast_inference.py`: thin CLI wrapper for inference
* `run_online_training.py`: thin CLI wrapper for online retraining across model types
* `run_data_retention.py`: thin CLI wrapper for retention
* `run_online_training_batch.py`: batch retraining from `configs/model_specs.json`
* `run_forecast_batch.py`: batch inference from `configs/model_specs.json`
* `run_data_retention_batch.py`: batch retention by unique source table from specs
* `configs/model_specs.json`: declarative model list (both `bme` and `pms` targets)
* `sql/forecast_schema.sql`: schema for `predictions` and `model_registry`
* `sql/online_learning_schema.sql`: schema for online training state and holdout metrics
* `aqi-train-online.service` + `aqi-train-online.timer`: scheduled batch retraining across all configured models
* `aqi-forecast.service` + `aqi-forecast.timer`: scheduled batch inference across all configured models
* `aqi-retention.service` + `aqi-retention.timer`: scheduled data retention pruning

## Initialize Forecast Tables
Run once per database used for forecasting:
```bash
psql bme -f sql/raw_schema_bme.sql
psql bme -f sql/forecast_schema.sql
psql bme -f sql/online_learning_schema.sql
psql pms -f sql/raw_schema_pms.sql
psql pms -f sql/forecast_schema.sql
psql pms -f sql/online_learning_schema.sql
```

## Train Model (offline or on Pi)
Example for temperature forecast from the `bme.pi` table:
```bash
python3 train_forecast_model.py \
  --database bme \
  --table pi \
  --time-col t \
  --target temperature \
  --history-hours 336 \
  --lags 1,2,3,6,12 \
  --model-path models/bme_temperature_model.json \
  --register
```

## Run One Inference Pass
```bash
python3 run_forecast_inference.py \
  --model-path models/bme_temperature_nn.json \
  --horizon-steps 12
```

Adaptive AR inference uses the same command with AR artifact path:
```bash
python3 run_forecast_inference.py \
  --model-path models/bme_temperature_ar.json \
  --horizon-steps 12
```

GRU-lite inference uses:
```bash
python3 run_forecast_inference.py \
  --model-path models/bme_temperature_rnn.json \
  --horizon-steps 12
```

## Run One Online NN Retraining Step
```bash
python3 run_online_training.py \
  --database bme \
  --table pi \
  --time-col t \
  --target temperature \
  --model-name aqpy_nn_temperature \
  --model-path models/bme_temperature_nn.json \
  --model-type nn_mlp \
  --history-hours 336 \
  --burn-in-rows 200 \
  --max-train-rows 5000 \
  --lags 1,2,3,6,12 \
  --holdout-ratio 0.2 \
  --min-new-rows 30 \
  --learning-rate 0.01 \
  --epochs 40 \
  --batch-size 64 \
  --hidden-dim 8
```

## Run One Adaptive AR Retraining Step
```bash
python3 run_online_training.py \
  --database bme \
  --table pi \
  --time-col t \
  --target temperature \
  --model-name aqpy_ar_temperature \
  --model-path models/bme_temperature_ar.json \
  --model-type adaptive_ar \
  --history-hours 336 \
  --burn-in-rows 200 \
  --max-train-rows 5000 \
  --lags 1,2,3,6,12 \
  --holdout-ratio 0.2 \
  --min-new-rows 30 \
  --forgetting-factor 0.995 \
  --ar-delta 100.0
```

## Run One GRU-lite Retraining Step
```bash
python3 run_online_training.py \
  --database bme \
  --table pi \
  --time-col t \
  --target temperature \
  --model-name aqpy_rnn_temperature \
  --model-path models/bme_temperature_rnn.json \
  --model-type rnn_lite_gru \
  --history-hours 336 \
  --burn-in-rows 200 \
  --max-train-rows 5000 \
  --seq-len 24 \
  --holdout-ratio 0.2 \
  --min-new-rows 30 \
  --hidden-dim 8 \
  --rnn-ridge 0.001 \
  --random-seed 42
```

Each retraining step logs holdout metrics into `online_training_metrics`, including:
* `holdout_mae`, `holdout_rmse`
* `baseline_mae`, `baseline_rmse`
* `mae_improvement_pct`, `rmse_improvement_pct`
* training hyperparameters and new rows processed

Parameterization notes:
* `--history-hours` controls database read window.
* `--max-train-rows` caps memory/compute by trimming to the most recent rows in that window.
* `--burn-in-rows` blocks model updates until enough data is accumulated.
* For AR/NN lag models use `--lags`; for GRU-lite use `--seq-len`.
* Maximum effective lookback is bounded by what exists in the database and these caps.

## Run One Retention Step (Training-Aware)
```bash
python3 run_data_retention.py \
  --database bme \
  --table pi \
  --time-col t \
  --retention-days 14 \
  --safety-hours 12
```

Retention cutoff is:
* `min(now() - retention_days, min(last_seen_ts) - safety_hours)`

This prevents deleting records that have not been incorporated into online training.

## Run Timers On Pi
```bash
sudo cp aqi-train-online.service /etc/systemd/system/aqi-train-online.service
sudo cp aqi-train-online.timer /etc/systemd/system/aqi-train-online.timer
sudo cp aqi-forecast.service /etc/systemd/system/aqi-forecast.service
sudo cp aqi-forecast.timer /etc/systemd/system/aqi-forecast.timer
sudo cp aqi-retention.service /etc/systemd/system/aqi-retention.service
sudo cp aqi-retention.timer /etc/systemd/system/aqi-retention.timer
sudo systemctl daemon-reload
sudo systemctl enable --now aqi-train-online.timer
sudo systemctl enable --now aqi-forecast.timer
sudo systemctl enable --now aqi-retention.timer
systemctl status aqi-train-online.timer
systemctl status aqi-forecast.timer
systemctl status aqi-retention.timer
journalctl -u aqi-train-online.service -n 100 --no-pager
journalctl -u aqi-forecast.timer -n 20 --no-pager
journalctl -u aqi-forecast.service -n 100 --no-pager
journalctl -u aqi-retention.service -n 100 --no-pager
```

## One-Script Bring-Up (Recommended)
If the Pi already has `/home/pi/AQPy` and `.venv` set up:
```bash
cd /home/pi/AQPy
sudo ./scripts/bringup_edge_stack.sh
```

If network/DB/systemd readiness is delayed at boot, use retry mode:
```bash
cd /home/pi/AQPy
sudo ./scripts/bringup_edge_stack.sh --wait
```

To also run a one-shot bootstrap (train all configured models immediately and write initial predictions):
```bash
cd /home/pi/AQPy
sudo ./scripts/bringup_edge_stack.sh --with-bootstrap
```

To bootstrap later without reinstalling systemd units:
```bash
cd /home/pi/AQPy
./scripts/bootstrap_models.sh
```

## Turnkey Fresh-Clone Install
From a newly cloned repo on Raspberry Pi:
```bash
cd /home/pi/AQPy
sudo ./scripts/install_from_fresh_clone.sh --with-bootstrap
```

To also install Grafana in the same run:
```bash
cd /home/pi/AQPy
sudo ./scripts/install_from_fresh_clone.sh --with-bootstrap --with-grafana
```

This installer:
* installs OS dependencies
* enables I2C + serial hardware (best effort)
* creates `.venv` and installs Python dependencies
* creates `.env` from template if missing
* ensures Postgres databases exist
* runs idempotent bring-up and optional model bootstrap
* optional Grafana install and service enable (`--with-grafana`)
* optional Grafana datasource + dashboard provisioning (`--with-grafana`)

After first run:
1. verify `.env` credentials/settings
2. reboot once if interface settings changed (`sudo reboot`)

## Grafana Metrics Queries (Examples)
Holdout MAE trend:
```sql
SELECT recorded_at AS time, holdout_mae
FROM online_training_metrics
WHERE model_name = 'aqpy_nn_temperature'
ORDER BY recorded_at;
```

Model vs baseline improvement:
```sql
SELECT recorded_at AS time, mae_improvement_pct, rmse_improvement_pct
FROM online_training_metrics
WHERE model_name = 'aqpy_nn_temperature'
ORDER BY recorded_at;
```

## Run Tests
Run the unit tests from repo root:
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

# Maintenance 
`systemctl` stores logs that can be accessed through `journalctl -u aqi`. `journalctl` uses the `less` linux utility to show the logs. A brief summary of `aqi.service` can be obtained by running `systemctl status aqi`. If the sensors stop working (or I didn't code things robustly enough) the python runtime errors will be recorded by `systemctl`. If the `read_sensors.py` script fails, `systemctl` will automatically restart it however if it fails too many times it will wait longer and longer between retries. 
