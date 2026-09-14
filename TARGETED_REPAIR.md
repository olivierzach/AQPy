# Targeted historical repairs

Start with the frozen inventory and profile in `REPAIR_INVENTORY.md`. Preparation
keeps every original forecast intact, produces separate corrected outputs only
where the physical/stability policy applies, and computes forward-error totals
for unchanged timely forecasts. It plans fresh historical fits only for observed
missing issue intervals, late/nonfinite/incompatible forecasts, or a corrected
source definition. The initial 200-reading warm-up must be available.

```bash
.venv/bin/python run_targeted_repair.py prepare \
  --directory replays/repair-inventory \
  --ar-replay replays/ar-repair-20260912
sudo systemctl enable --now aqi-repair@repair-inventory.timer
```

The optional AR import reuses an already validated reconstruction rather than
fitting it again. Inputs, original forecasts, repair tasks, fresh-fit artifacts,
corrected outputs, unresolved cases and progress remain in the inventory SQLite
file. Output rows record raw and served values, policy/reason, original row IDs,
fit provenance, historical issue/cutoff times, baseline and actual alignment.

Fresh fits use only the bounded past window at the repair issue, with deterministic
seeds; nearby tasks reuse the repair-owned fit until 30 new observations exist.
This reconstructs a declared fresh-fit experiment, not lost original incremental
model state. Late forecasts reconstruct from their estimated sensor input time.
Gaps use a reconstructed ten-minute cadence between observed neighboring issues;
those timestamps are not asserted to be exact deleted row IDs.

Original timestamp horizons match the nearest actual within 35 seconds. Gap and
imported replay horizons count the next observations and report the actual
observation timestamp when available. The `alignment` field distinguishes these
conventions. Unavailable tails stay unscored; missing warm-up is explicit.

The worker takes the global replay lock, uses one thread/quarter core, enforces a
256 MiB address-space ceiling, and yields to live jobs or low headroom. Tasks,
artifacts and outputs commit atomically. Code changes refuse resume. The timer
does not start automatically on installation; disable it after completion.

Completion is not publication approval. Independently verify source fingerprints,
planned coverage, causal fit/prediction calculations, physical/stability policy,
actual alignment and scores. `repair_reference.py` supplies separate mathematical
AR/NN/GRU fit and rollout implementations for this audit. Review time-series
behavior and persistence comparisons as well as execution success.

After the worker completes, run `run_targeted_repair.py finalize --directory DIR`
then `run_targeted_repair.py validate --directory DIR`, with the same memory and
CPU limits as the worker. Finalization exports bounded CSV evidence and scores
previously unscored AR tails against the inventory's independently fingerprinted
source tape. It never changes the original replay. Validation recalculates every
new fit and recursive prediction using an independent numerical implementation,
checks causal cutoffs, repair coverage, physical policy, original score aggregates,
actual alignment, source fingerprints and exported rows. Any discrepancy returns
a nonzero exit status. A successful worker exit alone is not validation.

Apply `sql/repair_history.sql` to each forecast database, then run
`run_targeted_repair.py publish --directory DIR`. Publication requires a finalized
independent PASS audit and unchanged file hashes. It imports in batches of 256,
checks every database row against the audited local evidence, and only then marks
that database's run visible. Re-running is idempotent. `predictions_repaired`
combines originals with explicit corrections/reconstructions; original tables
remain intact. Unrecoverable rows are listed in `history_repair.unresolved`.
Demonstrably invalid unresolved rows are excluded from the combined view. Plausible
originals whose pre-issue source has expired remain visible and are explicitly
labeled `original_unverified_missing_source`; inability to revalidate an old
forecast is not itself evidence that it was wrong. Original rows outside the audited interval are
still labeled `original`, not certified as verified. Publication across the two
databases is resumable, not a distributed atomic transaction.

Storage has hard ceilings: one million repair rows and one million unresolved
rows per database, 128 runs, and a 1 GiB preflight database-size limit. Publication
refuses further work at the ceilings; it does not silently delete evidence.
The row and run limits bound growth during import as well as between runs.
Corrected/reconstructed error scores must be distinguished from original model
performance; output fallback is not evidence that the raw model became better.
