#!/usr/bin/env python3
"""
Quick validation script to check daily_check sheet after update.
Run this after update_mumma_master.py to verify results.
"""
from pathlib import Path
from datetime import date
import pandas as pd
import xlwings as xw

MUMMA_MASTER_PATH = Path(
    "/Users/davidcraig/Dropbox (Personal)/Mumma/2526/MUMMA_MASTER_2526.xlsm"
)

def validate_daily_check():
    """Validate daily_check sheet structure and data."""
    if not MUMMA_MASTER_PATH.exists():
        print(f"❌ File not found: {MUMMA_MASTER_PATH}")
        return False
    
    app = xw.App(visible=False, add_book=False)
    try:
        wb = app.books.open(str(MUMMA_MASTER_PATH))
        if "daily_check" not in [s.name for s in wb.sheets]:
            print("❌ daily_check sheet not found")
            return False
        
        ws = wb.sheets["daily_check"]
        
        # Read the table data (starting at row 15)
        used = ws.used_range
        if not used or used.last_cell.row < 15:
            print("❌ No data found in daily_check sheet")
            return False
        
        # Read from row 15 (header) onwards
        last_col = used.last_cell.column
        last_col_letter = chr(64 + last_col) if last_col <= 26 else "Z"
        data = ws.range(f"D15:{last_col_letter}{used.last_cell.row}").value
        
        if not data or not isinstance(data, list):
            print("❌ Could not read data")
            return False
        
        if not isinstance(data[0], list):
            print("❌ Unexpected data format")
            return False
        
        headers = data[0]
        rows = data[1:] if len(data) > 1 else []
        
        if "Date" not in headers:
            print("❌ Date column not found")
            return False
        
        df = pd.DataFrame(rows, columns=headers)
        
        # Filter out completely empty rows (where Date is None/NaT and all other columns are empty/None)
        date_col_idx = headers.index("Date")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        
        # Remove rows where Date is NaT AND all other columns are empty/None
        # (These are leftover empty rows from previous writes)
        date_valid = df["Date"].notna()
        other_cols = [c for c in df.columns if c != "Date"]
        other_cols_empty = df[other_cols].isna().all(axis=1) | (df[other_cols] == None).all(axis=1)
        empty_rows = ~date_valid & other_cols_empty
        df = df[~empty_rows].copy()
        
        if len(empty_rows) > 0:
            print(f"ℹ️  Filtered out {empty_rows.sum()} completely empty rows from validation")
        
        # Validations
        print("\n📊 Validation Results:")
        print("=" * 60)
        
        # 1. Date range check
        start_date = date(2019, 7, 1)
        end_date = date.today()
        expected_days = (end_date - start_date).days + 1
        actual_rows = len(df)
        print(f"✅ Date Range: {start_date} to {end_date}")
        print(f"   Expected rows: {expected_days}")
        print(f"   Actual rows: {actual_rows}")
        if abs(actual_rows - expected_days) > 5:  # Allow 5 day tolerance
            print(f"   ⚠️  Warning: Row count differs by more than 5 days")
        
        # 2. Duplicate check (exclude NaT values)
        valid_dates = df[df["Date"].notna()].copy()
        duplicates = valid_dates[valid_dates["Date"].duplicated()]
        nat_count = df["Date"].isna().sum()
        if len(duplicates) > 0:
            print(f"❌ Found {len(duplicates)} duplicate dates!")
            print(f"   Duplicate dates: {duplicates['Date'].tolist()[:10]}")
        else:
            print(f"✅ No duplicate dates")
        if nat_count > 0:
            print(f"⚠️  Found {nat_count} rows with invalid/NaT dates")
        
        # 3. Shack data check
        shack_cols = ["Shack Total (€)", "Shack Food (€)", "Shack Drink (€)"]
        missing_shack_cols = [c for c in shack_cols if c not in df.columns]
        if missing_shack_cols:
            print(f"❌ Missing Shack columns: {missing_shack_cols}")
        else:
            # Convert to numeric, handling any datetime/string/non-numeric values
            try:
                shack_total = pd.to_numeric(df["Shack Total (€)"], errors="coerce")
                shack_total = shack_total.fillna(0)
                # Ensure it's numeric, not datetime
                if not pd.api.types.is_numeric_dtype(shack_total):
                    shack_total = pd.to_numeric(shack_total, errors="coerce").fillna(0)
                rows_with_shack = df[shack_total > 0]
                print(f"✅ Shack columns present")
                print(f"   Rows with Shack data: {len(rows_with_shack)}")
                if len(rows_with_shack) == 0:
                    print(f"   ⚠️  Warning: No rows have Shack sales > 0")
            except Exception as e:
                print(f"⚠️  Error checking Shack data: {e}")
                print(f"✅ Shack columns present (could not count rows with data)")
        
        # 4. Mumma data check
        mumma_cols = ["Mumma Total (€)", "Mumma Food (€)", "Mumma Drink (€)"]
        missing_mumma_cols = [c for c in mumma_cols if c not in df.columns]
        if missing_mumma_cols:
            print(f"❌ Missing Mumma columns: {missing_mumma_cols}")
        else:
            # Convert to numeric, handling any datetime/string/non-numeric values
            try:
                mumma_total = pd.to_numeric(df["Mumma Total (€)"], errors="coerce")
                mumma_total = mumma_total.fillna(0)
                # Ensure it's numeric, not datetime
                if not pd.api.types.is_numeric_dtype(mumma_total):
                    mumma_total = pd.to_numeric(mumma_total, errors="coerce").fillna(0)
                rows_with_mumma = df[mumma_total > 0]
                print(f"✅ Mumma columns present")
                print(f"   Rows with Mumma data: {len(rows_with_mumma)}")
                if len(rows_with_mumma) == 0:
                    print(f"   ⚠️  Warning: No rows have Mumma sales > 0")
            except Exception as e:
                print(f"⚠️  Error checking Mumma data: {e}")
                print(f"✅ Mumma columns present (could not count rows with data)")
        
        # 5. Date gaps check
        # Filter out NaT/invalid dates first
        df_valid_dates = df[df["Date"].notna()].copy()
        if len(df_valid_dates) > 0:
            df_sorted = df_valid_dates.sort_values("Date")
            date_diffs = df_sorted["Date"].diff().dt.days
            gaps = date_diffs[date_diffs > 1]
            if len(gaps) > 0:
                print(f"⚠️  Found {len(gaps)} date gaps (missing dates)")
            else:
                print(f"✅ No date gaps (continuous date range)")
        else:
            print(f"⚠️  No valid dates found (all NaT)")
        
        # 6. Manual columns check
        manual_cols = ["Mumma Checked", "Mumma Cash €", "Shack Checked", "Shack Cash €"]
        present_manual = [c for c in manual_cols if c in df.columns]
        print(f"✅ Manual columns present: {len(present_manual)}/{len(manual_cols)}")
        if len(present_manual) < len(manual_cols):
            missing = set(manual_cols) - set(present_manual)
            print(f"   Missing: {missing}")
        
        print("=" * 60)
        
        # Summary
        has_issues = (
            len(duplicates) > 0 or
            len(missing_shack_cols) > 0 or
            len(missing_mumma_cols) > 0 or
            len(gaps) > 0
        )
        
        if has_issues:
            print("\n❌ Validation found issues. Review above.")
            return False
        else:
            print("\n✅ All validations passed!")
            return True
        
    except Exception as e:
        print(f"❌ Error during validation: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'wb' in locals():
            wb.close()
        app.quit()

if __name__ == "__main__":
    success = validate_daily_check()
    exit(0 if success else 1)

