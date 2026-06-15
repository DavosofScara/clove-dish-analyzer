# Mumma Pipeline

Single automated pipeline that runs every Monday morning: downloads Lightspeed reports from email → cleans data → updates Mumma Master Excel → sends weekly report.

**Schedule:** Mondays 9:00–10:45 AM (triggers at 9:00, 9:15, 9:30, 9:45, 10:00, 10:15, 10:30, 10:45). Expect laptop to be asleep until 9 AM; open at 9 and launchd will run when the Mac wakes.

## Quick Setup

1. **Create `.env.local` file:**
   ```bash
   cd pipelines/mumma
   cp env.template .env.local
   ```

2. **Edit `.env.local` with your credentials:**
   - `MUMMA_EMAIL_HOST` - For Hover, use `mail.hover.com`; Outlook use `outlook.office365.com`
   - `MUMMA_EMAIL_USER` - Your email address (e.g., `dave@clove.solutions`)
   - `MUMMA_EMAIL_PASS` - Your email password (or app password for Gmail/Outlook)
   - `MUMMA_EMAIL_SENDER` - Filter for sender (e.g., `do_not_reply@lsk.lightspeedhq.com`)

3. **Install the launchd job:**
   ```bash
   cp pipelines/mumma/com.clove.mumma.pipeline.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.clove.mumma.pipeline.plist
   ```

## Manual Testing

Test the email checker manually:
```bash
cd /Users/davidcraig/code/clove/Clove_Sales_Analyzer
source pipelines/mumma/.env.local
python3 pipelines/mumma/email_attachment_checker.py --run-pipeline
```

## Getting Outlook App Password

If you don't have an app password yet:

1. Go to https://account.microsoft.com/security
2. Sign in with `dave@clove.solutions`
3. Navigate to "Security" → "Advanced security options"
4. Under "App passwords", create a new app password
5. Use that password (not your regular password) for `MUMMA_EMAIL_PASS`

## Pipeline Flow (single script)

`email_attachment_checker.py --run-pipeline` does everything in order:

1. **Download** – IMAP fetch, save CSV attachments to `data/mumma/raw/`
2. **Clean** – `lightspeed_clean_pipeline.py` → revenue_ledger.csv, daily_sales_summary.xlsx
3. **Update Excel** – Append new rows to Mumma Master
4. **Report** – Generate and email weekly insights

## Monitoring & Status

### Quick Status Check

```bash
launchctl list | grep mumma
tail -50 ~/Library/Logs/mumma_pipeline.log
```

### Checking Logs

**View recent pipeline output:**
```bash
tail -100 ~/Library/Logs/mumma_pipeline.log
```

**Check for errors:**
```bash
tail ~/Library/Logs/mumma_pipeline_error.log
```

### Success Indicators

In `~/Library/Logs/mumma_pipeline.log` look for:

- `📥 Downloaded X new attachment(s):` or `No new attachments found.` (both OK)
- `🚀 Running Lightspeed cleaning pipeline...`
- `✅ Appended X new row(s) to daily_sales` or `No new or updated data`
- `Email sent to stephengrieves@gmail.com`
- `Mumma pipeline completed (exit code: 0)`

### Before Monday Morning

1. Close the Mumma Master file (and any other devices that might have it open)
2. Open the laptop at 9 AM; the job will run when the Mac wakes
3. Ensure Excel (and Outlook if needed) are open, but Mumma Master closed

## Troubleshooting

- **Connection fails:** Verify your email password is correct (Hover uses regular password, not app password)
- **No emails found:** Check `MUMMA_EMAIL_SENDER` matches the actual sender address (`do_not_reply@lsk.lightspeedhq.com`)
- **Job didn't run:** Check `launchctl list | grep mumma` to verify job is loaded; ensure you opened the laptop at or after 9 AM
- **Excel -50 error:** Mumma Master file is open elsewhere or corrupted — close it everywhere, or replace with a backup from `back_ups/`
- **Check logs:** `tail -100 ~/Library/Logs/mumma_pipeline.log`

## Manual Run

```bash
cd /Users/davidcraig/code/clove/Clove_Sales_Analyzer
python3 pipelines/mumma/email_attachment_checker.py --run-pipeline --lookback 168
```

