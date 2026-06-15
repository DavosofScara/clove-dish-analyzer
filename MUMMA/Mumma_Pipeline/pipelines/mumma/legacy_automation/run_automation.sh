#!/bin/bash

# MUMMA Report Automation Launcher
# This script runs the automated report generation system

echo "Starting MUMMA Report Automation..."

# Change to the script directory
cd "$(dirname "$0")"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade requirements
echo "Installing/upgrading requirements..."
pip install -r requirements.txt

# Run the automation
echo "Running automation..."
python3 mumma_report_automation_enhanced.py --run-now

echo "Automation completed!" 