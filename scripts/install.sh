#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo "Run this installer in a native Apple Silicon macOS terminal." >&2
  exit 1
fi
python_bin="${AIRCONTROL_PYTHON:-python3.12}"
if ! "$python_bin" -c 'import sys, platform; assert sys.version_info[:2] == (3, 12) and platform.machine() == "arm64"' 2>/dev/null; then
  echo "Install native Python 3.12 from python.org or with 'brew install python@3.12'." >&2
  echo "Set AIRCONTROL_PYTHON to its full path if necessary." >&2
  exit 1
fi
"$python_bin" -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
./scripts/download-model.sh
