#!/usr/bin/env bash
# Standalone cumulative season YoY chart (PNG). Not part of the weekly email send.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPORT_DIR}"
if [[ -x "${REPORT_DIR}/.venv/bin/python" ]]; then
  exec "${REPORT_DIR}/.venv/bin/python" -m src.cumulative_season_yoy "$@"
fi
exec python3 -m src.cumulative_season_yoy "$@"
