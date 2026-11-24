#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -f assets/hand_landmarker.task ]]; then
  echo "Run ./scripts/install.sh first." >&2
  exit 1
fi
exec .venv/bin/python -m aircontrol "$@"
