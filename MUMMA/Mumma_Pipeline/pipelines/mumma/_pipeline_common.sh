#!/bin/bash
# Shared setup for Mumma pipeline run scripts.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="${HOME}/Library/Logs/mumma_pipeline.log"
LAST_RUN_FILE="${HOME}/Library/Logs/mumma_pipeline_last_run.txt"

export PATH="${HOME}/.pyenv/shims:${HOME}/.pyenv/bin:${PATH}"

if [ -f "${SCRIPT_DIR}/.env.local" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${SCRIPT_DIR}/.env.local"
    set +a
fi

cd "${REPO_ROOT}" || exit 1

# Default 168h (7 days) for weekly Lightspeed emails; override via arg or .env
DEFAULT_LOOKBACK="${MUMMA_PIPELINE_LOOKBACK_HOURS:-168}"

pipeline_log() {
    echo "$*" | tee -a "${LOG_FILE}"
}
