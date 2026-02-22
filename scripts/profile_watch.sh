#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SNAPSHOT="${REPO_ROOT}/scripts/profile_snapshot.sh"
INTERVAL="${AQPY_PROFILE_WATCH_INTERVAL:-30}"
WITH_LOGS=0
SERIAL_PROBE=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--interval N] [--with-logs] [--serial-probe]

Continuously run AQPy profile snapshots over SSH until Ctrl+C.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval)
      INTERVAL="${2:-30}"
      shift 2
      ;;
    --with-logs)
      WITH_LOGS=1
      shift
      ;;
    --serial-probe)
      SERIAL_PROBE=1
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

if [[ ! -x "${SNAPSHOT}" ]]; then
  echo "Missing executable snapshot script: ${SNAPSHOT}" >&2
  exit 1
fi

while true; do
  clear || true
  args=()
  if [[ "${WITH_LOGS}" -eq 1 ]]; then
    args+=(--with-logs)
  fi
  if [[ "${SERIAL_PROBE}" -eq 1 ]]; then
    args+=(--serial-probe)
  fi
  "${SNAPSHOT}" "${args[@]}"
  echo
  echo "Refreshing in ${INTERVAL}s... (Ctrl+C to stop)"
  sleep "${INTERVAL}"
done
