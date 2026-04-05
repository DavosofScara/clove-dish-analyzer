#!/usr/bin/env bash
# Send the Evolution2 weekly commercial email via Resend (--send).
# Intended for cron / launchd every Monday at 09:10 (local time).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPORT_DIR}"

# Prefer repo venv if present (create with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)
if [[ -x "${REPORT_DIR}/.venv/bin/python" ]]; then
  exec "${REPORT_DIR}/.venv/bin/python" -m src.main --send
fi

exec python3 -m src.main --send
