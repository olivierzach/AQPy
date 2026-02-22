#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
SPEC_FILE="${AQPY_MODEL_SPEC_FILE:-configs/model_specs.json}"
MODEL_FILTER="${AQPY_BOOTSTRAP_MODELS:-}"
DATABASE_FILTER="${AQPY_BOOTSTRAP_DATABASES:-}"
HORIZON_STEPS="${AQPY_BOOTSTRAP_HORIZON_STEPS:-0}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--skip-inference] [--models model1,model2] [--databases bme,pms]

Bootstraps all configured models from spec file:
  - online training for each selected model spec
  - optional one-shot inference for each selected model spec

Defaults:
  spec file       ${SPEC_FILE}
  horizon steps   from each spec (override with AQPY_BOOTSTRAP_HORIZON_STEPS)

Environment overrides (optional):
  PYTHON_BIN, AQPY_MODEL_SPEC_FILE, AQPY_BOOTSTRAP_MODELS, AQPY_BOOTSTRAP_DATABASES,
  AQPY_BOOTSTRAP_HORIZON_STEPS
EOF
}

SKIP_INFERENCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-inference)
      SKIP_INFERENCE=1
      shift
      ;;
    --models)
      MODEL_FILTER="${2:-}"
      shift 2
      ;;
    --databases)
      DATABASE_FILTER="${2:-}"
      shift 2
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

TRAIN_ARGS=(--spec-file "${SPEC_FILE}")
if [[ -n "${MODEL_FILTER}" ]]; then
  TRAIN_ARGS+=(--models "${MODEL_FILTER}")
fi
if [[ -n "${DATABASE_FILTER}" ]]; then
  TRAIN_ARGS+=(--databases "${DATABASE_FILTER}")
fi

echo "[bootstrap] Training configured models..."
"${PYTHON_BIN}" run_online_training_batch.py "${TRAIN_ARGS[@]}"

if [[ "${SKIP_INFERENCE}" -eq 0 ]]; then
  FORECAST_ARGS=(--spec-file "${SPEC_FILE}")
  if [[ -n "${MODEL_FILTER}" ]]; then
    FORECAST_ARGS+=(--models "${MODEL_FILTER}")
  fi
  if [[ -n "${DATABASE_FILTER}" ]]; then
    FORECAST_ARGS+=(--databases "${DATABASE_FILTER}")
  fi
  if [[ "${HORIZON_STEPS}" -gt 0 ]]; then
    FORECAST_ARGS+=(--horizon-steps "${HORIZON_STEPS}")
  fi
  echo "[bootstrap] Running one inference pass for configured models..."
  "${PYTHON_BIN}" run_forecast_batch.py "${FORECAST_ARGS[@]}"
fi

echo "[bootstrap] Complete."
