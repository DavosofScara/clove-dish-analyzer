#!/bin/bash
# Report-only dry run (skip email download/clean/Excel). Use after data is already up to date.
#
# Usage:
#   ./run_report_dry.sh
#   ./run_report_dry.sh --week 2026-06-14
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_pipeline_common.sh
source "${SCRIPT_DIR}/_pipeline_common.sh"

echo "🧪 Mumma report DRY RUN (HTML only, no email)"

python3 pipelines/mumma/mumma_weekly_report.py --no-email "$@"

HTML=$(ls -t reports/mumma/mumma_weekly_summary_*.html 2>/dev/null | head -1)
if [ -n "${HTML}" ]; then
    echo ""
    echo "✅ Report preview: ${REPO_ROOT}/${HTML}"
    echo "   open \"${REPO_ROOT}/${HTML}\""
fi
