# Follow-up: recursive NN instability

The earlier healthy operational snapshot was followed by a watchdog failure in
`aqpy_nn_pm10_en`. Fifty consecutive zero sensor readings were valid data. The
saved NN produced -0.003 at its first recursive step and -2.083 at step 12 because
raw predictions feed subsequent features. Output protection served zero while
preserving those raw values. Continued fitting reproduced the failure.

Online training now gates raw multi-step behavior at the latest input window and
sampled holdout origins before publishing. A failed NN continuation retries one
fresh fit and recomputes the accepted candidate's scores. Failed candidates never
replace live artifacts or advance training state. Missing/stale input skips are
explicit; zero observations remain valid. See DATA_HEALTH.md for exact scope.

The affected model was backed up locally, retrained and rescored. Its continued
candidate failed at step 11 with -3.210; the fresh candidate passed all nine probe
origins and published 12 forecasts. Holdout MAE was 0.574 versus persistence 0.516;
RMSE was 0.799 versus persistence 0.816. The sampled recursive MAE was 0.919 versus
0.529 for persistence. Stability improved; this is not a claim of superior overall
accuracy. Earlier metrics and predictions were retained, not rewritten.

Validation: the full suite ran 100 tests, OK with one integration test skipped;
a subsequent focused nine-test gate suite passed after adding the accepted-fit
rescore regression. Tests cover recursive blow-up, non-finite/out-of-envelope
outputs, valid zero training, missing/stale skips, preservation on rejection, and
fresh-fit rescoring. The next scheduled training and forecast cycles succeeded;
the watchdog checked all 48 models and returned healthy at 22:32 Pacific.

The compact repair-result report is committed beside this note. Full input and
model snapshots remain in `/home/pi/aqpy-watchdog-20260913/` on the Pi.
