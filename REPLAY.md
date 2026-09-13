# Chronological history replay

`run_replay.py` creates an isolated replay for any configured AR, NN, or GRU-lite
model. New model families require an explicit adapter. It never loads live model
artifacts and never writes to the production forecast, score, registry, or
training-state tables.

Each run freezes available source readings into an indexed SQLite tape, records
source hashes and model specifications, and starts from scratch. At each virtual
10-minute tick it trains only on earlier/available readings (up to 5000), forecasts
the next 12 sensor observations, and scores predictions only as those observations
are revealed. Horizons are observation counts, approximately minutes, not exact
wall-clock timestamp matches. The first 200 readings are warm-up. Missing tail
observations remain unscored. Gaps in timestamps are preserved; no fake readings
are inserted. Null/non-finite or duplicate source timestamps fail initialization.

Fits use the full past window and deterministic seeds. All families refit from
scratch at each eligible update (at least 30 new rows by default); they reuse only
their replay-owned model between updates. This is a corrected experiment, not an
exact reconstruction of historical live training state, compute latency, or the
old broken algorithm. Past holdout MAE/RMSE reports are not reused as replay scores.

## Prepare a run (explicit model selection required)

Run from `/home/pi/AQPy` as pi. This snapshots inputs but does not execute replay:

```bash
set -a
source .env
set +a
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python run_replay.py init \
  --run-dir replays/ar-pilot \
  --models aqpy_ar_pm25_st \
  --start 2026-08-29T00:00:00-07:00 \
  --end 2026-08-31T00:00:00-07:00 \
  --max-mib 128
```

Choose an interval that actually exists in the source tables. Omitting start/end
uses the available retained history up to the initialization time. `--families ar`,
`nn`, or `rnn` selects all specs in that family. Current defaults issue forecasts
every 600 virtual seconds and use the per-model horizon/training settings.
The immutable local tape also preserves that run's inputs if PostgreSQL later
prunes them; it is not a substitute for a full raw sensor archive.

## Run, pause, resume

Install the units with `scripts/bringup_edge_stack.sh` or the usual systemd install
procedure. Replay timers are never automatically enabled by bring-up. Only start
a replay after reviewing its model selection and input window:

```bash
sudo systemctl enable --now aqi-replay@ar-pilot.timer
sudo systemctl start aqi-replay@ar-pilot.service
```

Each invocation does at most 45 seconds of work (finishing its current model fit),
then yields. The timer resumes after 30 seconds. A global replay lock prevents two
runs working concurrently. Predictions, model parameters and clock progress commit
in one transaction, so interruption/resume cannot duplicate committed forecasts.
Failures are nonzero and visible in systemd. Completed runs have a `complete`
marker, preventing additional work; disable their timers after completion.

```bash
sudo systemctl disable --now aqi-replay@ar-pilot.timer
sudo systemctl stop aqi-replay@ar-pilot.service
# Resume later by enabling the timer and starting the service again.
```

The service uses one BLAS thread, CPUQuota=25% of ONE core, MemoryHigh=192M,
MemoryMax=256M, MemorySwapMax=0, low CPU priority and idle I/O priority. It pauses
between work units when live training/forecast/retention runs, RAM available is
below 600 MiB, or disk free is below 3 GiB. This Pi has memory cgroups disabled, so `LimitAS=256M` and an early Python
RLIMIT_AS limit enforce a 256 MiB virtual-address-space ceiling independently of
cgroups. Allocation failure exits visibly; checkpoint/resume remains available.
These bounds protect this worker, not unrelated programs.
It cannot stop a live model service.

Every run has a disk budget (default 1 GiB, choose 128–256 MiB for a small AR run).
The SQLite tape has a page cap; runtime disk usage checks occur every two seconds.
Small active transactions can temporarily use journal space. CSV export is
streamed and rejected before exceeding its budget; no partial CSV is retained.
Completed runs remain until explicitly archived/deleted. The combined run directory
has an additional 2 GiB cap: initialization, workers and exports fail visibly at
that bound rather than allowing a growing collection of runs to fill the disk.
Keep all runs beneath the same `replays/` directory so this shared cap applies.
The replay logic's code hash must match on resume; after algorithm changes,
initialize a new run or use its original committed implementation.

## Inspect results

```bash
.venv/bin/python run_replay.py status --run-dir replays/ar-pilot
.venv/bin/python run_replay.py export --run-dir replays/ar-pilot
journalctl -u aqi-replay@ar-pilot -n 50 --no-pager
```

Outputs are `replay.sqlite`, `predictions.csv`, `scores.json`, and `status.json`.
Forecast rows contain issue time, training cutoff, future observation index,
model forecast, persistence forecast (last observed reading), and revealed actual.
SQLite/CSV times are Unix seconds UTC. Score summaries report MAE and RMSE by
model and horizon, compared with persistence. Zero baseline error gives a null
percentage improvement. Never overwrite missing live forecasts with replay
values or label replay performance as original live performance.
