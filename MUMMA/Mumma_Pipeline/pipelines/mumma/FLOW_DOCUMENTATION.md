# Mumma Pipeline Flow Documentation

## Current Flow (As Understood)

### 1. Email Reception (Monday 6:33 AM)
- **Source**: Lightspeed sends 2 weekly reports to `dave@clove.solutions`:
  - Transaction details report (CSV)
  - Product breakdown report (CSV)

### 2. Laptop Startup (Monday 9:30 AM)
- User turns on laptop
- Automation triggers (via launchd/cron)

### 3. Email Processing (`email_attachment_checker.py`)
- **Action**: Downloads CSV attachments from email
- **Destination**: `data/mumma/raw/transactions/` and `data/mumma/raw/products/`
- **State tracking**: Prevents re-downloading same emails

### 4. Data Cleaning (`lightspeed_clean_pipeline.py`)
- **Input**: Raw CSV files from step 3
- **Outputs**:
  - `revenue_ledger.csv` - **Transaction-level ledger** (all individual transactions, appendable)
  - `daily_sales_summary.xlsx` - **Daily aggregated summary** (Date, Location, Total Sales, Food Sales, Drink Sales, Tax splits)
  - `product_insights.xlsx` - Product-level insights
  - `product_insights_detailed.csv` - Detailed product trends

**Question**: What is `revenue_ledger.csv` used for? Is it:
- A) Historical archive of all transactions?
- B) Used by other scripts?
- C) Just for reference/debugging?

### 5. Excel Master Update (`update_mumma_master.py`)
- **Input**: `daily_sales_summary.xlsx` from step 4
- **Action**:
  - Creates backup of `MUMMA_MASTER_2526.xlsm` in `back_ups/` folder
  - Updates `daily_sales` sheet (append new Date+Location combinations)
  - Updates `pivot` sheet (Date × Location summary)
  - Updates `daily_check` sheet (Date, Mumma/Shack totals, food/drink splits, manual check columns)
  - Refreshes pivot tables
- **Output**: Updated `MUMMA_MASTER_2526.xlsm` ready for manual cash entry and checks

**Question**: For `daily_check` - should we:
- A) Have a row for **every date** from first transaction to today (even if 0)?
- B) Only dates that have sales data?
- C) Only dates in the current week/month?

### 6. Weekly Report Generation (`mumma_weekly_report.py`)
- **Input**: `revenue_ledger.csv` and/or `product_insights_detailed.csv`
- **Action**: Generates weekly insights report with charts
- **Output**: PDF + HTML email sent to client (with CC to dave@clove.solutions)

**Question**: Should the weekly report use:
- A) Data from `daily_sales_summary.xlsx`?
- B) Data from `MUMMA_MASTER_2526.xlsm`?
- C) Data from `revenue_ledger.csv`?

## Final Flow (Confirmed)

### Data Flow
1. **Raw CSVs** → Cleaned and appended to `revenue_ledger.csv` (transaction-level archive)
2. **revenue_ledger.csv** → Aggregated to create `daily_sales_summary.xlsx` (daily totals by location)
3. **daily_sales_summary.xlsx** → Used to update `MUMMA_MASTER_2526.xlsm`

### Decisions Made

1. **Date Range for daily_check**: 
   - ✅ Include ALL dates from July 2019 to today (even if sales are 0)
   - ✅ If one location has sales and the other doesn't, show 0.0 for missing location

2. **Update Strategy for daily_check**:
   - ✅ Only append new dates (never update existing dates)
   - ✅ Don't update existing dates even if data changes

3. **Multiple Reports Same Week**:
   - ✅ Process the latest reports
   - ✅ Deduplicate based on Date+Location

4. **Revenue Ledger Purpose**:
   - Transaction-level archive (all individual transactions)
   - Used to create `daily_sales_summary.xlsx` via aggregation
   - Also used by weekly report for detailed analysis

5. **Weekly Report Timing**:
   - ✅ Always run after Excel update (regardless of new data)

