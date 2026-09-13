# Physical forecast output policy

Live inference preserves the unmodified model forecast in `predictions.raw_yhat`
and records the policy/reason in `output_policy`. `yhat` is the served value.
Older rows retain null raw_yhat and `legacy_unchecked`; their original yhat is
not rewritten by deployment.

`physical_output_v1` leaves valid forecasts unchanged. Negative particulate mass
and particle counts project to zero, the nearest nonnegative value. Impossible
humidity outside 0–100%, derived index outside 0–500, or negative pressure uses
the last available observed reading. Nonfinite forecasts and invalid baselines
still fail. No future actual is used in the correction. Corrections affect output
only, not the raw model's internal recursive rollout.

This policy does not certify model skill. Report error for raw and served values
separately and compare with persistence. An output that repeatedly requires
correction warrants investigation even when the served values are physically
valid. The watchdog now rejects physical-domain violations in the latest forecast
batch; it does not treat old invalid rows as a failure of the newly corrected batch.

Existing installations must apply `sql/prediction_policy_migration.sql` to bme
and pms before deploying this writer. `forecast_schema.sql` includes the migration
for bring-up. It adds nullable raw values and a policy column without changing
existing forecasts. The migration uses a short lock timeout.

Historical repairs use a separate provenance-preserving output. Preserve original
predictions, actual alignment and correction reason; never label a reconstructed
forecast or corrected score as the original live model's historical performance.
