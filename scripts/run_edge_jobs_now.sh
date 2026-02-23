#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${AQPY_ENV_FILE:-${REPO_ROOT}/.env}"
PYTHON_BIN="${AQPY_PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
SPEC_FILE="${AQPY_MODEL_SPEC_FILE:-${REPO_ROOT}/configs/model_specs.json}"
RUN_TRAIN=1
RUN_FORECAST=1
RUN_RETENTION=0
DB_FILTER=""
MODEL_FILTER=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [--train-only|--forecast-only|--retention-only|--with-retention] [--databases bme,pms] [--models m1,m2]

Runs AQPy batch jobs immediately without requiring:
  - manual venv activation
  - manual export/source of .env

Defaults:
  - train + forecast
  - no retention
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --train-only)
      RUN_TRAIN=1
      RUN_FORECAST=0
      RUN_RETENTION=0
      shift
      ;;
    --forecast-only)
      RUN_TRAIN=0
      RUN_FORECAST=1
      RUN_RETENTION=0
      shift
      ;;
    --retention-only)
      RUN_TRAIN=0
      RUN_FORECAST=0
      RUN_RETENTION=1
      shift
      ;;
    --with-retention)
      RUN_RETENTION=1
      shift
      ;;
    --databases)
      DB_FILTER="${2:-}"
      shift 2
      ;;
    --models)
      MODEL_FILTER="${2:-}"
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
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  exit 1
fi
if [[ ! -f "${SPEC_FILE}" ]]; then
  echo "Missing model spec file: ${SPEC_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

COMMON_ARGS=(--spec-file "${SPEC_FILE}")
if [[ -n "${DB_FILTER}" ]]; then
  COMMON_ARGS+=(--databases "${DB_FILTER}")
fi
if [[ -n "${MODEL_FILTER}" ]]; then
  COMMON_ARGS+=(--models "${MODEL_FILTER}")
fi

cd "${REPO_ROOT}"
"${PYTHON_BIN}" validate_model_specs.py --spec-file "${SPEC_FILE}"

if [[ "${RUN_TRAIN}" -eq 1 ]]; then
  echo "[run-now] Training batch..."
  "${PYTHON_BIN}" run_online_training_batch.py "${COMMON_ARGS[@]}"
fi

if [[ "${RUN_FORECAST}" -eq 1 ]]; then
  echo "[run-now] Forecast batch..."
  "${PYTHON_BIN}" run_forecast_batch.py "${COMMON_ARGS[@]}"
fi

if [[ "${RUN_RETENTION}" -eq 1 ]]; then
  echo "[run-now] Retention batch..."
  "${PYTHON_BIN}" run_data_retention_batch.py "${COMMON_ARGS[@]}"
fi

echo "[run-now] Complete."
