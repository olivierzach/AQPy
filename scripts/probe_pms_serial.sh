#!/usr/bin/env bash
set -euo pipefail

PORT="${AQPY_SERIAL_PORT:-/dev/serial0}"
BAUD="${AQPY_SERIAL_BAUD:-9600}"
ITERATIONS="${AQPY_PMS_PROBE_ITERATIONS:-30}"
CHUNK_SIZE="${AQPY_PMS_PROBE_CHUNK_SIZE:-32}"
SLEEP_SECONDS="${AQPY_PMS_PROBE_SLEEP_SECONDS:-0.3}"
PYTHON_BIN="${AQPY_PYTHON_BIN:-./.venv/bin/python}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--port /dev/serial0] [--baud 9600] [--iterations 30]

Probe PMS serial stream and print:
  index bytes_read first_two_bytes_hex

Environment overrides:
  AQPY_SERIAL_PORT, AQPY_SERIAL_BAUD, AQPY_PMS_PROBE_ITERATIONS,
  AQPY_PMS_PROBE_CHUNK_SIZE, AQPY_PMS_PROBE_SLEEP_SECONDS, AQPY_PYTHON_BIN
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --baud)
      BAUD="${2:-}"
      shift 2
      ;;
    --iterations)
      ITERATIONS="${2:-}"
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
  exit 1
fi

"${PYTHON_BIN}" - <<PY
import time

try:
    import serial
except Exception as exc:
    print(f"pyserial import failed: {exc}")
    raise SystemExit(1)

port = "${PORT}"
baud = int("${BAUD}")
iterations = int("${ITERATIONS}")
chunk_size = int("${CHUNK_SIZE}")
sleep_seconds = float("${SLEEP_SECONDS}")

print(f"Probing {port} @ {baud} baud for {iterations} iterations...")
try:
    s = serial.Serial(port, baud, timeout=2)
except Exception as exc:
    print(f"open failed: {exc}")
    raise SystemExit(1)

for i in range(iterations):
    b = s.read(chunk_size)
    prefix = b[:2].hex() if len(b) >= 2 else ""
    print(i, len(b), prefix)
    time.sleep(sleep_seconds)

s.close()
print("Done.")
PY
