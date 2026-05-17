# USB CO2 Sensor Plan (Staged, Non-Disruptive)

This note captures the implementation plan for adding a USB-connected CO2 sensor to AQPy
without breaking existing PMS5003 and BME280 ingestion.

## Goals
- Keep PMS + BME behavior unchanged during CO2 rollout.
- Add CO2 as a modular sensor path (ingest, retention, models, dashboards).
- Keep deployment reversible with feature flags.

## Recommended Hardware (USB-First)
Preferred path:
- A native USB CO2 sensor with Linux support and stable device interface.

Selection criteria:
- Exposes a reliable local interface (`/dev/ttyUSB*` or vendor CLI/API).
- NDIR measurement (better long-term indoor stability).
- Clear warm-up and calibration behavior in datasheet.

## Branch / Worktree Workflow
Use an isolated worktree so mainline remains stable while hardware is pending.

```bash
git fetch origin
git worktree add ../AQPy-co2-usb -b feat/co2-usb origin/main
cd ../AQPy-co2-usb
```

## Current Extendability Assessment
What is already modular:
- Forecast/training orchestration is spec-driven (`configs/model_specs.json`).
- Ingest loop supports independent tasks and partial failures (`AQIngestService`).

What is currently hardcoded:
- Ingest config and repository currently assume PMS + BME only.
- Bring-up/provision scripts only initialize/provision BME/PMS databases/sources.

Conclusion:
- CO2 requires incremental extension points, not a rewrite.

## Implementation Plan
1. Add CO2 sensor interface + driver adapter
- Add `aqpy/ingest/co2_usb.py` implementing a `read()` method for CO2 ppm.
- Keep driver selection env-based to allow swapping hardware later.

2. Extend ingest contracts
- Add `CO2Reading` typed contract in `aqpy/ingest/interfaces.py`.
- Add optional `insert_co2_sample()` method on repository protocol.

3. Add CO2 ingest task
- Add `CO2IngestTask` in `aqpy/ingest/service.py`.
- Feature-gate sensor init:
  - `AQPY_CO2_ENABLED`
  - `AQPY_CO2_DRIVER`
  - `AQPY_CO2_DEVICE`
  - optional polling/timing knobs

4. Add CO2 schema (separate DB for isolation)
- New `sql/raw_schema_co2.sql` with table `pi`:
  - `t TIMESTAMPTZ`
  - `co2_ppm DOUBLE PRECISION`
  - optional sensor temp/humidity if available

5. Extend repository
- Add CO2 DB connection only when CO2 enabled.
- Add `insert_co2_sample()` write path.
- Keep existing PMS/BME insert logic unchanged.

6. Bring-up and retention wiring
- Update bring-up script to initialize forecast + online schema for `co2` DB.
- Ensure retention batch includes `co2.pi` raw table and `co2.predictions`.

7. Model spec expansion
- Add CO2 specs (`nn_mlp`, `adaptive_ar`, `rnn_lite_gru`) for target `co2_ppm`.
- Keep burn-in and forecasting timers unchanged (they already run spec batches).

8. Grafana provisioning
- Add datasource `AQPy CO2`.
- Add panels in raw and overview dashboards for:
  - raw CO2 ppm
  - actual vs all-model predictions

9. Tests
- Ingest tests: CO2 enabled/disabled initialization paths.
- Repository tests: CO2 insert and connection lifecycle.
- Coverage matrix tests: model x target x family includes CO2.
- Dashboard tests: CO2 panel/query presence.

## Rollout Sequence (On Pi)
1. Deploy code + schema.
2. Enable CO2 env vars (keep disabled by default first).
3. Run one-shot ingest smoke test; verify rows in `co2.pi`.
4. Enable CO2 in service and restart `aqi.service`.
5. Wait for burn-in threshold; verify model artifacts + predictions.
6. Re-provision Grafana and verify CO2 panels.

## Acceptance Criteria
- Existing PMS/BME rows continue at expected cadence.
- CO2 rows are ingested independently, without affecting PMS/BME failures.
- Retention applies to CO2 raw and predictions per configured windows.
- CO2 models train/forecast from same timers after burn-in.
- Grafana shows raw and predicted CO2.

## Open Decisions (When Hardware Arrives)
- Final sensor driver type and parser implementation.
- Sampling interval for CO2 (match current cycle vs dedicated interval).
- Whether to store extra fields (sensor temp/humidity/status flags).
