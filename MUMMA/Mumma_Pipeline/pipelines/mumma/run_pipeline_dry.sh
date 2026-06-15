#!/bin/bash
# Full pipeline dry run: download CSVs → clean → Excel → HTML report (no client email).
#
# Usage:
#   ./run_pipeline_dry.sh              # default 7-day email lookback
#   ./run_pipeline_dry.sh 720          # custom lookback in hours
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_pipeline_common.sh
source "${SCRIPT_DIR}/_pipeline_common.sh"

LOOKBACK="${1:-${DEFAULT_LOOKBACK}}"

echo "🧪 Mumma pipeline DRY RUN (no email will be sent)"
echo "   Lookback: ${LOOKBACK}h"
echo "   Repo: ${REPO_ROOT}"

caffeinate -i -s python3 pipelines/mumma/email_attachment_checker.py \
    --run-pipeline \
    --no-email \
    --lookback "${LOOKBACK}"

HTML=$(ls -t reports/mumma/mumma_weekly_summary_*.html 2>/dev/null | head -1)
if [ -n "${HTML}" ]; then
    echo ""
    echo "✅ Dry run complete."
    echo "   HTML preview: ${REPO_ROOT}/${HTML}"
    echo "   open \"${REPO_ROOT}/${HTML}\""
fi
