#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
DB_NAME="${AQPY_DB_NAME_BME:-bme}"
TABLE_NAME="${AQPY_BOOTSTRAP_TABLE:-pi}"
TIME_COL="${AQPY_BOOTSTRAP_TIME_COL:-t}"
TARGET_COL="${AQPY_BOOTSTRAP_TARGET_COL:-temperature}"
HISTORY_HOURS="${AQPY_BOOTSTRAP_HISTORY_HOURS:-336}"
BURN_IN_ROWS="${AQPY_BOOTSTRAP_BURN_IN_ROWS:-200}"
MAX_TRAIN_ROWS="${AQPY_BOOTSTRAP_MAX_TRAIN_ROWS:-5000}"
HOLDOUT_RATIO="${AQPY_BOOTSTRAP_HOLDOUT_RATIO:-0.2}"
MIN_NEW_ROWS="${AQPY_BOOTSTRAP_MIN_NEW_ROWS:-0}"
LAGS="${AQPY_BOOTSTRAP_LAGS:-1,2,3,6,12}"
SEQ_LEN="${AQPY_BOOTSTRAP_SEQ_LEN:-24}"
HORIZON_STEPS="${AQPY_BOOTSTRAP_HORIZON_STEPS:-12}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--skip-inference]

Trains all three models once immediately:
  - nn_mlp           -> models/bme_temperature_nn.json
  - adaptive_ar      -> models/bme_temperature_ar.json
  - rnn_lite_gru     -> models/bme_temperature_rnn.json

Then optionally runs one inference pass for each model.

Environment overrides (optional):
  PYTHON_BIN, AQPY_DB_NAME_BME, AQPY_BOOTSTRAP_TABLE, AQPY_BOOTSTRAP_TIME_COL,
  AQPY_BOOTSTRAP_TARGET_COL, AQPY_BOOTSTRAP_HISTORY_HOURS, AQPY_BOOTSTRAP_BURN_IN_ROWS,
  AQPY_BOOTSTRAP_MAX_TRAIN_ROWS, AQPY_BOOTSTRAP_HOLDOUT_RATIO, AQPY_BOOTSTRAP_MIN_NEW_ROWS,
  AQPY_BOOTSTRAP_LAGS, AQPY_BOOTSTRAP_SEQ_LEN, AQPY_BOOTSTRAP_HORIZON_STEPS
EOF
}

SKIP_INFERENCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-inference)
      SKIP_INFERENCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python executable not found or not executable: ${PYTHON_BIN}" >&2
  echo "Create/activate venv first and install dependencies." >&2
  exit 1
fi

cd "${REPO_ROOT}"

echo "[bootstrap] Training NN model..."
"${PYTHON_BIN}" run_online_training.py \
  --database "${DB_NAME}" \
  --table "${TABLE_NAME}" \
  --time-col "${TIME_COL}" \
  --target "${TARGET_COL}" \
  --model-name aqpy_nn_temperature \
  --model-path models/bme_temperature_nn.json \
  --model-type nn_mlp \
  --history-hours "${HISTORY_HOURS}" \
  --burn-in-rows "${BURN_IN_ROWS}" \
  --max-train-rows "${MAX_TRAIN_ROWS}" \
  --lags "${LAGS}" \
  --holdout-ratio "${HOLDOUT_RATIO}" \
  --min-new-rows "${MIN_NEW_ROWS}" \
  --learning-rate 0.01 \
  --epochs 40 \
  --batch-size 64 \
  --hidden-dim 8

echo "[bootstrap] Training adaptive AR model..."
"${PYTHON_BIN}" run_online_training.py \
  --database "${DB_NAME}" \
  --table "${TABLE_NAME}" \
  --time-col "${TIME_COL}" \
  --target "${TARGET_COL}" \
  --model-name aqpy_ar_temperature \
  --model-path models/bme_temperature_ar.json \
  --model-type adaptive_ar \
  --history-hours "${HISTORY_HOURS}" \
  --burn-in-rows "${BURN_IN_ROWS}" \
  --max-train-rows "${MAX_TRAIN_ROWS}" \
  --lags "${LAGS}" \
  --holdout-ratio "${HOLDOUT_RATIO}" \
  --min-new-rows "${MIN_NEW_ROWS}" \
  --forgetting-factor 0.995 \
  --ar-delta 100.0

echo "[bootstrap] Training GRU-lite model..."
"${PYTHON_BIN}" run_online_training.py \
  --database "${DB_NAME}" \
  --table "${TABLE_NAME}" \
  --time-col "${TIME_COL}" \
  --target "${TARGET_COL}" \
  --model-name aqpy_rnn_temperature \
  --model-path models/bme_temperature_rnn.json \
  --model-type rnn_lite_gru \
  --history-hours "${HISTORY_HOURS}" \
  --burn-in-rows "${BURN_IN_ROWS}" \
  --max-train-rows "${MAX_TRAIN_ROWS}" \
  --seq-len "${SEQ_LEN}" \
  --holdout-ratio "${HOLDOUT_RATIO}" \
  --min-new-rows "${MIN_NEW_ROWS}" \
  --hidden-dim 8 \
  --rnn-ridge 0.001 \
  --random-seed 42

if [[ "${SKIP_INFERENCE}" -eq 0 ]]; then
  echo "[bootstrap] Running one inference pass for all three models..."
  "${PYTHON_BIN}" run_forecast_inference.py --model-path models/bme_temperature_nn.json --horizon-steps "${HORIZON_STEPS}"
  "${PYTHON_BIN}" run_forecast_inference.py --model-path models/bme_temperature_ar.json --horizon-steps "${HORIZON_STEPS}"
  "${PYTHON_BIN}" run_forecast_inference.py --model-path models/bme_temperature_rnn.json --horizon-steps "${HORIZON_STEPS}"
fi

echo "[bootstrap] Complete."
