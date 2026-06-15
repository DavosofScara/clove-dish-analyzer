#!/bin/bash
# Setup script for Mumma email checker automation
# This configures the Monday 7:05 AM email checker job

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.local"
TEMPLATE_FILE="$SCRIPT_DIR/env.template"

echo "🔧 Setting up Mumma email checker automation..."
echo ""

# Step 1: Create .env.local if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    echo "📝 Creating .env.local from template..."
    if [ -f "$TEMPLATE_FILE" ]; then
        cp "$TEMPLATE_FILE" "$ENV_FILE"
        echo "✅ Created $ENV_FILE"
        echo ""
        echo "⚠️  IMPORTANT: Edit $ENV_FILE and add your actual email credentials:"
        echo "   - MUMMA_EMAIL_HOST (e.g., outlook.office365.com)"
        echo "   - MUMMA_EMAIL_USER (dave@clove.solutions)"
        echo "   - MUMMA_EMAIL_PASS (your Outlook app password)"
        echo "   - MUMMA_EMAIL_SENDER (reports@lightspeedhq.com)"
        echo ""
        read -p "Press Enter after you've added your credentials to continue..."
    else
        echo "❌ Template file not found: $TEMPLATE_FILE"
        exit 1
    fi
else
    echo "✅ .env.local already exists"
fi

# Step 2: Verify credentials are set
echo ""
echo "🔍 Verifying credentials..."
source "$ENV_FILE" 2>/dev/null || true

if [ -z "$MUMMA_EMAIL_HOST" ] || [ -z "$MUMMA_EMAIL_USER" ] || [ -z "$MUMMA_EMAIL_PASS" ]; then
    echo "❌ Missing required credentials in .env.local"
    echo "   Please ensure MUMMA_EMAIL_HOST, MUMMA_EMAIL_USER, and MUMMA_EMAIL_PASS are set"
    exit 1
fi

echo "✅ Credentials found"
echo ""

# Step 3: Test email connection (optional)
read -p "Test email connection now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧪 Testing email connection..."
    cd "$REPO_ROOT"
    source "$ENV_FILE"
    python3 "$SCRIPT_DIR/email_attachment_checker.py" --lookback 1 || {
        echo "❌ Email connection test failed. Please check your credentials."
        exit 1
    }
    echo "✅ Email connection successful!"
    echo ""
fi

# Step 4: Set up launchd (macOS) or cron
echo "📅 Setting up scheduled job..."
echo ""
echo "Choose scheduling method:"
echo "1) launchd (macOS - recommended)"
echo "2) cron (works on all Unix systems)"
read -p "Enter choice (1 or 2): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[1]$ ]]; then
    # Launchd setup
    PLIST_NAME="com.clove.mumma-email-checker"
    PLIST_FILE="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
    
    cat > "$PLIST_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>set -a && source "$ENV_FILE" && set +a && cd "$REPO_ROOT" && python3 "$SCRIPT_DIR/email_attachment_checker.py" --run-pipeline --pipeline-output "$REPO_ROOT/data/mumma/processed/revenue_ledger.csv" --pipeline-metadata "$REPO_ROOT/data/mumma/processed/revenue_ledger.metadata.json" >> "$REPO_ROOT/pipelines/mumma/logs/email_checker.log" 2>&1</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>5</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$REPO_ROOT/pipelines/mumma/logs/email_checker.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO_ROOT/pipelines/mumma/logs/email_checker.error.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF
    
    # Create logs directory
    mkdir -p "$REPO_ROOT/pipelines/mumma/logs"
    
    # Load the launchd job
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    launchctl load "$PLIST_FILE"
    
    echo "✅ Launchd job installed: $PLIST_FILE"
    echo ""
    echo "The email checker will run every Monday at 7:05 AM"
    echo ""
    echo "To check status: launchctl list | grep $PLIST_NAME"
    echo "To unload: launchctl unload $PLIST_FILE"
    echo "To reload: launchctl unload $PLIST_FILE && launchctl load $PLIST_FILE"
    echo ""
    echo "Logs will be written to: $REPO_ROOT/pipelines/mumma/logs/email_checker.log"
    
elif [[ $REPLY =~ ^[2]$ ]]; then
    # Cron setup
    CRON_SCRIPT="$SCRIPT_DIR/run_email_checker.sh"
    
    # Create wrapper script that sources .env.local
    cat > "$CRON_SCRIPT" <<EOF
#!/bin/bash
# Wrapper script for Mumma email checker (sources .env.local)
source "$ENV_FILE"
cd "$REPO_ROOT"
python3 "$SCRIPT_DIR/email_attachment_checker.py" \\
    --run-pipeline \\
    --pipeline-output "$REPO_ROOT/data/mumma/processed/revenue_ledger.csv" \\
    --pipeline-metadata "$REPO_ROOT/data/mumma/processed/revenue_ledger.metadata.json"
EOF
    
    chmod +x "$CRON_SCRIPT"
    
    # Create logs directory
    mkdir -p "$REPO_ROOT/pipelines/mumma/logs"
    
    # Add cron job (Monday 7:05 AM)
    CRON_JOB="5 7 * * 1 $CRON_SCRIPT >> $REPO_ROOT/pipelines/mumma/logs/email_checker.log 2>&1"
    
    # Remove existing job if present
    (crontab -l 2>/dev/null | grep -v "$CRON_SCRIPT" || true) | crontab -
    
    # Add new job
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    
    echo "✅ Cron job installed"
    echo ""
    echo "The email checker will run every Monday at 7:05 AM"
    echo ""
    echo "To view cron jobs: crontab -l"
    echo "To edit: crontab -e"
    echo "To remove: crontab -l | grep -v '$CRON_SCRIPT' | crontab -"
    echo ""
    echo "Logs will be written to: $REPO_ROOT/pipelines/mumma/logs/email_checker.log"
else
    echo "❌ Invalid choice"
    exit 1
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Wait for next Monday 7:05 AM, or test manually:"
echo "   cd $REPO_ROOT"
echo "   source $ENV_FILE"
echo "   python3 $SCRIPT_DIR/email_attachment_checker.py --run-pipeline"
echo ""
echo "2. Check logs if issues occur:"
echo "   tail -f $REPO_ROOT/pipelines/mumma/logs/email_checker.log"

