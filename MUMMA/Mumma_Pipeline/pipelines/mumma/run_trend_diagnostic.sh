#!/bin/bash
# Manual script to run the Mumma trend diagnostic report.
#
# Run this on demand when the weekly report shows a downtrend worth explaining.
# Unlike the weekly report this is not scheduled and does not send email; it
# writes a self-contained HTML file to reports/mumma/.
#
# Usage:
#   ./run_trend_diagnostic.sh                                  # current month to date
#   ./run_trend_diagnostic.sh --start 2026-08-01 --end 2026-08-16
#   ./run_trend_diagnostic.sh --closure 2026-08-12:Mumma       # exclude a genuine closure
#
# Any arguments are passed straight through to mumma_trend_diagnostic.py.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.local"

cd "$REPO_ROOT"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    echo "✅ Loaded environment variables from $ENV_FILE"
else
    echo "⚠️  Warning: .env.local not found. Using system environment variables."
fi

echo "🔎 Validating ledger integrity first..."
if ! python3 "$SCRIPT_DIR/integrity_check.py" > /tmp/mumma_integrity.log 2>&1; then
    echo "❌ Integrity check FAILED. The diagnostic would report unreliable numbers."
    echo "   Review the detail below, fix the pipeline, then re-run."
    echo ""
    tail -20 /tmp/mumma_integrity.log
    exit 1
fi
grep -E "^WARN" /tmp/mumma_integrity.log || echo "   No integrity warnings."

echo ""
echo "📊 Generating Mumma trend diagnostic..."
python3 "$SCRIPT_DIR/mumma_trend_diagnostic.py" "$@"

echo ""
echo "✅ Trend diagnostic generated."
