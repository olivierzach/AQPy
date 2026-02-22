#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${AQPY_ENV_FILE:-${REPO_ROOT}/.env}"
WITH_LOGS=0
LOG_LINES="${AQPY_PROFILE_LOG_LINES:-30}"
SERIAL_PROBE=0
SERIAL_ITERATIONS="${AQPY_PROFILE_SERIAL_ITERATIONS:-10}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--with-logs] [--serial-probe] [--log-lines N]

One-shot runtime profile for AQPy over SSH:
  - host health (uptime/load/memory/disk)
  - systemd status for ingest/train/forecast/retention
  - database row counts + latest timestamps
  - latest model metrics/prediction counts
  - optional journal tails and serial probe
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-logs)
      WITH_LOGS=1
      shift
      ;;
    --serial-probe)
      SERIAL_PROBE=1
      shift
      ;;
    --log-lines)
      LOG_LINES="${2:-30}"
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

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

DB_HOST="${AQPY_DB_HOST:-localhost}"
DB_PORT="${AQPY_DB_PORT:-5432}"
DB_USER="${AQPY_DB_USER:-pi}"
DB_PASSWORD="${AQPY_DB_PASSWORD:-}"
DB_NAME_BME="${AQPY_DB_NAME_BME:-bme}"
DB_NAME_PMS="${AQPY_DB_NAME_PMS:-pms}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }
print_header() { printf "\n===== %s =====\n" "$1"; }

print_header "Host"
if date -Is >/dev/null 2>&1; then
  date -Is
else
  date
fi
hostnamectl 2>/dev/null | sed -n '1,8p' || true
uptime || true
df -h / || true
if have_cmd free; then
  free -h || true
fi
if have_cmd vcgencmd; then
  vcgencmd measure_temp || true
fi

print_header "Systemd Units"
for unit in \
  aqi.service \
  aqi-train-online.timer \
  aqi-forecast.timer \
  aqi-retention.timer; do
  systemctl --no-pager --full status "${unit}" 2>/dev/null | sed -n '1,16p' || true
done

if [[ -n "${DB_PASSWORD}" && "${DB_PASSWORD}" != "change_me" ]] && have_cmd psql; then
  export PGPASSWORD="${DB_PASSWORD}"

  print_header "DB: BME Raw Ingest"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME_BME}" -v ON_ERROR_STOP=1 -c \
    "SELECT count(*) AS rows, max(t) AS last_t FROM pi;" || true

  print_header "DB: PMS Raw Ingest"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME_PMS}" -v ON_ERROR_STOP=1 -c \
    "SELECT count(*) AS rows, max(t) AS last_t FROM pi;" || true

  print_header "DB: Predictions (BME)"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME_BME}" -v ON_ERROR_STOP=1 -c \
    "SELECT model_name, count(*) AS rows FROM predictions GROUP BY 1 ORDER BY 1;" || true

  print_header "DB: Predictions (PMS)"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME_PMS}" -v ON_ERROR_STOP=1 -c \
    "SELECT model_name, count(*) AS rows FROM predictions GROUP BY 1 ORDER BY 1;" || true

  print_header "DB: Latest Holdout Metrics (BME)"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME_BME}" -v ON_ERROR_STOP=1 -c \
    "SELECT model_name, recorded_at, holdout_mae, holdout_rmse, mae_improvement_pct
     FROM online_training_metrics
     ORDER BY recorded_at DESC
     LIMIT 6;" || true

  print_header "DB: Latest Holdout Metrics (PMS)"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME_PMS}" -v ON_ERROR_STOP=1 -c \
    "SELECT model_name, recorded_at, holdout_mae, holdout_rmse, mae_improvement_pct
     FROM online_training_metrics
     ORDER BY recorded_at DESC
     LIMIT 6;" || true
else
  print_header "DB"
  echo "Skipped DB checks (missing psql, AQPY_DB_PASSWORD, or placeholder password)."
fi

if [[ "${WITH_LOGS}" -eq 1 ]]; then
  print_header "Recent Logs (aqi)"
  journalctl -u aqi -n "${LOG_LINES}" --no-pager || true
  print_header "Recent Logs (aqi-train-online.service)"
  journalctl -u aqi-train-online.service -n "${LOG_LINES}" --no-pager || true
  print_header "Recent Logs (aqi-forecast.service)"
  journalctl -u aqi-forecast.service -n "${LOG_LINES}" --no-pager || true
fi

if [[ "${SERIAL_PROBE}" -eq 1 ]]; then
  print_header "Serial Probe (/dev/serial0)"
  python3 - <<PY
import time
try:
    import serial
except Exception as exc:
    print(f"pyserial import failed: {exc}")
    raise SystemExit(0)

iterations = int("${SERIAL_ITERATIONS}")
try:
    s = serial.Serial("/dev/serial0", 9600, timeout=2)
except Exception as exc:
    print(f"open failed: {exc}")
    raise SystemExit(0)

for i in range(iterations):
    b = s.read(32)
    prefix = b[:2].hex() if len(b) >= 2 else ""
    print(i, len(b), prefix)
    time.sleep(0.5)
s.close()
PY
fi

echo
echo "Profile complete."
