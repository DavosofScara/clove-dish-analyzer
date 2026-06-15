# Production Testing Checklist

## Pre-Test Setup
- [ ] Backup `MUMMA_MASTER_2526.xlsm` manually (extra safety)
- [ ] Verify `.env.local` has correct email credentials
- [ ] Check that Excel backup folder exists and is accessible

## Test 1: Email Download Only (Dry Run)
```bash
cd /Users/davidcraig/code/clove/Clove_Sales_Analyzer
python3 pipelines/mumma/email_attachment_checker.py
# (without --run-pipeline flag)
```
**Check**:
- [ ] New attachments downloaded to `data/mumma/raw/transactions/` and `data/mumma/raw/products/`
- [ ] Files are CSV format and readable
- [ ] State file updated (no re-download on second run)

## Test 2: Data Cleaning Pipeline
```bash
python3 pipelines/mumma/lightspeed_clean_pipeline.py
```
**Check**:
- [ ] `revenue_ledger.csv` updated with new rows
- [ ] `daily_sales_summary.xlsx` updated with new dates
- [ ] Both Mumma and Shack locations present in output
- [ ] Check `daily_sales_summary.xlsx` manually: verify Date, Location, Total Sales columns

## Test 3: Excel Master Update (Critical Test)
```bash
python3 pipelines/mumma/update_mumma_master.py
```
**Check**:
- [ ] Backup created in `back_ups/` folder
- [ ] No errors during execution
- [ ] `daily_sales` sheet: New Date+Location rows appended (no duplicates)
- [ ] `pivot` sheet: New dates added
- [ ] `daily_check` sheet: 
  - [ ] New dates appended (only new, not updating existing)
  - [ ] All dates from July 2019 to today present (check row count)
  - [ ] Shack columns populated (not blank)
  - [ ] No duplicate dates
  - [ ] Manual columns (Checked, Cash €) preserved
  - [ ] Pivot tables refreshed
- [ ] File opens correctly in Excel
- [ ] Slicers still work
- [ ] Dashboard elements intact

## Test 4: Weekly Report Generation
```bash
python3 pipelines/mumma/mumma_weekly_report.py --no-email
```
**Check**:
- [ ] Report PDF generated in `pipelines/mumma/reports/`
- [ ] Charts generated as PNG files
- [ ] Report includes both Mumma and Shack data
- [ ] No errors in console output

## Test 5: Full Flow (End-to-End)
```bash
python3 pipelines/mumma/email_attachment_checker.py --run-pipeline
```
**Check**:
- [ ] All steps complete without errors
- [ ] Email received with report (if testing with real email)
- [ ] Excel master file updated correctly
- [ ] Everything matches results from individual tests above

## Critical Validations

### daily_check Sheet Specific Checks
1. **Date Coverage**:
   ```python
   # In Python console or Excel:
   # Should have dates from 2019-07-01 to today
   # Count rows: Should be approximately (today - 2019-07-01) days
   ```

2. **Shack Data**:
   - [ ] At least some rows have Shack Total (€) > 0
   - [ ] Shack Food (€) and Shack Drink (€) populated where applicable
   - [ ] No blank/NaN values in Shack columns

3. **No Duplicates**:
   - [ ] Each date appears exactly once
   - [ ] No duplicate Date entries

4. **Manual Columns Preserved**:
   - [ ] Existing checkboxes still in place
   - [ ] Existing cash entries unchanged
   - [ ] New rows have empty manual columns

### Rollback Plan (If Issues Found)
1. **Restore from backup**:
   - Find latest backup in `back_ups/` folder
   - Copy back to `MUMMA_MASTER_2526.xlsm` location
   - Overwrite corrupted file

2. **Check what went wrong**:
   - Review console output
   - Check backup file is valid
   - Identify which step failed

## Production Readiness Checklist
- [ ] All individual tests pass
- [ ] Full end-to-end test passes
- [ ] Excel file structure intact
- [ ] No data corruption
- [ ] Automation script ready (`setup_email_checker.sh` configured)
- [ ] Launch agent configured and enabled
- [ ] Monitor first production run tomorrow morning

## Monitoring Tomorrow Morning
After laptop turns on at 9:30 AM:
1. Check `pipelines/mumma/logs/email_checker.log` for errors
2. Verify new backup created
3. Check Excel file updated correctly
4. Verify email report sent
5. Quick spot-check of data accuracy

