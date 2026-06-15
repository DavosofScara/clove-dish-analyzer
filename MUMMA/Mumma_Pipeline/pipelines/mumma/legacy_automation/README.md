# MUMMA Report Automation System

This system automatically processes Lightspeed CSV reports and generates comprehensive PDF reports with charts and dashboard data, then emails them to specified recipients.

## Features

- **Automated CSV Processing**: Automatically finds and processes the latest Lightspeed CSV report
- **Data Analysis**: Generates top 10 rankings by revenue, quantity, and transactions
- **Visual Charts**: Creates professional charts using matplotlib and seaborn
- **Dashboard Integration**: Extracts data from Excel dashboard and includes in reports
- **PDF Generation**: Creates professional PDF reports using ReportLab
- **Email Automation**: Sends reports via Outlook SMTP
- **Scheduling**: Runs automatically every Monday at 7:00 AM

## System Requirements

- macOS (tested on macOS 24.5.0)
- Python 3.8 or higher
- Outlook email account
- Access to specified file paths

## Installation

1. **Clone or download** the automation files to your desired directory

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up email credentials**:
   - Edit `config.py` and add your Outlook password
   - Or set environment variable: `export OUTLOOK_PASSWORD="your_password"`

4. **Make scripts executable**:
   ```bash
   chmod +x run_automation.sh
   chmod +x setup_cron.sh
   ```

## Configuration

### File Paths
Update the paths in `config.py` if your file locations differ:
- `csv_directory`: Where Lightspeed CSV files are saved
- `dashboard_file`: Path to the Excel dashboard file
- `output_directory`: Where generated reports are saved

### Email Settings
Configure your email settings in `config.py`:
- SMTP server: `smtp.office365.com` (Outlook)
- Sender: `dave@clove.solutions`
- Recipient: `davevondavrosh@gmail.com`

### Schedule
The system is configured to run every Monday at 7:00 AM. Adjust in `config.py` if needed.

## Usage

### Quick Test
Test the system without sending emails:
```bash
python3 test_automation.py
```

### Manual Run
Run the automation manually:
```bash
./run_automation.sh
```

### Automated Execution
Set up automatic execution:
```bash
./setup_cron.sh
```

## How It Works

1. **CSV Processing**: Finds the most recent CSV file and processes the data
2. **Data Analysis**: Calculates top performers and generates statistics
3. **Chart Generation**: Creates visual charts for revenue, quantity, and transactions
4. **Dashboard Integration**: Extracts data from Excel dashboard (DASH sheet, A1:AA61)
5. **PDF Creation**: Combines all data into a professional PDF report
6. **Email Delivery**: Sends the report via email with PDF attachment

## Report Content

Each generated report includes:
- **Summary Statistics**: Total revenue, quantity, transactions, averages
- **Top 10 Products**: Ranked by revenue, quantity sold, and transaction count
- **Visual Charts**: Bar charts and pie charts for data visualization
- **Dashboard Data**: Integrated Excel dashboard information
- **Professional Formatting**: Clean, business-ready PDF layout

## File Structure

```
MUMMA_Automation/
├── mumma_report_automation.py    # Main automation script
├── config.py                     # Configuration file
├── requirements.txt              # Python dependencies
├── run_automation.sh            # Launcher script
├── setup_cron.sh                # Cron job setup
├── test_automation.py           # Test script
├── README.md                    # This file
└── Reports/                     # Generated reports (created automatically)
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed
   ```bash
   pip install -r requirements.txt
   ```

2. **File Not Found**: Check file paths in `config.py`

3. **Email Failures**: Verify Outlook credentials and SMTP settings

4. **Permission Errors**: Make scripts executable
   ```bash
   chmod +x *.sh
   ```

### Logs

The system generates detailed logs:
- `mumma_automation.log`: Main automation logs
- `cron.log`: Scheduled execution logs (if using cron)

## Security Notes

- **Email Credentials**: Store passwords securely, preferably in environment variables
- **File Access**: Ensure the system has appropriate access to required directories
- **Automation**: The system runs automatically - ensure it's secure and tested

## Customization

### Adding New Charts
Modify the `generate_charts()` method in `mumma_report_automation.py`

### Changing Report Layout
Edit the `generate_pdf_report()` method to modify PDF structure

### Adding New Data Sources
Extend the system by adding new data processing methods

## Support

For issues or questions:
1. Check the logs for error details
2. Verify all file paths and permissions
3. Test individual components using `test_automation.py`
4. Ensure all dependencies are properly installed

## License

This automation system is created for MUMMA business use. Please ensure compliance with your organization's policies and data handling requirements. 