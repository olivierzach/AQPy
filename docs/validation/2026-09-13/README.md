# AQPy repair completion and operational validation

Validated September 13, 2026, Pacific time (September 14 UTC). Both historical
repair intervals are published. The delta had completed its numerical audit but
had not been published; publication was resumed successfully before this audit.

## Verified results

- Main: 206,075 published repair rows, 173 unresolved cases with unavailable
  source/warm-up evidence. Delta: 2,626 published repair rows, zero unresolved.
- Independently validated evidence files still match their saved SHA-256 hashes.
  A fresh read-only database audit streamed every published prediction and
  unresolved row and matched counts and hashes against both publication records.
  Both runs have publication timestamps. All delta rows are visible through
  `predictions_repaired`. Original production forecast tables remain preserved.
- All 48 model artifacts, sensor sources, recent forecast batches and training
  state/metrics passed the health checks. Both raw sensor tables contain fresh,
  advancing timestamps. Recent forecasts cover 9 BME and 39 PMS models and extend
  into the future. See `final-operational-audit.json` for exact timestamps.
- All 75 overview/repair-history dashboard queries passed against live databases.
  Grafana HTTP `/api/health` returned database `ok`; PostgreSQL and Grafana were
  active. No failed systemd units were present in the final service check.
- All 34 local sensor-backup partitions (44,548 rows) passed gzip/JSON parsing,
  row-count and uncompressed SHA-256 checks against their catalog.
- Unit suite: 92 tests ran, OK, one skipped (requires a dedicated PostgreSQL test
  database). This run did not repeat the isolated database mutation integration
  test; live publication was verified read-only instead. Updated service files
  passed `systemd-analyze verify`; `git diff --check` passed.

## Memory protections deployed

Ingestion and retention now have 128 MiB address-space ceilings, forecasting
256 MiB, and training 384 MiB. Numerical libraries use one thread. The installed
units match the repository changes. Ingestion was restarted successfully with
zero automatic restarts; forecast and training jobs completed successfully under
these limits, including the next scheduled cycle at 21:08 Pacific. Retention's
new limit applies on its next scheduled run; destructive pruning was not forced
as part of validation. Health and backups already had 128 MiB limits.

The Pi reported about 1.16 GiB available RAM, 15 GiB free disk, and zero OOM kills
in its current-boot counter. About 197 MiB of zram swap was occupied; this alone
is not evidence of current pressure. Memory cgroups are unavailable on this Pi,
so `LimitAS` is the effective per-process bound. These limits do not bound the
whole host, PostgreSQL, Grafana, or unsupervised manual jobs and cannot guarantee
that future allocations will always succeed. See `DATA_HEALTH.md` for behavior.

## Evidence and remaining limitations

The combined model disposition report covers both intervals and separates raw,
served and persistence error. Repair validation is not proof that every model
outperforms persistence. The 173 main-run unresolved cases remain explicit.

This directory preserves compact publication and validation reports in Git.
Large replay inventories, raw backups, changing model artifacts, databases and
`.env` remain local and ignored; a Git push is not a backup of those runtime
assets. Raw backups are on the same device, with no remote destination configured.

One initial audit freshness query exceeded its 10-second timeout. It was replaced
with indexed per-model reads and the complete audit passed without changing
production data.
