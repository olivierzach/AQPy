# Targeted history inventory

Freeze source readings and original forecasts before deciding which models need
repair. This tool reads production databases in read-only transactions and writes
only an isolated SQLite evidence file. Inputs include original issue/target times,
model versions and registry training timestamps. Completed sources/models are
checkpointed; interrupted snapshots resume at those boundaries. Specifications
and the end timestamp remain fixed across resumes.

```bash
set -a
source .env
set +a
.venv/bin/python run_repair_inventory.py --directory replays/repair-inventory \
  --end 2026-09-13T08:00:00+00:00
.venv/bin/python run_repair_inventory.py --directory replays/repair-inventory --analyze
```

Initialization includes all retained source rows through the fixed end. Source
and forecast hashes are recorded. Nonfinite raw sensors fail snapshot; invalid
forecast values are preserved as evidence. Analysis identifies per-row physical,
timing, missing registry and future-model defects, actual source ranges and gaps,
and the largest observed forecast errors. It compares timely forecasts against
nearest actuals within 35 seconds and a last-observation baseline. Error summaries
do not establish independent sample counts or long-term model skill.

An issue gap greater than 20 minutes is evidence for planning, not an authoritative
list of original missing row IDs. Account for warm-up, model introduction and
known downtime before reconstructing a schedule. A missing actual at the tape's
end is not a missing sensor measurement to fabricate.

The CLI enforces a 128 MiB address-space limit and a 512 MiB SQLite budget by
default, with a 2 GiB combined replay-root ceiling and 3 GiB free-disk floor.
Source and forecast reads stream in 512-row batches; analysis handles one source
and model at a time. For large runs use a low-priority systemd job with
CPUQuota=25%, LimitAS=128M and idle I/O priority. Evidence is retained locally;
archive completed runs explicitly when their disk budget is reached.
