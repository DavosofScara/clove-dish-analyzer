#!/usr/bin/env python3
"""
Script to read exported dashboard CSV and integrate with MUMMA automation
"""

import pandas as pd
import os
import logging

def read_dashboard_csv(csv_path):
    """Read the exported dashboard CSV and convert to the expected format"""
    
    if not os.path.exists(csv_path):
        logging.warning(f"Dashboard CSV not found: {csv_path}")
        return None
    
    try:
        # Read the CSV file
        df = pd.read_csv(csv_path, header=None)
        
        # Convert to list of lists (expected format)
        dashboard_data = df.values.tolist()
        
        # Ensure we have 61 rows and 26 columns
        if len(dashboard_data) < 61:
            # Pad with empty rows
            while len(dashboard_data) < 61:
                dashboard_data.append([''] * 26)
        elif len(dashboard_data) > 61:
            # Truncate to 61 rows
            dashboard_data = dashboard_data[:61]
        
        # Ensure each row has 26 columns
        for i, row in enumerate(dashboard_data):
            if len(row) < 26:
                # Pad with empty columns
                dashboard_data[i] = row + [''] * (26 - len(row))
            elif len(row) > 26:
                # Truncate to 26 columns
                dashboard_data[i] = row[:26]
        
        logging.info(f"Successfully loaded dashboard data: {len(dashboard_data)} rows x {len(dashboard_data[0])} columns")
        return dashboard_data
        
    except Exception as e:
        logging.error(f"Error reading dashboard CSV: {e}")
        return None

def update_automation_with_csv():
    """Update the automation to use the exported CSV instead of sample data"""
    
    csv_path = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/mumma_dashboard_export.csv"
    
    if os.path.exists(csv_path):
        print(f"✅ Found dashboard CSV: {csv_path}")
        dashboard_data = read_dashboard_csv(csv_path)
        
        if dashboard_data:
            print(f"✅ Dashboard data loaded: {len(dashboard_data)} rows x {len(dashboard_data[0])} columns")
            print("📊 First few rows:")
            for i, row in enumerate(dashboard_data[:5]):
                print(f"Row {i+1}: {row[:6]}...")  # Show first 6 columns
            
            return dashboard_data
        else:
            print("❌ Failed to load dashboard data from CSV")
            return None
    else:
        print(f"❌ Dashboard CSV not found: {csv_path}")
        print("💡 Run the VBA script in Excel first to export the data")
        return None

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    print("🔍 Checking for exported dashboard CSV...")
    result = update_automation_with_csv()
    
    if result:
        print("\n🎉 Dashboard CSV integration ready!")
        print("💡 Now run your automation and it will use the real dashboard data")
    else:
        print("\n💡 To get real dashboard data:")
        print("1. Open MUMMA MASTER 2425.xlsx in Excel")
        print("2. Press Alt+F11 to open VBA editor")
        print("3. Insert → Module")
        print("4. Paste the VBA code from export_dashboard.vba")
        print("5. Run ExportDashboardDataSimple()")
        print("6. Paste into new Excel file and save as CSV")
        print("7. Place CSV in your MUMMA folder") 