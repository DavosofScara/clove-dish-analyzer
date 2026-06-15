# 📊 VBA Dashboard Export Instructions

## 🎯 **What This Does**
The VBA script will export the DASH tab (A1:AA61) from `MUMMA MASTER 2425.xlsx` as a PDF file, which will then be automatically included in your email reports.

## 📋 **Step-by-Step Instructions**

### **Step 1: Open the Excel File**
1. Open `MUMMA MASTER 2425.xlsx` in Excel
2. Enter the password if prompted

### **Step 2: Open VBA Editor**
1. Press **Alt + F11** (Windows) or **Option + F11** (Mac)
2. This opens the Visual Basic Editor

### **Step 3: Insert Module**
1. In the VBA Editor, right-click on your workbook name
2. Select **Insert** → **Module**
3. A new module will appear

### **Step 4: Paste the VBA Code**
1. Copy the code from `export_dashboard_pdf.vba`
2. Paste it into the new module
3. Press **Ctrl + S** (Windows) or **Cmd + S** (Mac) to save

### **Step 5: Run the Script**
1. Go back to Excel (Alt + Q or Option + Q)
2. Press **Alt + F8** to open the Macro dialog
3. Select **ExportDashboardAsPDF** and click **Run**

### **Step 6: Check Output**
- The script will create `mumma_dashboard.pdf` in your MUMMA folder
- If PDF export fails, it will save as Excel and give you manual PDF instructions

## 🔧 **Alternative: Simple Export**
If the main script doesn't work, try **ExportDashboardSimple**:
1. Run **ExportDashboardSimple** instead
2. Follow the manual PDF export instructions
3. Save as `mumma_dashboard.pdf` in your MUMMA folder

## 📁 **File Locations**
- **Input**: `/Users/davidcraig/Dropbox (Personal)/Mumma/2425/MUMMA MASTER 2425.xlsx`
- **Output**: `/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/mumma_dashboard.pdf`

## ✅ **What Happens Next**
Once the dashboard PDF is created:
1. Your automation will automatically detect it
2. Both the main report AND dashboard will be attached to emails
3. Email subject will show "MUMMA Sales Report + Dashboard"

## 🚨 **Troubleshooting**
- **"DASH sheet not found"**: Make sure you're in the right Excel file
- **PDF export fails**: Use the manual export method provided
- **File access denied**: Check folder permissions

## 💡 **Pro Tip**
Run this VBA script once, and the dashboard PDF will be automatically included in all future reports! 