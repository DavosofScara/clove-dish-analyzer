#!/bin/bash
# Manual script to run the Mumma weekly report
# Copy and paste this entire script to run anytime

set -e

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.local"

# Change to repo root
cd "$REPO_ROOT"

# Load environment variables
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    echo "✅ Loaded environment variables from $ENV_FILE"
else
    echo "⚠️  Warning: .env.local not found. Using system environment variables."
fi

# Run the weekly report
echo "📊 Generating Mumma weekly report..."
python3 "$SCRIPT_DIR/mumma_weekly_report.py"

echo ""
echo "✅ Weekly report generated and emailed!"

