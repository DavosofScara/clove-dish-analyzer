#!/usr/bin/env bash
# Send the Evolution2 weekly CDP email via Resend (--send).
# Intended for cron / launchd every Monday at 09:20 (local time).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPORT_DIR}"

if [[ -x "${REPORT_DIR}/.venv/bin/python" ]]; then
  exec "${REPORT_DIR}/.venv/bin/python" -m src.cdp_main --send
fi

exec python3 -m src.cdp_main --send
