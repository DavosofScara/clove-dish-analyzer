#!/usr/bin/env python3
"""
Update MUMMA_MASTER_2526.xlsx with fresh daily sales data.

IMPORTANT SAFETY:
- ONLY modifies the `daily_sales` sheet
- Does NOT touch: pivot, daily_check, dashboard, DM, lists, staff_db, staff_dec, xl_Sales sheets
- Preserves all named tables and structures
- Creates backup before making any changes

Steps:
- Read processed daily sales from data/mumma/processed/daily_sales_summary.xlsx
- Update the `daily_sales` sheet (append new rows or replace all with --replace-all flag)
- Preserves DailySalesTable structure if it exists
- Pivot tables automatically refresh when data changes (they reference DailySalesTable)

Uses xlwings instead of openpyxl to preserve slicers and other Excel features.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import xlwings as xw  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "mumma" / "processed"
DAILY_SUMMARY_PATH = PROCESSED_DIR / "daily_sales_summary.xlsx"

# Shared Dropbox workbook
MUMMA_MASTER_PATH = Path(
    "/Users/davidcraig/Dropbox (Personal)/Mumma/2526/MUMMA_MASTER_2526.xlsm"
)


def update_excel_dashboard_with_pivot(
    daily_summary_path: Path = DAILY_SUMMARY_PATH,
    master_path: Path = MUMMA_MASTER_PATH,
    replace_all: bool = False,
) -> None:
    """Update `daily_sales` sheet in the Mumma master workbook using xlwings.
    
    SAFETY: Only modifies daily_sales sheet. All other sheets, tables, and structures are preserved.
    """
    if not daily_summary_path.exists():
        raise FileNotFoundError(f"Daily summary not found at {daily_summary_path}")
    
    # Ensure directory exists
    master_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create backup directory
    backup_dir = master_path.parent / "back_ups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Create numbered backup FIRST before doing anything else
    backup_path = None
    if master_path.exists():
        # Find the highest backup number in the back_ups folder
        # Search for both .xlsx and .xlsm extensions (backups may have either)
        existing_backups_xlsx = list(backup_dir.glob(f"{master_path.stem}_backup_*.xlsx"))
        existing_backups_xlsm = list(backup_dir.glob(f"{master_path.stem}_backup_*.xlsm"))
        existing_backups = existing_backups_xlsx + existing_backups_xlsm
        
        if existing_backups:
            backup_numbers = []
            for backup in existing_backups:
                try:
                    num_str = backup.stem.split("_backup_")[-1]
                    backup_numbers.append(int(num_str))
                except (ValueError, IndexError):
                    pass
            
            next_backup_num = max(backup_numbers) + 1 if backup_numbers else 1
        else:
            next_backup_num = 1
        
        backup_path = backup_dir / f"{master_path.stem}_backup_{next_backup_num}{master_path.suffix}"
        shutil.copy2(master_path, backup_path)
        print(f"📦 Created backup: {backup_path.name} (in back_ups folder)")
    else:
        print(f"📄 File doesn't exist yet - will create new file: {master_path.name}")
    
    create_new_file = not master_path.exists()

    # Load daily summary
    daily_df = pd.read_excel(daily_summary_path)
    if "Date" not in daily_df.columns:
        raise ValueError("Expected a 'Date' column in daily_sales_summary.xlsx")

    # Normalize column names we rely on
    cols = {c: c for c in daily_df.columns}
    for c in daily_df.columns:
        lc = str(c).strip().lower()
        if lc == "total" and "Total Sales" not in cols.values():
            cols[c] = "Total Sales"
    daily_df = daily_df.rename(columns=cols)

    if "Total Sales" not in daily_df.columns:
        for candidate in ("Total", "Sales"):
            if candidate in daily_df.columns:
                daily_df = daily_df.rename(columns={candidate: "Total Sales"})
                break
    if "Total Sales" not in daily_df.columns:
        raise ValueError("Could not find a 'Total Sales' column in daily sales summary.")

    # Ensure Date is datetime.date
    daily_df["Date"] = pd.to_datetime(daily_df["Date"]).dt.date

    # Build pivot-like summary: Date x Location -> Total Sales
    if "Location" in daily_df.columns:
        pivot = (
            daily_df.pivot_table(
                index="Date",
                columns="Location",
                values="Total Sales",
                aggfunc="sum",
                fill_value=0.0,
            )
            .sort_index()
            .reset_index()
        )
        
        # Ensure both Mumma and Shack columns exist (pivot_table only creates columns for locations that have data)
        if "Mumma" not in pivot.columns:
            pivot["Mumma"] = 0.0
        if "Shack" not in pivot.columns:
            pivot["Shack"] = 0.0

        # Food by Date x Location
        food_p = (
            daily_df.pivot_table(
                index="Date",
                columns="Location",
                values="Food Sales",
                aggfunc="sum",
                fill_value=0.0,
            )
            .sort_index()
            .reset_index()
        )
        # Ensure both location columns exist (pivot_table only creates columns for locations that have data)
        if "Mumma" not in food_p.columns:
            food_p["Mumma"] = 0.0
        if "Shack" not in food_p.columns:
            food_p["Shack"] = 0.0
        # Rename e.g. Mumma -> "Mumma Food (€)"
        food_rename: dict[str, str] = {}
        for col in food_p.columns:
            if col == "Date":
                continue
            food_rename[col] = f"{col} Food (€)"
        food_p = food_p.rename(columns=food_rename)

        # Drink by Date x Location
        drink_p = (
            daily_df.pivot_table(
                index="Date",
                columns="Location",
                values="Drink Sales",
                aggfunc="sum",
                fill_value=0.0,
            )
            .sort_index()
            .reset_index()
        )
        # Ensure both location columns exist (pivot_table only creates columns for locations that have data)
        if "Mumma" not in drink_p.columns:
            drink_p["Mumma"] = 0.0
        if "Shack" not in drink_p.columns:
            drink_p["Shack"] = 0.0
        drink_rename: dict[str, str] = {}
        for col in drink_p.columns:
            if col == "Date":
                continue
            drink_rename[col] = f"{col} Drink (€)"
        drink_p = drink_p.rename(columns=drink_rename)

        # Merge totals (pivot) with food and drink metrics
        metrics_wide = pivot.merge(food_p, on="Date", how="outer").merge(
            drink_p, on="Date", how="outer"
        )
        # Fill any NaN values with 0.0 after merge
        metrics_wide = metrics_wide.fillna(0.0)
    else:
        # Single-location case - still provide Food/Drink columns but without location split
        pivot = (
            daily_df.groupby("Date")["Total Sales"]
            .sum()
            .reset_index()
        )
        metrics_wide = pivot.copy()
        if "Food Sales" in daily_df.columns:
            food_tot = (
                daily_df.groupby("Date")["Food Sales"]
                .sum()
                .reset_index()
                .rename(columns={"Food Sales": "Food (€)"})
            )
            metrics_wide = metrics_wide.merge(food_tot, on="Date", how="left")
        if "Drink Sales" in daily_df.columns:
            drink_tot = (
                daily_df.groupby("Date")["Drink Sales"]
                .sum()
                .reset_index()
                .rename(columns={"Drink Sales": "Drink (€)"})
            )
            metrics_wide = metrics_wide.merge(drink_tot, on="Date", how="left")

    # Track if we add any new data
    added_new_data = False

    # Open Excel application (invisible mode)
    # macOS requires both Accessibility AND Automation permissions for xlwings
    # Error -1743 means "user declined permission" - Excel is blocking automation
    import time
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Try to create Excel app instance
            app = xw.App(visible=False, add_book=False)
            # Small delay to let Excel initialize
            time.sleep(0.5)
            
            # Try to set display_alerts - this is where permission errors often occur
            try:
                app.display_alerts = False
            except Exception as alert_error:
                error_code = getattr(alert_error, 'errornum', None)
                if error_code == -1743 or "declined permission" in str(alert_error).lower():
                    print(f"⚠️  Excel automation permission denied (attempt {attempt + 1}/{max_retries})")
                    print("   This usually means:")
                    print("   1. Excel needs Automation permissions")
                    print("   2. Excel has a modal dialog open (close it)")
                    print("   3. Excel is blocking automation for security")
                    print("   Fix: System Settings → Privacy & Security → Automation")
                    print("        → Enable Terminal/Python for Microsoft Excel")
                    if attempt < max_retries - 1:
                        print(f"   Retrying in {retry_delay} seconds...")
                        app.quit()
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise
                else:
                    raise
            
            # Success - break out of retry loop
            break
            
        except Exception as e:
            error_msg = str(e)
            error_code = getattr(e, 'errornum', None)
            
            # Check for specific permission errors
            if error_code == -1743 or "declined permission" in error_msg.lower():
                if attempt < max_retries - 1:
                    print(f"⚠️  Permission error (attempt {attempt + 1}/{max_retries}), retrying...")
                    time.sleep(retry_delay)
                    continue
                else:
                    print("❌ Excel automation permission denied after retries")
                    print("   Required permissions:")
                    print("   1. System Settings → Privacy & Security → Accessibility")
                    print("      → Enable Terminal (or Python)")
                    print("   2. System Settings → Privacy & Security → Automation")
                    print("      → Enable Terminal/Python for Microsoft Excel")
                    print("   3. Make sure Excel is not open with a modal dialog")
                    print("   4. Try closing and reopening Excel")
                    raise
            elif "System Events" in error_msg or "terminology" in error_msg.lower():
                print("⚠️  xlwings requires Accessibility permissions.")
                print("   Please grant Terminal/iTerm Accessibility access:")
                print("   System Settings → Privacy & Security → Accessibility")
                print("   Add Terminal (or iTerm) and check the box.")
                print("   Then restart Terminal and try again.")
                raise
            else:
                # Other errors - just raise them
                raise
    
    try:
        # Open existing workbook (never create new - file should already exist)
        if not master_path.exists():
            raise FileNotFoundError(
                f"Excel file does not exist at {master_path}\n"
                "This script only updates existing files. Please create the file manually first."
            )
        wb = app.books.open(str(master_path))
        print(f"📄 Opened existing workbook: {master_path.name}")
        print(f"   Sheets in workbook: {[s.name for s in wb.sheets]}")

        # ----- Sheet 1: daily_sales - APPEND or REPLACE data -----
        if "daily_sales" in [s.name for s in wb.sheets]:
            ws_data = wb.sheets["daily_sales"]
            
            # If replace_all is True, replace all data in daily_sales sheet
            # IMPORTANT: We preserve the Excel Table structure (DailySalesTable) and all other sheets
            # SAFETY: We do NOT delete the table, we overwrite data cells to preserve structure
            if replace_all:
                print("🔄 Replacing all data in daily_sales sheet (replace_all=True)")
                print("   ✅ SAFETY: Preserving Excel Table structure (DailySalesTable)")
                print("   ✅ SAFETY: All other sheets (pivot, daily_check, dashboard, DM) are untouched")
                # Clear existing data first, then write new data
                try:
                    # Clear entire used range to remove old data
                    used_range = ws_data.used_range
                    if used_range:
                        ws_data.range(used_range.address).clear_contents()
                        print(f"   🗑️  Cleared existing data range: {used_range.address}")
                except Exception as e:
                    print(f"   ⚠️  Could not clear range automatically ({e}), will overwrite")
                
                existing_df = pd.DataFrame()
                start_row = 1  # Start from row 1 to include headers
                new_data_df = daily_df.copy()
                rows_to_update = pd.DataFrame()
            else:
                # Read existing data to check for duplicates
                # Try to read from an Excel Table if it exists, otherwise read from used range
                existing_df = pd.DataFrame()
                table_found = False
                table_header_row: int | None = None
                try:
                    # First, try to find if there's any Excel Table on this sheet
                    try:
                        list_objects = ws_data.api.ListObjects
                        if list_objects and list_objects.Count > 0:
                            # Use the first table on the sheet (assumed to be the daily sales table)
                            table = list_objects.Item(1)
                            table_range = table.Range
                            table_header_row = int(table_range.Row)
                            existing_data = ws_data.range(table_range.Address).value
                            table_found = True
                            print(f"📋 Found Excel Table '{table.Name}' on daily_sales sheet - reading from table (header row {table_header_row})")
                    except Exception:
                        # No table found, read from used range
                        pass
                    
                    if not table_found:
                        # Fall back to used range
                        used_range = ws_data.used_range
                        if used_range and used_range.last_cell.row > 1:
                            existing_data = ws_data.range(f"A1:{used_range.last_cell.address}").value
                        else:
                            existing_data = None
                    
                    if existing_data:
                        # xlwings returns list of lists for multi-row ranges
                        if isinstance(existing_data, list) and len(existing_data) > 0:
                            # Check if first element is a list (multiple rows)
                            if isinstance(existing_data[0], list):
                                headers = existing_data[0]
                                existing_rows = existing_data[1:] if len(existing_data) > 1 else []
                                if existing_rows:
                                    existing_df = pd.DataFrame(existing_rows, columns=headers)
                                    # Drop completely empty rows (Excel "used range" can include empty trailing rows)
                                    existing_df = existing_df.dropna(how="all")
                                    # Normalize Date column
                                    if "Date" in existing_df.columns:
                                        existing_df["Date"] = pd.to_datetime(existing_df["Date"], errors='coerce').dt.date
                                    # Normalize Location column if it exists
                                    if "Location" in existing_df.columns:
                                        existing_df["Location"] = existing_df["Location"].astype(str).str.strip()
                                    print(f"📊 Read {len(existing_df)} existing row(s) from daily_sales sheet")
                                else:
                                    print("📊 No data rows found (only headers)")
                            else:
                                # Single row case - just headers
                                print("📊 Only header row found")
                except Exception as e:
                    print(f"⚠️  Could not read existing data: {e}")
                    import traceback
                    print(traceback.format_exc())
                    existing_df = pd.DataFrame()
                
                # Find duplicates: compare Date + Location (if Location exists) or just Date
                # Use merge with indicator for reliable duplicate detection
                rows_to_update = pd.DataFrame()  # Initialize empty DataFrame
                if not existing_df.empty and "Date" in daily_df.columns:
                    # Normalize dates to ensure comparison works
                    daily_df["Date"] = pd.to_datetime(daily_df["Date"]).dt.date
                    existing_df["Date"] = pd.to_datetime(existing_df["Date"]).dt.date
                    
                    # Normalize Location if it exists (strip whitespace, handle case)
                    if "Location" in daily_df.columns and "Location" in existing_df.columns:
                        daily_df["Location"] = daily_df["Location"].astype(str).str.strip()
                        existing_df["Location"] = existing_df["Location"].astype(str).str.strip()
                        
                        # Use merge to find duplicates based on Date + Location
                        # IMPORTANT: Only mark as "needs update" if values actually differ
                        merge_cols = ["Date", "Location"]
                        merged = daily_df.merge(
                            existing_df[merge_cols + ["Total Sales"]],  # Include Total Sales for comparison
                            on=merge_cols,
                            how="left",
                            indicator=True,
                            suffixes=("", "_existing"),
                        )
                        # Separate new rows (don't exist) and rows to update (do exist AND values differ)
                        new_data_df = daily_df[merged["_merge"] == "left_only"].copy()
                        
                        # For rows that exist, check if values differ significantly
                        both_mask = merged["_merge"] == "both"
                        rows_that_exist = daily_df[both_mask].copy()
                        
                        if len(rows_that_exist) > 0:
                            # Compare values - only update if Total Sales differs by more than 0.01
                            existing_totals = merged.loc[both_mask, "Total Sales_existing"].values
                            new_totals = rows_that_exist["Total Sales"].values
                            value_diffs = abs(new_totals - existing_totals)
                            needs_update_mask = value_diffs > 0.01
                            
                            rows_to_update = rows_that_exist[needs_update_mask].copy()
                            
                            # Count how many need updating vs are already correct
                            already_correct = (~needs_update_mask).sum()
                            if already_correct > 0:
                                print(f"   ℹ️  {already_correct} existing row(s) already have correct values (no update needed)")
                        else:
                            rows_to_update = pd.DataFrame()
                    else:
                        # Just compare on Date
                        merged = daily_df.merge(
                            existing_df[["Date"]],
                            on="Date",
                            how="left",
                            indicator=True,
                        )
                        new_data_df = daily_df[merged["_merge"] == "left_only"].copy()
                        rows_to_update = daily_df[merged["_merge"] == "both"].copy()
                    
                    num_to_update = len(rows_to_update)
                    if num_to_update > 0:
                        print(
                            f"📝 Found {num_to_update} existing row(s) to update in daily_sales "
                            "(Date+Location combination exists - will be updated)"
                        )
                    if len(new_data_df) > 0:
                        print(f"📊 Found {len(new_data_df)} new row(s) to append to daily_sales")
                else:
                    new_data_df = daily_df.copy()
                    rows_to_update = pd.DataFrame()
            
            # Find where to append - base it on the number of rows that actually have a Date
            # (Only if not replacing all)
            if not replace_all:
                if not existing_df.empty:
                    if "Date" in existing_df.columns:
                        # Count only rows where Date is present; ignore trailing formula/blank rows
                        valid_mask = existing_df["Date"].notna()
                        num_data_rows = valid_mask.sum()
                    else:
                        num_data_rows = len(existing_df)
                    # If we have a table, anchor on its header row; otherwise assume header at row 1
                    if table_found and table_header_row is not None:
                        # Data start at header_row + 1; append after last data row
                        start_row = int(table_header_row) + int(num_data_rows) + 1
                    else:
                        # Header is row 1, data start at row 2; append after last data row
                        start_row = int(num_data_rows) + 2
                    print(f"📍 Existing data rows (with Date): {num_data_rows} (table_header_row={table_header_row}) -> appending from row {start_row}")
                else:
                    # No existing data, start at row 1 (header row)
                    start_row = 1
                    print("📍 No existing data in daily_sales - starting at row 1")
        else:
            ws_data = wb.sheets.add("daily_sales")
            new_data_df = daily_df.copy()
            rows_to_update = pd.DataFrame()
            start_row = 1  # Start with header

        # Handle updates and new data
        # NOTE: We no longer update existing rows - only append new ones
        # This prevents accidentally breaking slicers/pivot tables
        # If rows need updating, they should be manually corrected in Excel
        if len(rows_to_update) > 0 and not replace_all:
            print(f"⚠️  Found {len(rows_to_update)} existing row(s) with Date+Location that already exist")
            print(f"   Skipping these rows to avoid duplicates (they already exist in Excel)")
            print(f"   If these rows need updating, please update them manually in Excel")
            # Clear rows_to_update - we'll only append new rows
            rows_to_update = pd.DataFrame()
        
        # Write data (either new, updated, or replacement)
        # Track the actual number of data columns written (excluding timestamp)
        num_data_cols_written = len(new_data_df.columns) if len(new_data_df) > 0 else len(daily_df.columns)
        if len(new_data_df) > 0:
            # For replace_all: write all data including headers, overwriting existing
            # For append mode: append to table or range
            if replace_all:
                # Replace mode: Write all data starting from row 1 (headers + data)
                # CRITICAL: Ensure DataFrame has exact columns matching Excel structure
                print(f"   📝 Preparing to write {len(new_data_df)} rows...")
                print(f"   📋 Columns available: {list(new_data_df.columns)}")
                
                # Ensure we have the correct column order matching the original structure
                expected_cols = ["Date", "Location", "Total Sales", "10% Sales", "20% Sales", "Food Sales", "Drink Sales"]
                if all(c in new_data_df.columns for c in expected_cols):
                    data_to_write = new_data_df[expected_cols].copy()
                    print(f"   ✅ Using expected column order: {list(data_to_write.columns)}")
                else:
                    # Missing some columns - use what we have but warn
                    missing = set(expected_cols) - set(new_data_df.columns)
                    print(f"   ⚠️  Missing columns: {missing}, using available columns")
                    data_to_write = new_data_df.copy()
                
                # Convert Date to datetime if needed (xlwings handles this, but be explicit)
                if "Date" in data_to_write.columns:
                    data_to_write["Date"] = pd.to_datetime(data_to_write["Date"])
                
                num_data_cols_written = len(data_to_write.columns)
                
                try:
                    # For replace_all, we need to completely replace the data
                    # This means clearing old data (including headers if structure changed) and writing fresh
                    used_range = ws_data.used_range
                    if used_range:
                        # Clear the entire used range (headers + data) to ensure clean slate
                        # This is necessary because we're replacing ALL data with correct data from daily_summary
                        ws_data.range(used_range.address).clear_contents()
                        print(f"   🗑️  Cleared existing data (including headers) in range: {used_range.address}")
                    
                    # Write DataFrame explicitly to avoid index column issues
                    # Reset index to ensure clean DataFrame
                    data_to_write = data_to_write.reset_index(drop=True)
                    
                    # Write headers first (row 1)
                    ws_data.range("A1").value = [list(data_to_write.columns)]
                    
                    # Write data starting at row 2 (convert DataFrame to list of lists, no index)
                    if len(data_to_write) > 0:
                        data_values = data_to_write.values.tolist()
                        ws_data.range("A2").value = data_values
                    
                    table_found = True
                    print(f"✅ Successfully wrote {len(data_to_write)} rows to daily_sales sheet")
                    print(f"   📋 Headers written (row 1, columns A-{chr(64+len(data_to_write.columns))}): {list(data_to_write.columns)}")
                    print(f"   📊 Data rows written (rows 2-{len(data_to_write)+1}): {len(data_to_write)} rows")
                    print(f"   ℹ️  If DailySalesTable exists, Excel will automatically update it to match new structure")
                    print(f"   ℹ️  Only daily_sales sheet modified - all other sheets untouched")
                    
                except Exception as e:
                    print(f"❌ Error writing data: {e}")
                    import traceback
                    traceback.print_exc()
                    raise
            else:
                # Append mode: Check if there's an Excel Table we should append to
                table_found = False
                try:
                    table = ws_data.api.ListObjects("DailySalesTable")
                    if table:
                        # Append rows to table - Excel will auto-expand the table
                        # Convert DataFrame to list of lists (one list per row)
                        for idx, row in new_data_df.iterrows():
                            new_row = table.ListRows.Add()
                            # Write each cell in the row
                            for col_idx, col_name in enumerate(new_data_df.columns):
                                new_row.Range(1, col_idx + 1).value = row[col_name]
                        table_found = True
                        print(f"✅ Appended {len(new_data_df)} new row(s) to DailySalesTable")
                except Exception as e:
                    # No table found or error accessing table, use regular range append
                    if "DailySalesTable" in str(e) or "ListObjects" in str(e):
                        # Table doesn't exist, that's fine - use regular append
                        pass
                    else:
                        print(f"⚠️  Error appending to table: {e}")
                
                if not table_found:
                    # Write header if starting new sheet
                    if start_row == 1:
                        ws_data.range(f"A{start_row}").value = new_data_df
                    else:
                        # Append data without header
                        ws_data.range(f"A{start_row}").value = new_data_df.values
                    print(f"✅ Appended {len(new_data_df)} new row(s) to daily_sales (range {start_row})")
            
            added_new_data = True
        elif len(rows_to_update) == 0:
            print("ℹ️  No new or updated data for daily_sales (all rows already exist and match)")

        # Update timestamp in the column after the last data column
        # Safely determine timestamp column location
        try:
            # Get current headers to find last column
            current_headers = ws_data.range("A1").expand("right").value
            if isinstance(current_headers, list):
                num_cols = len(current_headers)
            else:
                # Fallback - use data columns
                num_cols = num_data_cols_written if num_data_cols_written > 0 else len(daily_df.columns)
        except Exception:
            # Fallback - use data columns
            num_cols = num_data_cols_written if num_data_cols_written > 0 else len(daily_df.columns)
        
        # Convert column number to letter (1-based: 1=A, 2=B, etc.)
        def col_num_to_letter(n):
            result = ""
            while n > 0:
                n -= 1
                result = chr(65 + (n % 26)) + result
                n //= 26
            return result
        
        timestamp_col = col_num_to_letter(num_cols + 1)
        timestamp_header = f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            ws_data.range(f"{timestamp_col}1").value = timestamp_header
            print(f"   📅 Timestamp written to column {timestamp_col}1: {timestamp_header}")
        except Exception as e:
            print(f"   ⚠️  Could not write timestamp: {e}")
            print(f"   (This is non-critical - data updates completed successfully)")

        # ----- Only update daily_sales - do NOT touch pivot, daily_check, dashboard, or DM sheets -----
        # All other sheet logic removed - only daily_sales is updated

        # Save workbook (we now always save because helper sheets or data may have changed)
        wb.save(str(master_path))
        print(f"✅ Successfully saved workbook to {master_path}")

        wb.close()
        
    except Exception as e:
        error_msg = f"❌ Error updating workbook: {e}"
        print(error_msg)
        print(f"   Backup available: {backup_path.name if backup_path else 'N/A'}")
        # Close Excel before raising - prevents hanging
        try:
            if 'wb' in locals() and wb is not None:
                wb.close()
        except:
            pass
        raise
    finally:
        # CRITICAL: Always quit Excel, even on errors, to prevent hanging
        try:
            app.quit()
            time.sleep(0.5)  # Give Excel time to close
        except:
            # If quit fails, force kill Excel processes (prevents hanging)
            try:
                subprocess.run(["pkill", "-f", "Microsoft Excel"], check=False, timeout=2)
            except:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update MUMMA_MASTER_2526.xlsx with daily sales and pivot summary."
    )
    parser.add_argument(
        "--daily-summary",
        type=Path,
        default=DAILY_SUMMARY_PATH,
        help="Path to daily_sales_summary.xlsx",
    )
    parser.add_argument(
        "--master",
        type=Path,
        default=MUMMA_MASTER_PATH,
        help="Path to MUMMA_MASTER_2526.xlsx",
    )
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help="Replace all data in daily_sales sheet instead of appending (use for rebuilding)",
    )
    args = parser.parse_args()

    update_excel_dashboard_with_pivot(args.daily_summary, args.master, replace_all=args.replace_all)
    print(f"✅ Updated Mumma master workbook at {args.master}")


if __name__ == "__main__":
    main()
