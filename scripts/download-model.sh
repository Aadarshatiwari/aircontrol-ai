#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp assets/.hand-landmarker.XXXXXX)"
trap 'rm -f "$tmp"' EXIT
curl --fail --location --silent --show-error --retry 2 \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task \
  --output "$tmp"
printf '%s  %s\n' fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1 "$tmp" | shasum -a 256 --check
.venv/bin/python -m zipfile -t "$tmp"
chmod 644 "$tmp"
mv "$tmp" assets/hand_landmarker.task
