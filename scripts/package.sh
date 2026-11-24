#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f assets/hand_landmarker.task ]]; then
  echo "Run ./scripts/install.sh first." >&2
  exit 1
fi
.venv/bin/python -m pip install -r requirements-package.txt
.venv/bin/python -m PyInstaller --noconfirm AirControl.spec
