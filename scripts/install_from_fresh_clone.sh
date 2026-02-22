#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_USER="${AQPY_APP_USER:-${SUDO_USER:-$(id -un)}}"
APP_GROUP="${AQPY_APP_GROUP:-${APP_USER}}"
APP_DIR="${AQPY_APP_DIR:-${REPO_ROOT}}"
DB_NAME="${AQPY_DB_NAME_BME:-bme}"
PMS_DB_NAME="${AQPY_DB_NAME_PMS:-pms}"
RUN_BOOTSTRAP=0
RUN_GRAFANA=0

usage() {
  cat <<EOF
Usage: sudo $(basename "$0") [--with-bootstrap] [--with-grafana]

Turnkey install from a fresh clone:
  1) Installs OS prerequisites
  2) Enables I2C + serial hardware (best-effort via raspi-config)
  3) Creates Python venv and installs requirements
  4) Creates default .env if missing
  5) Ensures Postgres databases exist (${DB_NAME}, ${PMS_DB_NAME})
  6) Runs bring-up (units/timers/schema)

Options:
  --with-bootstrap   train all configured models immediately and write initial predictions
  --with-grafana     install and enable Grafana server
  -h, --help         show help

Environment overrides:
  AQPY_APP_USER, AQPY_APP_GROUP, AQPY_APP_DIR,
  AQPY_DB_NAME_BME, AQPY_DB_NAME_PMS
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Required command not found: ${cmd}" >&2
    exit 1
  fi
}

install_grafana() {
  echo "[install] Installing Grafana..."
  apt-get install -y apt-transport-https software-properties-common wget gpg
  install -d -m 0755 /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/grafana.gpg ]]; then
    wget -q -O- https://apt.grafana.com/gpg.key | gpg --dearmor >/etc/apt/keyrings/grafana.gpg
    chmod 644 /etc/apt/keyrings/grafana.gpg
  fi
  cat >/etc/apt/sources.list.d/grafana.list <<'EOF'
deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main
EOF
  apt-get update
  apt-get install -y grafana
  systemctl enable --now grafana-server
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-bootstrap)
      RUN_BOOTSTRAP=1
      shift
      ;;
    --with-grafana)
      RUN_GRAFANA=1
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

require_cmd apt-get
require_cmd python3
require_cmd systemctl

echo "[install] Installing OS packages..."
apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  i2c-tools \
  postgresql \
  postgresql-client

require_cmd psql

if [[ "${RUN_GRAFANA}" -eq 1 ]]; then
  install_grafana
fi

if command -v raspi-config >/dev/null 2>&1; then
  echo "[install] Enabling Raspberry Pi interfaces (I2C + serial hardware)..."
  raspi-config nonint do_i2c 0 || true
  raspi-config nonint do_serial_cons 1 || true
  raspi-config nonint do_serial_hw 0 || true
fi

echo "[install] Preparing Python virtual environment..."
cd "${REPO_ROOT}"
if [[ ! -d .venv ]]; then
  sudo -u "${APP_USER}" python3 -m venv .venv
fi
sudo -u "${APP_USER}" .venv/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u "${APP_USER}" .venv/bin/python -m pip install -r requirements.txt

if [[ ! -f .env ]]; then
  echo "[install] Creating .env from template..."
  cp .env.example .env
  chown "${APP_USER}:${APP_GROUP}" .env
  chmod 600 .env
fi

echo "[install] Ensuring PostgreSQL is running..."
systemctl enable --now postgresql

echo "[install] Ensuring databases exist..."
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb "${DB_NAME}"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${PMS_DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb "${PMS_DB_NAME}"
fi

echo "[install] Running edge stack bring-up..."
BRINGUP_ARGS=(--wait)
if [[ "${RUN_BOOTSTRAP}" -eq 1 ]]; then
  BRINGUP_ARGS+=(--with-bootstrap)
fi
AQPY_APP_USER="${APP_USER}" \
AQPY_APP_GROUP="${APP_GROUP}" \
AQPY_APP_DIR="${APP_DIR}" \
AQPY_DB_NAME_BME="${DB_NAME}" \
"${REPO_ROOT}/scripts/bringup_edge_stack.sh" "${BRINGUP_ARGS[@]}"

echo "[install] Completed."
echo "[install] Next: verify .env credentials and run 'sudo reboot' if interfaces were toggled."
