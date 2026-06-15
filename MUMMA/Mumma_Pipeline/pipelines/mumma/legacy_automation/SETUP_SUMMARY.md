# MUMMA Automation System - Setup Summary

## 🎯 What Has Been Created

I've built a complete automation system for processing your Lightspeed CSV reports and generating comprehensive PDF reports. Here's what you now have:

### 📁 Core Files Created

1. **`mumma_report_automation.py`** - Main automation script (basic version)
2. **`mumma_report_automation_enhanced.py`** - Enhanced version with better error handling
3. **`email_config.py`** - Email configuration and credentials
4. **`requirements.txt`** - Python package dependencies
5. **`test_automation.py`** - Test script for the system
6. **`test_email.py`** - Test script for email functionality
7. **`run_automation.sh`** - Shell script to run automation manually
8. **`setup_cron.sh`** - Script to set up automatic scheduling
9. **`setup_automation.sh`** - Complete setup script
10. **`README.md`** - Comprehensive documentation

## 🚀 Quick Start

### 1. Complete Setup
```bash
./setup_automation.sh
```

### 2. Configure Email
Set your Outlook password:
```bash
export OUTLOOK_PASSWORD="your_password"
```
Or edit `email_config.py` and add your password.

### 3. Test the System
```bash
python3 test_automation.py
```

### 4. Test Email (Optional)
```bash
python3 test_email.py
```

### 5. Run Manually
```bash
./run_automation.sh
```

### 6. Set Up Automation (Every Monday at 7 AM)
```bash
./setup_cron.sh
```

## 📊 What the System Does

### Automated Workflow
1. **Finds Latest CSV** - Automatically locates the most recent Lightspeed report
2. **Processes Data** - Cleans and analyzes the CSV data
3. **Generates Charts** - Creates visual charts for:
   - Top 10 products by revenue
   - Top 10 products by quantity sold
   - Top 10 products by transaction count
   - Revenue distribution by category
4. **Creates PDF Report** - Combines all data into a professional report
5. **Sends Email** - Automatically emails the report with PDF attachment

### Report Content
- **Summary Statistics** - Total revenue, quantity, transactions, averages
- **Top Performers** - Ranked lists of best-selling products
- **Visual Charts** - Professional charts and graphs
- **Dashboard Integration** - Excel dashboard data (when accessible)
- **Professional Formatting** - Clean, business-ready PDF layout

## 📧 Email Configuration

### Current Settings
- **From**: dave@clove.solutions
- **To**: davevondavrosh@gmail.com
- **SMTP**: smtp.office365.com (Outlook)
- **Schedule**: Every Monday at 7:00 AM

### Email Credentials
You need to provide your Outlook password either:
- Set environment variable: `export OUTLOOK_PASSWORD="your_password"`
- Edit `email_config.py` and add your password

## 🔧 Troubleshooting

### Common Issues
1. **Excel File Access** - The dashboard Excel file appears to be encrypted. The system will work without it.
2. **Email Failures** - Check your Outlook credentials and SMTP settings
3. **File Permissions** - Ensure scripts are executable: `chmod +x *.sh`

### Logs
- **`mumma_automation.log`** - Main automation logs
- **`cron.log`** - Scheduled execution logs
- **Console output** - Real-time status information

## 📅 Scheduling

### Automatic Execution
The system is configured to run every Monday at 7:00 AM, giving you a 2.5-hour window to receive the report by 9:00 AM.

### Manual Execution
You can run the system manually at any time using:
```bash
./run_automation.sh
```

## 🎯 Next Steps

### Immediate Actions
1. **Set your email password** (see email configuration above)
2. **Test the system** with `python3 test_automation.py`
3. **Verify PDF generation** - check the Reports/ folder
4. **Test email functionality** with `python3 test_email.py`

### Production Setup
1. **Set up automatic scheduling** with `./setup_cron.sh`
2. **Monitor the first automated run** on Monday morning
3. **Verify email delivery** to davevondavrosh@gmail.com

### Customization
- **Modify charts** - Edit the `generate_charts()` method
- **Change report layout** - Modify the `generate_pdf_report()` method
- **Adjust schedule** - Edit the cron job or modify `setup_cron.sh`

## 🔒 Security Notes

- **Email credentials** are stored in `email_config.py` (keep this secure)
- **Environment variables** are preferred for passwords
- **File access** is limited to specified directories
- **Automation** runs with your user permissions

## 📞 Support

The system includes comprehensive logging and error handling. If you encounter issues:

1. **Check the logs** for detailed error information
2. **Verify file paths** in the configuration
3. **Test individual components** using the test scripts
4. **Ensure all dependencies** are properly installed

## 🎉 Success Indicators

You'll know the system is working when:
- ✅ PDF reports are generated in the Reports/ folder
- ✅ Charts are created with your data
- ✅ Emails are sent successfully
- ✅ Automation runs automatically on Monday mornings
- ✅ Reports arrive by 9:00 AM as requested

---

**The system is now ready to automate your MUMMA reporting process!** 🚀 