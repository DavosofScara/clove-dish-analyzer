#!/bin/bash
# Check script that runs periodically to see if we need to run the pipeline
# This handles cases where the computer was sleeping at the scheduled time

# Set up PATH
export PATH="$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH"

# Check if it's Monday
DAY=$(date +%u)  # 1 = Monday
if [ "$DAY" != "1" ]; then
    exit 0  # Not Monday, do nothing
fi

# Check if it's between 9 AM and 11 AM
HOUR=$(date +%H)
if [ "$HOUR" -lt 9 ] || [ "$HOUR" -ge 11 ]; then
    exit 0  # Outside the window
fi

# Check if we've already run today
LAST_RUN_FILE="$HOME/Library/Logs/mumma_pipeline_last_run.txt"
TODAY=$(date +%Y-%m-%d)

if [ -f "$LAST_RUN_FILE" ] && [ "$(cat "$LAST_RUN_FILE")" = "$TODAY" ]; then
    exit 0  # Already ran today
fi

# Run the pipeline (MUMMA repo — dry by default on Mondays)
/Users/davidcraig/code/clove/MUMMA/Mumma_Pipeline/pipelines/mumma/run_mumma_pipeline.sh

