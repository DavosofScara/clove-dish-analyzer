#!/bin/bash
# Scheduled Monday pipeline wrapper (launchd). Defaults to DRY RUN for safety.
#
# To send client emails from cron, point launchd at run_pipeline_full_scheduled.sh instead,
# or set MUMMA_SCHEDULED_MODE=full in .env.local.
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_pipeline_common.sh
source "${SCRIPT_DIR}/_pipeline_common.sh"

DAY=$(date +%u)  # 1 = Monday
if [ "$DAY" != "1" ]; then
    exit 0
fi

HOUR=$(date +%H)
if [ "$HOUR" -lt 9 ] || [ "$HOUR" -ge 11 ]; then
    exit 0
fi

TODAY=$(date +%Y-%m-%d)
CURRENT_TIME=$(date +%H:%M)

if [ -f "$LAST_RUN_FILE" ] && [ "$(cat "$LAST_RUN_FILE")" = "$TODAY" ]; then
    exit 0
fi

{
    echo "========================================"
    echo "$(date): Starting Mumma pipeline (scheduled)"
    echo "Day of week: $(date +%A)"
    echo "Time: $CURRENT_TIME"
    echo "Mode: ${MUMMA_SCHEDULED_MODE:-dry}"
} >> "${LOG_FILE}" 2>&1

LOOKBACK="${DEFAULT_LOOKBACK}"
MODE="${MUMMA_SCHEDULED_MODE:-dry}"

if [ "$MODE" = "full" ]; then
    PIPELINE_CMD=(python3 pipelines/mumma/email_attachment_checker.py --run-pipeline --lookback "${LOOKBACK}")
else
    PIPELINE_CMD=(python3 pipelines/mumma/email_attachment_checker.py --run-pipeline --no-email --lookback "${LOOKBACK}")
fi

caffeinate -i -s "${PIPELINE_CMD[@]}" >> "${LOG_FILE}" 2>&1
EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    if tail -30 "${LOG_FILE}" | grep -q "Downloaded .* new attachment"; then
        echo "$TODAY" > "$LAST_RUN_FILE"
    fi
fi

{
    echo "$(date): Mumma pipeline completed (exit code: ${EXIT_CODE}, mode: ${MODE})"
    echo "========================================"
} >> "${LOG_FILE}" 2>&1

exit "$EXIT_CODE"
