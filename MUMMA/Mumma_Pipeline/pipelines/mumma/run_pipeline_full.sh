#!/bin/bash
# Full pipeline with client email: download CSVs → clean → Excel → send weekly report.
#
# Usage:
#   ./run_pipeline_full.sh              # default 7-day email lookback
#   ./run_pipeline_full.sh 720          # custom lookback in hours
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_pipeline_common.sh
source "${SCRIPT_DIR}/_pipeline_common.sh"

LOOKBACK="${1:-${DEFAULT_LOOKBACK}}"

echo "📧 Mumma pipeline FULL RUN (will send client email)"
echo "   Lookback: ${LOOKBACK}h"
echo "   Recipients: ${MUMMA_EMAIL_RECIPIENT:-not set}"
read -r -p "Continue? [y/N] " confirm
if [[ ! "${confirm}" =~ ^[yY]$ ]]; then
    echo "Cancelled."
    exit 0
fi

caffeinate -i -s python3 pipelines/mumma/email_attachment_checker.py \
    --run-pipeline \
    --lookback "${LOOKBACK}"

echo "✅ Full pipeline complete."
