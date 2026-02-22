#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${AQPY_ENV_FILE:-${REPO_ROOT}/.env}"
GRAFANA_DS_DIR="${AQPY_GRAFANA_DS_DIR:-/etc/grafana/provisioning/datasources}"
GRAFANA_DASH_PROVIDER_DIR="${AQPY_GRAFANA_DASH_PROVIDER_DIR:-/etc/grafana/provisioning/dashboards}"
GRAFANA_DASH_JSON_DIR="${AQPY_GRAFANA_DASH_JSON_DIR:-/var/lib/grafana/dashboards/aqpy}"

usage() {
  cat <<EOF
Usage: sudo $(basename "$0")

Provision Grafana for AQPy:
  1) Creates PostgreSQL datasources (bme + pms)
  2) Installs AQPy dashboard provider
  3) Installs AQPy starter dashboard JSON
  4) Restarts grafana-server

Reads DB connection values from:
  ${ENV_FILE}
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root (sudo)." >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  exit 1
fi

if ! systemctl list-unit-files grafana-server.service >/dev/null 2>&1; then
  echo "grafana-server.service is not installed. Install Grafana first." >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

DB_HOST="${AQPY_DB_HOST:-localhost}"
DB_PORT="${AQPY_DB_PORT:-5432}"
DB_USER="${AQPY_DB_USER:-pi}"
DB_PASSWORD="${AQPY_DB_PASSWORD:-}"
DB_NAME_BME="${AQPY_DB_NAME_BME:-bme}"
DB_NAME_PMS="${AQPY_DB_NAME_PMS:-pms}"

if [[ -z "${DB_PASSWORD}" || "${DB_PASSWORD}" == "change_me" ]]; then
  echo "AQPY_DB_PASSWORD is empty or placeholder in ${ENV_FILE}. Update it first." >&2
  exit 1
fi

install -d -m 0755 "${GRAFANA_DS_DIR}"
install -d -m 0755 "${GRAFANA_DASH_PROVIDER_DIR}"
install -d -m 0755 "${GRAFANA_DASH_JSON_DIR}"

cat >"${GRAFANA_DS_DIR}/aqpy-datasources.yaml" <<EOF
apiVersion: 1

deleteDatasources:
  - name: AQPy BME
    orgId: 1
  - name: AQPy PMS
    orgId: 1

datasources:
  - name: AQPy BME
    uid: aqpy-bme
    type: postgres
    access: proxy
    url: ${DB_HOST}:${DB_PORT}
    database: ${DB_NAME_BME}
    user: ${DB_USER}
    jsonData:
      sslmode: disable
      postgresVersion: 1700
      timescaledb: false
    secureJsonData:
      password: ${DB_PASSWORD}
    isDefault: true
    editable: true
  - name: AQPy PMS
    uid: aqpy-pms
    type: postgres
    access: proxy
    url: ${DB_HOST}:${DB_PORT}
    database: ${DB_NAME_PMS}
    user: ${DB_USER}
    jsonData:
      sslmode: disable
      postgresVersion: 1700
      timescaledb: false
    secureJsonData:
      password: ${DB_PASSWORD}
    editable: true
EOF

cat >"${GRAFANA_DASH_PROVIDER_DIR}/aqpy-dashboards.yaml" <<EOF
apiVersion: 1

providers:
  - name: AQPy
    orgId: 1
    folder: AQPy
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: ${GRAFANA_DASH_JSON_DIR}
EOF

install -m 0644 "${REPO_ROOT}/grafana/dashboards/aqpy-overview.json" \
  "${GRAFANA_DASH_JSON_DIR}/aqpy-overview.json"

systemctl enable --now grafana-server
systemctl restart grafana-server

echo "[grafana] Provisioned datasources and dashboard."
echo "[grafana] Open: http://<pi-ip>:3000"
