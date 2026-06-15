#!/bin/bash

# MUMMA Automation Complete Setup Script
# This script sets up the entire automation system

echo "🚀 MUMMA Report Automation Setup"
echo "================================="

# Get the current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📁 Working directory: $SCRIPT_DIR"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed or not in PATH"
    echo "   Please install Python 3.8 or higher"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Create virtual environment
echo "🔧 Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade requirements
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Make scripts executable
echo "🔐 Making scripts executable..."
chmod +x run_automation.sh
chmod +x setup_cron.sh
chmod +x setup_automation.sh

# Create necessary directories
echo "📂 Creating necessary directories..."
mkdir -p Reports
mkdir -p logs

# Test the system
echo "🧪 Testing the automation system..."
python3 test_automation.py

if [ $? -eq 0 ]; then
    echo "✅ System test passed!"
else
    echo "❌ System test failed. Please check the logs."
    exit 1
fi

# Setup instructions
echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Configure email credentials:"
echo "   - Edit email_config.py and add your Outlook password, OR"
echo "   - Set environment variable: export OUTLOOK_PASSWORD='your_password'"
echo ""
echo "2. Test email functionality:"
echo "   python3 test_email.py"
echo ""
echo "3. Run automation manually:"
echo "   ./run_automation.sh"
echo ""
echo "4. Set up automatic execution (every Monday at 7 AM):"
echo "   ./setup_cron.sh"
echo ""
echo "5. View logs:"
echo "   tail -f mumma_automation.log"
echo ""
echo "📁 Generated reports will be saved to: Reports/"
echo "📧 Reports will be emailed to: davevondavrosh@gmail.com"
echo ""
echo "🔧 For troubleshooting, check:"
echo "   - mumma_automation.log (main logs)"
echo "   - cron.log (scheduled execution logs)"
echo "   - Reports/ (generated PDFs)"
echo ""
echo "📚 Full documentation: README.md" 