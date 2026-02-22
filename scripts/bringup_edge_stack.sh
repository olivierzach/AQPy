#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
DB_NAME="${AQPY_DB_NAME_BME:-bme}"
INSTALL_DIR="${AQPY_SYSTEMD_DIR:-/etc/systemd/system}"
APP_DIR="${AQPY_APP_DIR:-${REPO_ROOT}}"
APP_USER="${AQPY_APP_USER:-${SUDO_USER:-pi}}"
APP_GROUP="${AQPY_APP_GROUP:-${APP_USER}}"
WAIT_RETRIES="${AQPY_BRINGUP_WAIT_RETRIES:-10}"
WAIT_SECONDS="${AQPY_BRINGUP_WAIT_SECONDS:-6}"
RUN_BOOTSTRAP=0
RUN_PIP_INSTALL=0
WAIT_MODE=0

usage() {
  cat <<EOF
Usage: sudo $(basename "$0") [--with-bootstrap] [--with-pip-install] [--wait]

End-to-end bring-up:
  1) Initialize forecast/online-learning DB schema
  2) Install systemd units/timers for ingest + train + forecast + retention
  3) Enable/start all services and timers
  4) Optionally bootstrap all 3 models immediately

Options:
  --with-bootstrap     run scripts/bootstrap_models.sh after enabling units
  --with-pip-install   install Python deps via venv pip before setup
  --wait               retry transient failures (db/systemd readiness)
  -h, --help           show help

Environment overrides (optional):
  PYTHON_BIN, AQPY_DB_NAME_BME, AQPY_SYSTEMD_DIR,
  AQPY_APP_DIR, AQPY_APP_USER, AQPY_APP_GROUP,
  AQPY_BRINGUP_WAIT_RETRIES, AQPY_BRINGUP_WAIT_SECONDS
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Required command not found: ${cmd}" >&2
    exit 1
  fi
}

retry_cmd() {
  local retries="$1"
  local delay="$2"
  shift 2
  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if [[ "${attempt}" -ge "${retries}" ]]; then
      echo "Command failed after ${attempt} attempts: $*" >&2
      return 1
    fi
    echo "Retry ${attempt}/${retries} failed; waiting ${delay}s: $*" >&2
    sleep "${delay}"
    attempt=$((attempt + 1))
  done
}

render_unit() {
  local src="$1"
  local dst="$2"
  local app_dir_escaped
  app_dir_escaped="$(printf '%s' "${APP_DIR}" | sed 's/[\/&]/\\&/g')"
  sed \
    -e "s|/home/pi/AQPy|${app_dir_escaped}|g" \
    -e "s/^User=.*/User=${APP_USER}/" \
    -e "s/^Group=.*/Group=${APP_GROUP}/" \
    "${src}" > "${dst}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-bootstrap)
      RUN_BOOTSTRAP=1
      shift
      ;;
    --with-pip-install)
      RUN_PIP_INSTALL=1
      shift
      ;;
    --wait)
      WAIT_MODE=1
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

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root (sudo)." >&2
  exit 1
fi

require_cmd install
require_cmd psql
require_cmd systemctl

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python executable not found or not executable: ${PYTHON_BIN}" >&2
  echo "Create the project venv first: python3 -m venv .venv" >&2
  exit 1
fi

cd "${REPO_ROOT}"

if [[ ! -d /run/systemd/system ]]; then
  echo "systemd does not appear to be active on this host." >&2
  exit 1
fi

SYSTEMD_FILES=(
  "aqi.service"
  "aqi-train-online.service"
  "aqi-train-online.timer"
  "aqi-train-online-ar.service"
  "aqi-train-online-ar.timer"
  "aqi-train-online-rnn.service"
  "aqi-train-online-rnn.timer"
  "aqi-forecast.service"
  "aqi-forecast.timer"
  "aqi-forecast-ar.service"
  "aqi-forecast-ar.timer"
  "aqi-forecast-rnn.service"
  "aqi-forecast-rnn.timer"
  "aqi-retention.service"
  "aqi-retention.timer"
)

for file in "${SYSTEMD_FILES[@]}"; do
  if [[ ! -f "${REPO_ROOT}/${file}" ]]; then
    echo "Missing required unit file: ${REPO_ROOT}/${file}" >&2
    exit 1
  fi
done

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  echo "Configured AQPY_APP_USER does not exist: ${APP_USER}" >&2
  exit 1
fi

if [[ "${RUN_PIP_INSTALL}" -eq 1 ]]; then
  echo "[bringup] Installing Python dependencies..."
  "${PYTHON_BIN}" -m pip install -r requirements.txt
fi

echo "[bringup] Initializing schema in database '${DB_NAME}'..."
if [[ "${WAIT_MODE}" -eq 1 ]]; then
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" psql "${DB_NAME}" -f sql/forecast_schema.sql
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" psql "${DB_NAME}" -f sql/online_learning_schema.sql
else
  psql "${DB_NAME}" -f sql/forecast_schema.sql
  psql "${DB_NAME}" -f sql/online_learning_schema.sql
fi

echo "[bringup] Installing systemd units into ${INSTALL_DIR}..."
for file in "${SYSTEMD_FILES[@]}"; do
  tmp_rendered="$(mktemp)"
  render_unit "${REPO_ROOT}/${file}" "${tmp_rendered}"
  install -m 0644 "${tmp_rendered}" "${INSTALL_DIR}/${file}"
  rm -f "${tmp_rendered}"
done

echo "[bringup] Reloading systemd..."
if [[ "${WAIT_MODE}" -eq 1 ]]; then
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl daemon-reload
else
  systemctl daemon-reload
fi

echo "[bringup] Enabling and starting services/timers..."
if [[ "${WAIT_MODE}" -eq 1 ]]; then
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi.service
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi-train-online.timer
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi-train-online-ar.timer
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi-train-online-rnn.timer
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi-forecast.timer
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi-forecast-ar.timer
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi-forecast-rnn.timer
  retry_cmd "${WAIT_RETRIES}" "${WAIT_SECONDS}" systemctl enable --now aqi-retention.timer
else
  systemctl enable --now aqi.service
  systemctl enable --now aqi-train-online.timer
  systemctl enable --now aqi-train-online-ar.timer
  systemctl enable --now aqi-train-online-rnn.timer
  systemctl enable --now aqi-forecast.timer
  systemctl enable --now aqi-forecast-ar.timer
  systemctl enable --now aqi-forecast-rnn.timer
  systemctl enable --now aqi-retention.timer
fi

if [[ "${RUN_BOOTSTRAP}" -eq 1 ]]; then
  echo "[bringup] Bootstrapping model artifacts and initial predictions..."
  sudo -u "${APP_USER}" "${REPO_ROOT}/scripts/bootstrap_models.sh"
fi

echo "[bringup] Status summary:"
systemctl --no-pager --full status \
  aqi.service \
  aqi-train-online.timer \
  aqi-train-online-ar.timer \
  aqi-train-online-rnn.timer \
  aqi-forecast.timer \
  aqi-forecast-ar.timer \
  aqi-forecast-rnn.timer \
  aqi-retention.timer || true

echo "[bringup] Complete."
