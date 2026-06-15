#!/bin/bash

# MUMMA Automation Cron Job Setup
# This script sets up automatic execution every Monday at 7 AM

echo "Setting up MUMMA automation cron job..."

# Get the current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER_SCRIPT="$SCRIPT_DIR/run_automation.sh"

# Make the launcher script executable
chmod +x "$LAUNCHER_SCRIPT"

# Create the cron job entry (every Monday at 7:00 AM)
CRON_JOB="0 7 * * 1 $LAUNCHER_SCRIPT >> $SCRIPT_DIR/cron.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "$LAUNCHER_SCRIPT"; then
    echo "Cron job already exists. Updating..."
    # Remove existing job
    crontab -l 2>/dev/null | grep -v "$LAUNCHER_SCRIPT" | crontab -
fi

# Add the new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "Cron job set up successfully!"
echo "The automation will run every Monday at 7:00 AM"
echo ""
echo "To view current cron jobs: crontab -l"
echo "To edit cron jobs: crontab -e"
echo "To remove all cron jobs: crontab -r"
echo ""
echo "Logs will be saved to: $SCRIPT_DIR/cron.log" 