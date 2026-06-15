#!/bin/bash
# Quick status check for Mumma email checker automation

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_FILE="$REPO_ROOT/pipelines/mumma/logs/email_checker.log"
ERROR_LOG="$REPO_ROOT/pipelines/mumma/logs/email_checker.error.log"
LEDGER="$REPO_ROOT/data/mumma/processed/revenue_ledger.csv"
METADATA="$REPO_ROOT/data/mumma/processed/revenue_ledger.metadata.json"
STATE="$REPO_ROOT/data/mumma/state/email_attachments.json"

echo "🔍 Mumma Email Checker Status"
echo "=============================="
echo ""

# Check if launchd job is loaded
echo "📅 Scheduled Job:"
if launchctl list | grep -q "mumma-email-checker"; then
    echo "   ✅ Job is loaded and active"
else
    echo "   ❌ Job not found (may need to reload)"
fi
echo ""

# Check last run time from logs
echo "📋 Last Run:"
if [ -f "$LOG_FILE" ]; then
    LAST_RUN=$(tail -20 "$LOG_FILE" | grep -E "(Downloaded|No new attachments|Running Lightspeed)" | tail -1)
    if [ -n "$LAST_RUN" ]; then
        echo "   $LAST_RUN"
    else
        echo "   No recent activity in logs"
    fi
    echo "   Log file: $LOG_FILE"
    echo "   Last modified: $(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOG_FILE" 2>/dev/null || echo "N/A")"
else
    echo "   ⚠️  No log file found (job hasn't run yet)"
fi
echo ""

# Check for errors
echo "⚠️  Errors:"
if [ -f "$ERROR_LOG" ] && [ -s "$ERROR_LOG" ]; then
    echo "   ❌ Errors found in error log:"
    tail -5 "$ERROR_LOG" | sed 's/^/      /'
else
    echo "   ✅ No errors"
fi
echo ""

# Check output files
echo "📊 Output Files:"
if [ -f "$LEDGER" ]; then
    ROW_COUNT=$(wc -l < "$LEDGER" | tr -d ' ')
    FILE_SIZE=$(du -h "$LEDGER" | cut -f1)
    echo "   ✅ revenue_ledger.csv exists"
    echo "      Rows: $ROW_COUNT"
    echo "      Size: $FILE_SIZE"
    echo "      Last updated: $(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LEDGER" 2>/dev/null || echo "N/A")"
else
    echo "   ⚠️  revenue_ledger.csv not found"
fi

if [ -f "$METADATA" ]; then
    echo "   ✅ revenue_ledger.metadata.json exists"
    echo "      Last updated: $(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$METADATA" 2>/dev/null || echo "N/A")"
else
    echo "   ⚠️  revenue_ledger.metadata.json not found"
fi
echo ""

# Check state file
echo "💾 Email State:"
if [ -f "$STATE" ]; then
    PROCESSED_COUNT=$(jq 'length' "$STATE" 2>/dev/null || echo "0")
    echo "   ✅ State file exists"
    echo "      Processed emails: $PROCESSED_COUNT"
else
    echo "   ⚠️  No state file (no emails processed yet)"
fi
echo ""

# Quick health check
echo "🎯 Quick Health Check:"
HEALTHY=true

if ! launchctl list | grep -q "mumma-email-checker"; then
    echo "   ❌ Job not loaded"
    HEALTHY=false
fi

if [ ! -f "$LOG_FILE" ]; then
    echo "   ⚠️  No logs yet (normal if job hasn't run)"
fi

if [ -f "$ERROR_LOG" ] && [ -s "$ERROR_LOG" ]; then
    echo "   ❌ Errors in error log"
    HEALTHY=false
fi

if [ "$HEALTHY" = true ]; then
    echo "   ✅ All systems operational"
fi
echo ""

echo "📖 View full logs:"
echo "   tail -f $LOG_FILE"
echo ""
echo "🔧 Manual test:"
echo "   cd $REPO_ROOT/pipelines/mumma"
echo "   source .env.local"
echo "   cd ../.."
echo "   python3 pipelines/mumma/email_attachment_checker.py --run-pipeline"

