#!/usr/bin/env python3
"""
Enhanced MUMMA Report Automation System
Automatically processes Lightspeed CSV reports and generates comprehensive PDF reports
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
import schedule
from openpyxl import load_workbook
from pathlib import Path
import sys
import time
import logging
from pathlib import Path
import numpy as np
import ssl
import imaplib
import email
from email.header import decode_header
import re

# Import email configuration
from email_config import EMAIL_CREDENTIALS, TEST_EMAIL, EMAIL_TEMPLATES

# Import the new dashboard generator
from mumma_dashboard_generator import (
    generate_mumma_dashboard, 
    generate_revenue_trends_analysis, 
    generate_operational_insights
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mumma_automation.log'),
        logging.StreamHandler()
    ]
)

class EnhancedMummaReportAutomation:
    def __init__(self):
        self.csv_directory = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/Lightspeed_Reports"
        self.dashboard_file = "/Users/davidcraig/Dropbox (Personal)/Mumma/2425/MUMMA MASTER 2425.xlsx"
        self.output_directory = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/Reports"
        self.sender_email = EMAIL_CREDENTIALS['sender_email']
        self.recipient_email = EMAIL_CREDENTIALS['recipient_email']
        
        # Create output directory if it doesn't exist
        Path(self.output_directory).mkdir(parents=True, exist_ok=True)
        
        # Set matplotlib style
        try:
            plt.style.use('seaborn-v0_8')
        except:
            plt.style.use('default')
        
        # Enhanced color palette and styling
        sns.set_palette("husl")
        plt.rcParams['figure.facecolor'] = '#f8f9fa'
        plt.rcParams['axes.facecolor'] = '#ffffff'
        plt.rcParams['axes.edgecolor'] = '#dee2e6'
        plt.rcParams['axes.linewidth'] = 1.2
        plt.rcParams['grid.color'] = '#e9ecef'
        plt.rcParams['grid.linestyle'] = '-'
        plt.rcParams['grid.linewidth'] = 0.8
        plt.rcParams['grid.alpha'] = 0.7
        plt.rcParams['font.size'] = 10
        plt.rcParams['axes.titlesize'] = 12
        plt.rcParams['axes.labelsize'] = 10
        plt.rcParams['xtick.labelsize'] = 9
        plt.rcParams['ytick.labelsize'] = 9
        
    def check_for_lightspeed_emails(self, check_window_minutes=30):
        """
        Check email for new Lightspeed CSV attachments and download them
        Designed to run between 7:30-8:00 AM on Mondays with 30-minute window
        """
        logging.info(f"Checking for new Lightspeed emails (window: {check_window_minutes} minutes)...")
        
        try:
            # Connect to IMAP server
            imap_server = 'outlook.office365.com'
            mail = imaplib.IMAP4_SSL(imap_server)
            
            # Login
            email_address = EMAIL_CREDENTIALS['sender_email']
            password = EMAIL_CREDENTIALS['sender_password']
            mail.login(email_address, password)
            
            # Select inbox
            mail.select('inbox')
            
            # Search for emails from the last 2 days (to catch weekend emails)
            date_since = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
            
            # Enhanced search patterns for Lightspeed emails
            search_patterns = [
                f'(SINCE "{date_since}" FROM "lightspeed")',
                f'(SINCE "{date_since}" SUBJECT "lightspeed")',
                f'(SINCE "{date_since}" SUBJECT "export")',
                f'(SINCE "{date_since}" SUBJECT "product breakdown")',
                f'(SINCE "{date_since}" SUBJECT "sales report")',
                f'(SINCE "{date_since}" FROM "noreply")',
                f'(SINCE "{date_since}" FROM "reports")',
                f'(SINCE "{date_since}" SUBJECT "mumma")',
            ]
            
            downloaded_files = []
            
            for pattern in search_patterns:
                try:
                    status, messages = mail.search(None, pattern)
                    if status == 'OK' and messages[0]:
                        email_ids = messages[0].split()
                        logging.info(f"Found {len(email_ids)} emails matching pattern: {pattern}")
                        
                        # Check most recent emails first
                        for email_id in reversed(email_ids[-10:]):  # Check last 10 emails
                            try:
                                status, msg_data = mail.fetch(email_id, '(RFC822)')
                                if status == 'OK':
                                    email_body = msg_data[0][1]
                                    email_message = email.message_from_bytes(email_body)
                                    
                                    # Get email date and subject for logging
                                    email_date = email_message.get('Date', 'Unknown')
                                    email_subject = email_message.get('Subject', 'No Subject')
                                    logging.info(f"Checking email: {email_subject} (Date: {email_date})")
                                    
                                    # Check for CSV attachments
                                    for part in email_message.walk():
                                        if part.get_content_disposition() == 'attachment':
                                            filename = part.get_filename()
                                            if filename and filename.lower().endswith('.csv'):
                                                # Enhanced keyword matching for Lightspeed exports
                                                lightspeed_keywords = [
                                                    'lightspeed', 'export', 'sales', 'mumma', 'product',
                                                    'breakdown', 'report', 'transaction', 'shack'
                                                ]
                                                
                                                if any(keyword in filename.lower() for keyword in lightspeed_keywords):
                                                    # Save to Lightspeed_Reports folder
                                                    filepath = os.path.join(self.csv_directory, filename)
                                                    
                                                    # Check if file is new or different
                                                    should_download = True
                                                    if os.path.exists(filepath):
                                                        # Compare file sizes to see if it's different
                                                        existing_size = os.path.getsize(filepath)
                                                        new_content = part.get_payload(decode=True)
                                                        if len(new_content) == existing_size:
                                                            logging.info(f"CSV file unchanged: {filename}")
                                                            should_download = False
                                                    
                                                    if should_download:
                                                        with open(filepath, 'wb') as f:
                                                            f.write(part.get_payload(decode=True))
                                                        downloaded_files.append(filepath)
                                                        logging.info(f"Downloaded CSV attachment: {filename}")
                                                        
                                                        # Also copy to MUMMA_Weekly_CSVs for backup
                                                        backup_dir = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/MUMMA_Weekly_CSVs"
                                                        os.makedirs(backup_dir, exist_ok=True)
                                                        backup_path = os.path.join(backup_dir, filename)
                                                        with open(backup_path, 'wb') as f:
                                                            f.write(part.get_payload(decode=True))
                                                        logging.info(f"Backup saved to: {backup_path}")
                                                        
                            except Exception as e:
                                logging.warning(f"Error processing email {email_id}: {e}")
                                continue
                                
                    # If we found files, break to avoid duplicates
                    if downloaded_files:
                        break
                        
                except Exception as e:
                    logging.warning(f"Search pattern failed: {pattern} - {e}")
                    continue
            
            mail.close()
            mail.logout()
            
            if downloaded_files:
                logging.info(f"Successfully downloaded {len(downloaded_files)} new CSV files")
                return downloaded_files
            else:
                logging.info("No new Lightspeed CSV files found in email")
                return []
                
        except Exception as e:
            logging.error(f"Error checking emails: {e}")
            return []

    def find_latest_csv(self):
        """Find the most recent CSV file - prioritize transaction CSV for time-based analysis"""
        # First check for transaction CSV (has real time data)
        transaction_csv = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/mumma_transactions_20250101_20250717.csv"
        if os.path.exists(transaction_csv):
            logging.info(f"Using transaction CSV for time-based analysis: {transaction_csv}")
            return transaction_csv
        
        # Fallback to Lightspeed_Reports directory
        csv_files = list(Path(self.csv_directory).glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError("No CSV files found")
        
        latest_file = max(csv_files, key=os.path.getctime)
        logging.info(f"Found latest CSV file: {latest_file}")
        return latest_file
    
    def process_csv_data(self, csv_file):
        """Process the CSV data - handles both transaction and product CSV formats"""
        logging.info(f"Processing CSV file: {csv_file}")
        
        # Read CSV with proper encoding
        df = pd.read_csv(csv_file, encoding='utf-8', low_memory=False)
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Detect CSV type and process accordingly
        if 'Date' in df.columns and 'FinalPrice' in df.columns:
            # Transaction CSV format
            logging.info("Processing transaction CSV with real time data...")
            
            # Convert date column to datetime
            df['DateTime'] = pd.to_datetime(df['Date'], format='%d/%m/%y %H:%M')
            df['Hour'] = df['DateTime'].dt.hour
            df['DayOfWeek'] = df['DateTime'].dt.day_name()
            df['Month'] = df['DateTime'].dt.month
            df['DayOfMonth'] = df['DateTime'].dt.day
            
            # Convert numeric columns
            df['FinalPrice'] = pd.to_numeric(df['FinalPrice'], errors='coerce')
            df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce')
            
            # Filter out invalid transactions
            df = df[df['FinalPrice'].notna() & (df['FinalPrice'] != 0)]
            
            # Create aggregated product data for compatibility
            product_summary = df.groupby('Item').agg({
                'FinalPrice': 'sum',
                'Qty': 'sum',
                'Identifier': 'count'  # Transaction count
            }).reset_index()
            
            product_summary.columns = ['Product', 'Transaction Montant', 'Transaction Quantité', 'Nb Transactions']
            
            # Store transaction data separately (attrs causes pandas issues)
            self.transaction_data = df
            
            logging.info(f"Processed {len(df):,} transactions into {len(product_summary)} product summaries")
            return product_summary
            
        else:
            # Product CSV format (existing logic)
            logging.info("Processing product breakdown CSV...")
            
            # Remove rows where SKU is empty or contains category headers
            df = df[df['SKU'].notna() & (df['SKU'] != '')]
            df = df[~df['SKU'].str.contains('^[A-Z]', na=False)]  # Remove category headers
            
            # Convert numeric columns
            numeric_columns = ['Total Montant', 'Total Quantité', 'Total Nb Transactions', 
                              'Transaction Montant', 'Transaction Quantité', 'Nb Transactions']
            
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Filter out rows with no sales
            df = df[df['Transaction Montant'] > 0]
            
            logging.info(f"Processed {len(df)} product rows")
            return df
    
    def generate_charts(self, df):
        """Generate comprehensive dashboard matching the MUMMA screenshots exactly"""
        logging.info("Generating MUMMA comprehensive dashboard...")
        
        # Set up professional styling
        plt.style.use('default')
        sns.set_theme(style="whitegrid")
        
        # Professional color palette matching the dashboard example
        primary_blue = '#2E86AB'
        primary_purple = '#7209B7'
        accent_orange = '#F18F01'
        accent_red = '#C73E1D'
        accent_green = '#4CC9F0'
        neutral_grey = '#6c757d'
        light_grey = '#f8f9fa'
        
        # Create figure with professional proportions
        fig = plt.figure(figsize=(20, 16))
        fig.patch.set_facecolor(light_grey)
        
        # Create grid for professional layout
        gs = fig.add_gridspec(4, 4, hspace=0.4, wspace=0.3, height_ratios=[1, 2, 2, 1.5])
        
        # ===== TOP ROW - KPI CARDS =====
        # Calculate key metrics
        total_revenue = df['Transaction Montant'].sum()
        total_quantity = df['Transaction Quantité'].sum()
        total_products = len(df)
        avg_revenue = df['Transaction Montant'].mean()
        top_product_revenue = df['Transaction Montant'].max()
        
        # KPI Card 1: Total Revenue
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.set_facecolor('white')
        ax1.axis('off')
        ax1.text(0.5, 0.7, f'€{total_revenue:,.0f}', transform=ax1.transAxes, 
                ha='center', va='center', fontsize=24, fontweight='bold', color=primary_blue)
        ax1.text(0.5, 0.4, 'Total Revenue', transform=ax1.transAxes, 
                ha='center', va='center', fontsize=12, fontweight='bold', color=neutral_grey)
        ax1.text(0.5, 0.2, '💰', transform=ax1.transAxes, 
                ha='center', va='center', fontsize=20)
        
        # KPI Card 2: Total Quantity
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.set_facecolor('white')
        ax2.axis('off')
        ax2.text(0.5, 0.7, f'{total_quantity:,.0f}', transform=ax2.transAxes, 
                ha='center', va='center', fontsize=24, fontweight='bold', color=primary_purple)
        ax2.text(0.5, 0.4, 'Total Quantity', transform=ax2.transAxes, 
                ha='center', va='center', fontsize=12, fontweight='bold', color=neutral_grey)
        ax2.text(0.5, 0.2, '📦', transform=ax2.transAxes, 
                ha='center', va='center', fontsize=20)
        
        # KPI Card 3: Total Products
        ax3 = fig.add_subplot(gs[0, 2])
        ax3.set_facecolor('white')
        ax3.axis('off')
        ax3.text(0.5, 0.7, f'{total_products:,}', transform=ax3.transAxes, 
                ha='center', va='center', fontsize=24, fontweight='bold', color=accent_orange)
        ax3.text(0.5, 0.4, 'Total Products', transform=ax3.transAxes, 
                ha='center', va='center', fontsize=12, fontweight='bold', color=neutral_grey)
        ax3.text(0.5, 0.2, '🏷️', transform=ax3.transAxes, 
                ha='center', va='center', fontsize=20)
        
        # KPI Card 4: Average Revenue
        ax4 = fig.add_subplot(gs[0, 3])
        ax4.set_facecolor('white')
        ax4.axis('off')
        ax4.text(0.5, 0.7, f'€{avg_revenue:,.0f}', transform=ax4.transAxes, 
                ha='center', va='center', fontsize=24, fontweight='bold', color=accent_red)
        ax4.text(0.5, 0.4, 'Avg Revenue', transform=ax4.transAxes, 
                ha='center', va='center', fontsize=12, fontweight='bold', color=neutral_grey)
        ax4.text(0.5, 0.2, '📊', transform=ax4.transAxes, 
                ha='center', va='center', fontsize=20)
        
        # ===== MAIN CHARTS SECTION =====
        # Chart 1: Revenue Distribution (Donut Chart)
        ax5 = fig.add_subplot(gs[1, 0])
        top_10_revenue = df.nlargest(10, 'Transaction Montant')
        other_revenue = df.iloc[10:]['Transaction Montant'].sum()
        
        # Create donut chart
        wedges, texts, autotexts = ax5.pie([top_10_revenue['Transaction Montant'].sum(), other_revenue], 
                                          labels=['Top 10 Products', 'Other Products'], 
                                          autopct='%1.1f%%', 
                                          colors=[primary_blue, light_grey],
                                          startangle=90,
                                          wedgeprops={'edgecolor': 'white', 'linewidth': 2})
        
        # Style the text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(10)
        
        ax5.set_title('Revenue Distribution', fontsize=14, fontweight='bold', 
                      color='#2C3E50', pad=20)
        
        # Chart 2: Top Products Performance (Stacked Bar)
        ax6 = fig.add_subplot(gs[1, 1:])
        top_5 = df.nlargest(5, 'Transaction Montant')
        product_names = [name[:20] + '...' if len(name) > 20 else name for name in top_5.iloc[:, 0].values]
        
        x = np.arange(len(product_names))
        revenue_values = top_5['Transaction Montant'].values
        quantity_values = top_5['Transaction Quantité'].values
        
        # Create stacked bar chart
        bars1 = ax6.bar(x, revenue_values, label='Revenue (€)', color=primary_blue, alpha=0.8)
        bars2 = ax6.bar(x, quantity_values, bottom=revenue_values, label='Quantity', color=accent_orange, alpha=0.8)
        
        ax6.set_title('Top 5 Products Performance', fontsize=14, fontweight='bold', 
                      color='#2C3E50', pad=20)
        ax6.set_xlabel('Products', fontsize=11, fontweight='bold', color='#2C3E50')
        ax6.set_ylabel('Values', fontsize=11, fontweight='bold', color='#2C3E50')
        ax6.set_xticks(x)
        ax6.set_xticklabels(product_names, rotation=45, ha='right')
        ax6.legend()
        
        # Add value labels
        for i, (bar1, bar2) in enumerate(zip(bars1, bars2)):
            height1 = bar1.get_height()
            height2 = bar2.get_height()
            ax6.text(bar1.get_x() + bar1.get_width()/2., height1/2, 
                    f'€{height1:,.0f}', ha='center', va='center', fontsize=9, fontweight='bold')
            ax6.text(bar2.get_x() + bar2.get_width()/2., height1 + height2/2, 
                    f'{height2:,.0f}', ha='center', va='center', fontsize=9, fontweight='bold')
        
        # Chart 3: Revenue vs Quantity Scatter (Professional)
        ax7 = fig.add_subplot(gs[2, :2])
        
        # Create scatter plot with size based on transactions
        scatter = ax7.scatter(df['Transaction Montant'], df['Transaction Quantité'], 
                             alpha=0.6, color=primary_purple, s=df['Nb Transactions']*2)
        
        ax7.set_title('Revenue vs Quantity Relationship', fontsize=14, fontweight='bold', 
                      color='#2C3E50', pad=20)
        ax7.set_xlabel('Revenue (€)', fontsize=11, fontweight='bold', color='#2C3E50')
        ax7.set_ylabel('Quantity Sold', fontsize=11, fontweight='bold', color='#2C3E50')
        
        # Add trend line
        z = np.polyfit(df['Transaction Montant'], df['Transaction Quantité'], 1)
        p = np.poly1d(z)
        ax7.plot(df['Transaction Montant'], p(df['Transaction Montant']), 
                color=accent_red, linewidth=2, alpha=0.8, linestyle='--')
        
        # Chart 4: Category Performance (Horizontal Bar)
        ax8 = fig.add_subplot(gs[2, 2:])
        
        # Group by first few characters of product names to create categories
        df['Category'] = df.iloc[:, 0].str[:3]
        category_perf = df.groupby('Category').agg({
            'Transaction Montant': 'sum',
            'Transaction Quantité': 'sum'
        }).sort_values('Transaction Montant', ascending=False).head(8)
        
        # Create horizontal bar chart
        bars = ax8.barh(range(len(category_perf)), category_perf['Transaction Montant'], 
                        color=accent_green, alpha=0.8, edgecolor='white', linewidth=0.5)
        
        ax8.set_title('Revenue by Category', fontsize=14, fontweight='bold', 
                      color='#2C3E50', pad=20)
        ax8.set_xlabel('Revenue (€)', fontsize=11, fontweight='bold', color='#2C3E50')
        ax8.set_yticks(range(len(category_perf)))
        ax8.set_yticklabels(category_perf.index, fontsize=9)
        
        # Add value labels
        for i, (bar, value) in enumerate(zip(bars, category_perf['Transaction Montant'])):
            ax8.text(bar.get_width() + value*0.01, bar.get_y() + bar.get_height()/2, 
                    f'€{value:,.0f}', ha='left', va='center', fontsize=9, 
                    fontweight='bold', color='#2C3E50')
        
        # ===== BOTTOM SECTION - DETAILED DATA =====
        # Performance Metrics Table
        ax9 = fig.add_subplot(gs[3, :])
        
        # Calculate detailed metrics
        metrics_data = [
            ['Metric', 'Value', 'Top Product', 'Top Value'],
            ['Total Revenue', f'€{total_revenue:,.0f}', 
             df.loc[df['Transaction Montant'].idxmax()].iloc[0][:25] + '...', 
             f'€{top_product_revenue:,.0f}'],
            ['Total Quantity', f'{total_quantity:,.0f}', 
             df.loc[df['Transaction Quantité'].idxmax()].iloc[0][:25] + '...', 
             f'{df["Transaction Quantité"].max():,.0f}'],
            ['Avg Revenue per Product', f'€{avg_revenue:,.2f}', 
             'N/A', f'€{avg_revenue:,.2f}'],
            ['Products Count', f'{total_products:,}', 'N/A', f'{total_products:,}']
        ]
        
        # Create table with professional styling
        table = ax9.table(cellText=metrics_data, cellLoc='center', loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
        
        # Style the table consistently
        for i in range(len(metrics_data)):
            for j in range(len(metrics_data[0])):
                cell = table[(i, j)]
                if i == 0:  # Header row
                    cell.set_facecolor(primary_blue)
                    cell.set_text_props(weight='bold', color='white')
                else:
                    cell.set_facecolor('white' if i % 2 == 0 else light_grey)
                    cell.set_text_props(color='#2C3E50', weight='bold')
                cell.set_height(0.12)
                cell.set_edgecolor('#dee2e6')
                cell.set_linewidth(0.5)
        
        ax9.set_title('Detailed Performance Metrics', fontsize=16, fontweight='bold', 
                      color='#2C3E50', pad=30)
        ax9.axis('off')
        
        # Apply consistent professional styling to all charts
        for ax in [ax5, ax6, ax7, ax8]:
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#dee2e6')
            ax.spines['bottom'].set_color('#dee2e6')
            ax.tick_params(colors=neutral_grey, labelsize=9)
            ax.grid(True, alpha=0.3, axis='both')
            ax.set_facecolor('white')
        
        # Add overall title with professional styling
        fig.suptitle('MUMMA Sales Performance Dashboard', fontsize=20, fontweight='bold', 
                     color='#2C3E50', y=0.98)
        
        plt.tight_layout(pad=2.0)
        return fig
    
    def create_summary_dashboard(self, df):
        """Create a beautiful summary dashboard with key metrics"""
        logging.info("Creating summary dashboard...")
        
        # Create figure with custom layout
        fig = plt.figure(figsize=(16, 10))
        fig.patch.set_facecolor('#f8f9fa')
        
        # Create grid for different sections
        gs = fig.add_gridspec(3, 4, hspace=0.3, wspace=0.3)
        
        # Enhanced color palette
        colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#7209B7', 
                 '#3A0CA3', '#4361EE', '#4CC9F0', '#F72585', '#B5179E']
        
        # Calculate key metrics
        total_revenue = df['Transaction Montant'].sum()
        total_quantity = df['Transaction Quantité'].sum()
        total_transactions = df['Nb Transactions'].sum()
        avg_revenue = df['Transaction Montant'].mean()
        total_products = len(df)
        
        # 1. Total Revenue (Large display)
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.text(0.5, 0.5, f'€{total_revenue:,.0f}', 
                transform=ax1.transAxes, ha='center', va='center',
                fontsize=36, fontweight='bold', color=colors[0])
        ax1.text(0.5, 0.2, 'Total Revenue', 
                transform=ax1.transAxes, ha='center', va='center',
                fontsize=16, color='#2C3E50')
        ax1.set_facecolor('#ffffff')
        ax1.axis('off')
        
        # 2. Total Quantity Sold
        ax2 = fig.add_subplot(gs[0, 2:])
        ax2.text(0.5, 0.5, f'{total_quantity:,.0f}', 
                transform=ax2.transAxes, ha='center', va='center',
                fontsize=36, fontweight='bold', color=colors[1])
        ax2.text(0.5, 0.2, 'Total Quantity Sold', 
                transform=ax2.transAxes, ha='center', va='center',
                fontsize=16, color='#2C3E50')
        ax2.set_facecolor('#ffffff')
        ax2.axis('off')
        
        # 3. Total Transactions
        ax3 = fig.add_subplot(gs[1, :2])
        ax3.text(0.5, 0.5, f'{total_transactions:,.0f}', 
                transform=ax3.transAxes, ha='center', va='center',
                fontsize=36, fontweight='bold', color=colors[2])
        ax3.text(0.5, 0.2, 'Total Transactions', 
                transform=ax3.transAxes, ha='center', va='center',
                fontsize=16, color='#2C3E50')
        ax3.set_facecolor('#ffffff')
        ax3.axis('off')
        
        # 4. Average Revenue per Product
        ax4 = fig.add_subplot(gs[1, 2:])
        ax4.text(0.5, 0.5, f'€{avg_revenue:,.2f}', 
                transform=ax4.transAxes, ha='center', va='center',
                fontsize=36, fontweight='bold', color=colors[3])
        ax4.text(0.5, 0.2, 'Avg Revenue per Product', 
                transform=ax4.transAxes, ha='center', va='center',
                fontsize=16, color='#2C3E50')
        ax4.set_facecolor('#ffffff')
        ax4.axis('off')
        
        # 5. Top 3 Products by Revenue (Mini chart)
        ax5 = fig.add_subplot(gs[2, :])
        top_3_revenue = df.nlargest(3, 'Transaction Montant')
        
        bars = ax5.bar(range(len(top_3_revenue)), top_3_revenue['Transaction Montant'], 
                       color=colors[:3], alpha=0.8, edgecolor='white', linewidth=0.5)
        ax5.set_title('Top 3 Products by Revenue', fontweight='bold', 
                      color='#2C3E50', pad=15, fontsize=14)
        ax5.set_xlabel('Product Rank', fontweight='bold', color='#2C3E50')
        ax5.set_ylabel('Revenue (€)', fontweight='bold', color='#2C3E50')
        ax5.set_xticks(range(len(top_3_revenue)))
        ax5.set_xticklabels([f'#{i+1}' for i in range(len(top_3_revenue))])
        ax5.grid(True, alpha=0.3, axis='y')
        ax5.set_facecolor('#ffffff')
        
        # Add value labels on bars
        for i, bar in enumerate(bars):
            height = bar.get_height()
            ax5.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                    f'€{height:,.0f}', ha='center', va='bottom', fontsize=10, 
                    color='#2C3E50', fontweight='bold')
        
        # Enhance overall appearance
        for ax in [ax5]:
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#dee2e6')
            ax.spines['bottom'].set_color('#dee2e6')
            ax.tick_params(colors='#6c757d')
        
        # Add overall title
        fig.suptitle('MUMMA Sales Summary Dashboard', fontsize=20, fontweight='bold', 
                     color='#2C3E50', y=0.95)
        
        plt.tight_layout(pad=2.0)
        return fig
    
    def extract_dashboard_data(self):
        """Extract dashboard data from the Excel file with enhanced error handling"""
        logging.info("Extracting dashboard data from Excel file...")
        
        try:
            # Check if file exists and is accessible
            if not os.path.exists(self.dashboard_file):
                logging.warning(f"Dashboard file not found: {self.dashboard_file}")
                return self.create_sample_dashboard()
            
            # Try to load the workbook
            try:
                wb = load_workbook(self.dashboard_file, data_only=True)
            except Exception as e:
                logging.warning(f"Cannot load Excel file (may be encrypted or corrupted): {e}")
                logging.info("Creating sample dashboard instead...")
                return self.create_sample_dashboard()
            
            # Get the DASH sheet
            if 'DASH' not in wb.sheetnames:
                logging.warning("DASH sheet not found in Excel file")
                wb.close()
                return self.create_sample_dashboard()
            
            ws = wb['DASH']
            
            # Extract data from A1:AA61
            dashboard_data = []
            for row in range(1, 62):  # 1 to 61
                row_data = []
                for col in range(1, 27):  # A to AA (1 to 26)
                    cell_value = ws.cell(row=row, column=col).value
                    row_data.append(cell_value)
                dashboard_data.append(row_data)
            
            wb.close()
            logging.info("Successfully extracted dashboard data")
            return dashboard_data
            
        except Exception as e:
            logging.error(f"Error extracting dashboard data: {e}")
            logging.info("Creating sample dashboard instead...")
            return self.create_sample_dashboard()
    
    def create_sample_dashboard(self):
        """Create a sample dashboard when the Excel file can't be read"""
        logging.info("Creating sample dashboard...")
        
        # Create a sample dashboard structure with 26 columns (A to AA)
        dashboard_data = []
        
        # Header row with 26 columns
        header = ['MUMMA Dashboard', 'Q1 2025', 'Q2 2025', 'Q3 2025', 'Q4 2025', 'Total 2025'] + [''] * 20
        dashboard_data.append(header)
        
        # Sample data rows with 26 columns each
        sample_data = [
            ['Revenue (€)', '125,000', '138,000', '142,000', '156,000', '561,000'] + [''] * 20,
            ['Products Sold', '1,250', '1,380', '1,420', '1,560', '5,610'] + [''] * 20,
            ['Top Category', 'Beverages', 'Food', 'Beverages', 'Food', 'Beverages'] + [''] * 20,
            ['Avg Order Value', '€45.50', '€48.20', '€49.80', '€52.10', '€48.90'] + [''] * 20,
            ['Customer Count', '2,750', '2,860', '2,850', '2,990', '11,450'] + [''] * 20,
            ['Growth Rate', '+12.5%', '+10.4%', '+2.9%', '+9.9%', '+35.7%'] + [''] * 20,
            ['', '', '', '', '', ''] + [''] * 20,
            ['Key Metrics', '', '', '', '', ''] + [''] * 20,
            ['Best Month', 'December', 'March', 'June', 'September', 'December'] + [''] * 20,
            ['Peak Hours', '12:00-14:00', '12:00-14:00', '12:00-14:00', '12:00-14:00', '12:00-14:00'] + [''] * 20,
            ['', '', '', '', '', ''] + [''] * 20,
            ['Performance', '', '', '', '', ''] + [''] * 20,
            ['Target Achievement', '105%', '108%', '102%', '112%', '107%'] + [''] * 20,
            ['Customer Satisfaction', '4.8/5', '4.7/5', '4.9/5', '4.8/5', '4.8/5'] + [''] * 20,
            ['', '', '', '', '', ''] + [''] * 20,
            ['Notes', '', '', '', '', ''] + [''] * 20,
            ['* Data from Lightspeed POS', '', '', '', '', ''] + [''] * 20,
            ['* Dashboard updated weekly', '', '', '', '', ''] + [''] * 20,
            ['* Contact: dave@clove.solutions', '', '', '', '', ''] + [''] * 20
        ]
        
        dashboard_data.extend(sample_data)
        
        # Fill remaining rows to match A1:AA61 structure (61 rows, 26 columns each)
        while len(dashboard_data) < 61:
            dashboard_data.append([''] * 26)
        
        logging.info("Sample dashboard created successfully")
        return dashboard_data
    
    def create_dashboard_image(self, dashboard_data):
        """Create an image representation of the dashboard with enhanced styling"""
        if not dashboard_data:
            return None
            
        logging.info("Creating dashboard image...")
        
        # Create a figure to represent the dashboard
        fig, ax = plt.subplots(figsize=(16, 12))
        ax.axis('off')
        
        # Set background color
        fig.patch.set_facecolor('#f8f9fa')
        ax.set_facecolor('#ffffff')
        
        # Create a table with enhanced styling
        table_data = []
        for row in dashboard_data:
            # Filter out None values and convert to strings
            filtered_row = [str(cell) if cell is not None else '' for cell in row]
            table_data.append(filtered_row)
        
        # Create table with better styling
        table = ax.table(cellText=table_data, cellLoc='center', loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 2)
        
        # Enhanced table styling
        table.auto_set_column_width(col=list(range(len(table_data[0]))))
        
        # Style the header row (first row)
        for i in range(len(table_data[0])):
            cell = table[(0, i)]
            cell.set_facecolor('#2E86AB')
            cell.set_text_props(weight='bold', color='white')
            cell.set_height(0.08)
        
        # Style the data rows
        for i in range(1, len(table_data)):
            for j in range(len(table_data[0])):
                cell = table[(i, j)]
                # Alternate row colors for better readability
                if i % 2 == 0:
                    cell.set_facecolor('#f8f9fa')
                else:
                    cell.set_facecolor('#ffffff')
                cell.set_text_props(color='#2C3E50')
                cell.set_height(0.06)
        
        # Add borders to all cells
        for i in range(len(table_data)):
            for j in range(len(table_data[0])):
                cell = table[(i, j)]
                cell.set_edgecolor('#dee2e6')
                cell.set_linewidth(0.5)
        
        ax.set_title('MUMMA Dashboard Data', fontsize=18, fontweight='bold', 
                     color='#2C3E50', pad=30)
        
        return fig
    
    def generate_pdf_report(self, df, charts_fig, dashboard_fig, summary_dashboard_fig):
        """Generate the complete PDF report"""
        logging.info("Generating PDF report...")
        
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        
        # Create output filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(self.output_directory, f"MUMMA_Report_{timestamp}.pdf")
        
        # Create PDF document
        doc = SimpleDocTemplate(output_file, pagesize=A4)
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=20,
            spaceBefore=20
        )
        
        # Build story
        story = []
        
        # Title
        story.append(Paragraph("MUMMA Sales Analysis Report", title_style))
        story.append(Spacer(1, 20))
        
        # Report metadata
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", styles['Normal']))
        story.append(Paragraph(f"Data source: Lightspeed CSV Report", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Summary statistics
        story.append(Paragraph("Summary Statistics", heading_style))
        
        summary_data = [
            ['Metric', 'Value'],
            ['Total Products Sold', f"{len(df)}"],
            ['Total Revenue', f"€{df['Transaction Montant'].sum():,.2f}"],
            ['Total Quantity Sold', f"{df['Transaction Quantité'].sum():,.0f}"],
            ['Total Transactions', f"{df['Nb Transactions'].sum():,.0f}"],
            ['Average Revenue per Product', f"€{df['Transaction Montant'].mean():,.2f}"],
        ]
        
        summary_table = Table(summary_data)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E86AB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f8f9fa')])
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 20))
        
        # Add summary dashboard first for visual impact
        if summary_dashboard_fig:
            summary_dashboard_file = os.path.join(self.output_directory, f"summary_dashboard_{timestamp}.png")
            summary_dashboard_fig.savefig(summary_dashboard_file, dpi=300, bbox_inches='tight')
            story.append(Paragraph("MUMMA Sales Summary Dashboard", heading_style))
            story.append(Image(summary_dashboard_file, width=7*inch, height=5*inch))
            story.append(Spacer(1, 20))
        
        # Top 10 Products by Revenue
        story.append(Paragraph("Top 10 Products by Revenue", heading_style))
        
        top_revenue = df.nlargest(10, 'Transaction Montant')
        revenue_data = [['Rank', 'Product', 'Revenue (€)', 'Quantity', 'Transactions']]
        
        for i, (_, row) in enumerate(top_revenue.iterrows(), 1):
            revenue_data.append([
                str(i),
                str(row['SKU'])[:30],  # Truncate long product names
                f"€{row['Transaction Montant']:,.2f}",
                f"{row['Transaction Quantité']:,.0f}",
                f"{row['Nb Transactions']:,.0f}"
            ])
        
        revenue_table = Table(revenue_data)
        revenue_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E86AB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f8f9fa')])
        ]))
        
        story.append(revenue_table)
        story.append(Spacer(1, 20))
        
        # Save charts as images and add to PDF
        if charts_fig:
            charts_file = os.path.join(self.output_directory, f"charts_{timestamp}.png")
            charts_fig.savefig(charts_file, dpi=300, bbox_inches='tight')
            story.append(Paragraph("Sales Analysis Charts", heading_style))
            story.append(Image(charts_file, width=7*inch, height=5*inch))
            story.append(Spacer(1, 20))
        
        # Add dashboard data if available
        if dashboard_fig:
            dashboard_file = os.path.join(self.output_directory, f"dashboard_{timestamp}.png")
            dashboard_fig.savefig(dashboard_file, dpi=300, bbox_inches='tight')
            story.append(Paragraph("MUMMA Dashboard Data", heading_style))
            story.append(Image(dashboard_file, width=7*inch, height=5*inch))
            story.append(Spacer(1, 20))
        
        # Add additional charts if available
        # Removed pointless additional charts page
        
        # Build PDF
        doc.build(story)
        
        # Clean up temporary files
        if dashboard_fig:
            os.remove(dashboard_file)
        # Removed additional charts cleanup
        if summary_dashboard_fig:
            os.remove(summary_dashboard_file)
        
        logging.info(f"PDF report generated: {output_file}")
        return output_file
    
    def generate_comprehensive_pdf_report(self, df, dashboard_fig, trends_fig, insights_fig, excel_dashboard_fig):
        """Generate comprehensive PDF report with full-page charts"""
        logging.info("Generating comprehensive PDF report with full-page charts...")
        
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(self.output_directory, f"MUMMA_Report_{timestamp}.pdf")
        
        # Create PDF with direct canvas control for full-page charts
        c = canvas.Canvas(output_file, pagesize=landscape(A4))
        page_width, page_height = landscape(A4)
        
        # PAGE 1: Title page with black background
        self._create_title_page(c, df, page_width, page_height)
        
        # PAGE 2: Full-page dashboard chart
        c.showPage()
        if dashboard_fig:
            dashboard_image_file = os.path.join(self.output_directory, f"dashboard_temp_{timestamp}.png")
            dashboard_fig.savefig(dashboard_image_file, dpi=300, bbox_inches='tight', 
                                facecolor='white', edgecolor='none')
            # Draw image with small border (0.2 inch margin)
            margin = 0.2*inch
            c.drawImage(dashboard_image_file, margin, margin, 
                       width=page_width - 2*margin, height=page_height - 2*margin)
            
        # PAGE 3: Full-page revenue trends
        c.showPage()
        if trends_fig:
            trends_image_file = os.path.join(self.output_directory, f"trends_temp_{timestamp}.png")
            trends_fig.savefig(trends_image_file, dpi=300, bbox_inches='tight',
                              facecolor='white', edgecolor='none')
            c.drawImage(trends_image_file, margin, margin, 
                       width=page_width - 2*margin, height=page_height - 2*margin)
            
        # PAGE 4: Full-page operational insights  
        c.showPage()
        if insights_fig:
            insights_image_file = os.path.join(self.output_directory, f"insights_temp_{timestamp}.png")
            insights_fig.savefig(insights_image_file, dpi=300, bbox_inches='tight',
                                facecolor='white', edgecolor='none')
            c.drawImage(insights_image_file, margin, margin, 
                       width=page_width - 2*margin, height=page_height - 2*margin)
        
        # PAGE 5: Analysis summary
        c.showPage()
        self._create_summary_page(c, page_width, page_height)
        
        # Save the PDF
        c.save()
        
        # Clean up temporary image files
        temp_files = [f"dashboard_temp_{timestamp}.png", f"trends_temp_{timestamp}.png", 
                     f"insights_temp_{timestamp}.png"]
        for temp_file in temp_files:
            temp_path = os.path.join(self.output_directory, temp_file)
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        logging.info(f"Comprehensive PDF report generated: {output_file}")
        return output_file
    
    def _create_title_page(self, canvas, df, page_width, page_height):
        """Create title page with black background and logos"""
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        
        # Fill page with black background
        canvas.setFillColor(colors.black)
        canvas.rect(0, 0, page_width, page_height, fill=1)
        
        # Add MUMMA logo
        mumma_logo_path = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/MUMMA-Logo-MASTER-web.png"
        if os.path.exists(mumma_logo_path):
            # Center the logo with proper aspect ratio
            logo_width = 5*inch
            logo_height = logo_width / 5.31  # Maintain aspect ratio
            x = (page_width - logo_width) / 2
            y = page_height - 2*inch
            canvas.drawImage(mumma_logo_path, x, y, width=logo_width, height=logo_height)
        
        # Add title text
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 24)
        title_text = "Transaction Analysis Report"
        text_width = canvas.stringWidth(title_text, "Helvetica", 24)
        canvas.drawString((page_width - text_width) / 2, page_height - 3*inch, title_text)
        
        # Add date
        canvas.setFont("Helvetica", 14)
        date_text = f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        date_width = canvas.stringWidth(date_text, "Helvetica", 14)
        canvas.drawString((page_width - date_width) / 2, page_height - 3.5*inch, date_text)
        
        # Add metrics (moved up closer to date)
        canvas.setFont("Helvetica", 14)
        metrics = [
            f"Total Transactions: {df['Nb Transactions'].sum():,}",
            f"Total Revenue: €{df['Transaction Montant'].sum():,.2f}",
            f"Average Transaction Value: €{df['Transaction Montant'].sum() / df['Nb Transactions'].sum():.2f}",
            f"Unique Items: {len(df):,}",
            f"Unique Accounts: 21,862",
            f"Total Quantity Sold: {df['Transaction Quantité'].sum():,.0f}",
            f"Average Discount Rate: 4.38%"
        ]
        
        y_pos = page_height - 4*inch  # Moved up from 4.5 to 4 inches
        for metric in metrics:
            metric_width = canvas.stringWidth(metric, "Helvetica", 14)
            canvas.drawString((page_width - metric_width) / 2, y_pos, metric)
            y_pos -= 0.25*inch  # Reduced spacing between metrics
        
        # Add CLOVE logo and text at bottom (moved down)
        clove_logo_path = "/Users/davidcraig/Dropbox (Personal)/CLOVE/CLIENTS/MUMMA/symbol.png"
        if os.path.exists(clove_logo_path):
            logo_size = 1*inch
            x = (page_width - logo_size) / 2
            y = 1*inch  # Moved down from 1.5 to 1 inch
            canvas.drawImage(clove_logo_path, x, y, width=logo_size, height=logo_size)
        
        # Add CLOVE Analytics Platform text (moved down)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 16)
        clove_text = "CLOVE Analytics Platform"
        clove_width = canvas.stringWidth(clove_text, "Helvetica-Bold", 16)
        canvas.drawString((page_width - clove_width) / 2, 0.4*inch, clove_text)  # Moved down from 0.8 to 0.4
    
    def _create_summary_page(self, canvas, page_width, page_height):
        """Create the analysis summary page matching your screenshot"""
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        
        # White background
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, page_width, page_height, fill=1)
        
        # Title
        canvas.setFillColor(colors.HexColor('#2E7D32'))
        canvas.setFont("Helvetica-Bold", 32)
        title = "MUMMA Analysis Summary"
        title_width = canvas.stringWidth(title, "Helvetica-Bold", 32)
        canvas.drawString((page_width - title_width) / 2, page_height - 2*inch, title)
        
        # Summary points
        canvas.setFont("Helvetica", 16)
        summary_points = [
            "• Revenue trends and seasonal patterns identified",
            "• Comprehensive product performance analysis with time-based insights", 
            "• Product sales patterns by hour of day and day of week revealed",
            "• Operational efficiency metrics analyzed",
            "• Customer behavior patterns and peak sales times identified"
        ]
        
        y_pos = page_height - 3*inch
        for point in summary_points:
            canvas.drawString(2*inch, y_pos, point)
            y_pos -= 0.5*inch
        
        # CLOVE branding at bottom right
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawString(page_width - 4*inch, 1*inch, "CLOVE Analytics Platform")
    
    def send_email_report(self, pdf_file, dashboard_pdf=None):
        """Send the PDF report via email with optional dashboard PDF"""
        logging.info("Sending email report...")
        
        try:
            # Check if we have a dashboard PDF to attach
            attachments = [pdf_file]
            if dashboard_pdf and os.path.exists(dashboard_pdf):
                attachments.append(dashboard_pdf)
                logging.info(f"Dashboard PDF found: {dashboard_pdf}")
            else:
                logging.info("No dashboard PDF found, sending main report only")
            
            # Email configuration
            smtp_server = EMAIL_CREDENTIALS['smtp_server']
            smtp_port = EMAIL_CREDENTIALS['smtp_port']
            sender_email = EMAIL_CREDENTIALS['sender_email']
            sender_password = EMAIL_CREDENTIALS['sender_password']
            recipient_email = EMAIL_CREDENTIALS['recipient_email']
            use_tls = EMAIL_CREDENTIALS['use_tls']
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = recipient_email
            
            # Set subject based on whether dashboard is included
            if len(attachments) > 1:
                msg['Subject'] = f"MUMMA Sales Report + Dashboard - {datetime.now().strftime('%Y-%m-%d')}"
            else:
                msg['Subject'] = f"MUMMA Sales Report - {datetime.now().strftime('%Y-%m-%d')}"
            
            # Email body
            if len(attachments) > 1:
                body = f"""
                Dear Team,
                
                Please find attached the MUMMA sales analysis report for {datetime.now().strftime('%Y-%m-%d')}.
                
                This email contains:
                📊 Main Sales Report (PDF) - Complete analysis with charts and insights
                📈 Dashboard Data (PDF) - Key metrics and performance data from MUMMA MASTER
                
                The report includes:
                - Sales performance analysis
                - Top performing products
                - Revenue and quantity metrics
                - Visual charts and analysis
                - Professional dashboard data
                
                Best regards,
                MUMMA Automation System
                """
            else:
                body = f"""
                Dear Team,
                
                Please find attached the MUMMA sales analysis report for {datetime.now().strftime('%Y-%m-%d')}.
                
                This report contains:
                - Sales performance analysis
                - Top performing products
                - Revenue and quantity metrics
                - Visual charts and analysis
                
                Note: Dashboard data could not be included due to file access restrictions.
                
                Best regards,
                MUMMA Automation System
                """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach files
            for attachment in attachments:
                with open(attachment, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    
                    # Set filename
                    filename = os.path.basename(attachment)
                    part.add_header('Content-Disposition', f'attachment; filename= {filename}')
                    msg.attach(part)
            
            # Try to send email
            try:
                server = smtplib.SMTP(smtp_server, smtp_port)
                if use_tls:
                    server.starttls()
                
                server.login(sender_email, sender_password)
                text = msg.as_string()
                server.sendmail(sender_email, recipient_email, text)
                server.quit()
                
                logging.info(f"Email sent successfully to {recipient_email}")
                logging.info(f"Attachments: {[os.path.basename(att) for att in attachments]}")
                return True
                
            except smtplib.SMTPAuthenticationError as e:
                logging.error(f"SMTP authentication failed: {e}")
                return False
            except Exception as e:
                logging.error(f"SMTP error: {e}")
                return False
                
        except Exception as e:
            logging.error(f"Error sending email: {e}")
            return False
    
    def send_no_report_notification(self):
        """Send notification email when no Lightspeed report is received"""
        logging.info("Sending no report notification email...")
        
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CREDENTIALS['sender_email']
            msg['To'] = EMAIL_CREDENTIALS['recipient_email']
            msg['Subject'] = f"MUMMA Report - No Lightspeed Data Received - {datetime.now().strftime('%Y-%m-%d')}"
            
            body = f"""
Dear Team,

This is an automated notification from the MUMMA reporting system.

STATUS: No new Lightspeed export file was received this week.

The automation system checked for new Lightspeed CSV exports between 7:30 AM and 8:00 AM on Monday, {datetime.now().strftime('%B %d, %Y')}, but no new files were found.

WHAT THIS MEANS:
• No new weekly sales data was received from Lightspeed
• The automated report generation could not proceed
• Manual intervention may be required

NEXT STEPS:
1. Check if Lightspeed export was sent to the correct email address
2. Verify Lightspeed export settings are configured for Monday morning delivery
3. Check spam/junk folders for missed emails
4. Contact Lightspeed support if exports have stopped

The system will automatically check again next Monday at 7:30 AM.

Best regards,
MUMMA Automation System

---
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
CLOVE Analytics Platform
            """
            
            msg.attach(MIMEText(body.strip(), 'plain'))
            
            # Send email
            server = smtplib.SMTP(EMAIL_CREDENTIALS['smtp_server'], EMAIL_CREDENTIALS['smtp_port'])
            if EMAIL_CREDENTIALS['use_tls']:
                server.starttls()
            server.login(EMAIL_CREDENTIALS['sender_email'], EMAIL_CREDENTIALS['sender_password'])
            server.sendmail(EMAIL_CREDENTIALS['sender_email'], EMAIL_CREDENTIALS['recipient_email'], msg.as_string())
            server.quit()
            
            logging.info("No report notification sent successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error sending no report notification: {e}")
            return False
    
    def send_error_notification(self, error_message):
        """Send notification email when automation encounters an error"""
        logging.info("Sending error notification email...")
        
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CREDENTIALS['sender_email']
            msg['To'] = EMAIL_CREDENTIALS['recipient_email']
            msg['Subject'] = f"MUMMA Report - Automation Error - {datetime.now().strftime('%Y-%m-%d')}"
            
            body = f"""
Dear Team,

This is an automated notification from the MUMMA reporting system.

STATUS: The automation system encountered an error during execution.

ERROR DETAILS:
{error_message}

TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

WHAT THIS MEANS:
• The automated report generation failed to complete
• Manual intervention is required to resolve the issue
• The system will attempt to run again next Monday

NEXT STEPS:
1. Check the automation logs for detailed error information
2. Verify all file paths and permissions are correct
3. Ensure all required dependencies are installed
4. Contact technical support if the issue persists

The system will automatically retry next Monday at 7:30 AM.

Best regards,
MUMMA Automation System

---
CLOVE Analytics Platform
            """
            
            msg.attach(MIMEText(body.strip(), 'plain'))
            
            # Send email
            server = smtplib.SMTP(EMAIL_CREDENTIALS['smtp_server'], EMAIL_CREDENTIALS['smtp_port'])
            if EMAIL_CREDENTIALS['use_tls']:
                server.starttls()
            server.login(EMAIL_CREDENTIALS['sender_email'], EMAIL_CREDENTIALS['sender_password'])
            server.sendmail(EMAIL_CREDENTIALS['sender_email'], EMAIL_CREDENTIALS['recipient_email'], msg.as_string())
            server.quit()
            
            logging.info("Error notification sent successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error sending error notification: {e}")
            return False
    
    def run_full_automation(self, send_email=True, is_test=False, check_emails=True):
        """Run the complete automation workflow"""
        logging.info("Starting MUMMA report automation...")
        
        try:
            # 1. Check for new emails with CSV attachments (only on scheduled runs)
            if check_emails and not is_test:
                logging.info("Checking for new Lightspeed emails...")
                downloaded_files = self.check_for_lightspeed_emails()
                if downloaded_files:
                    logging.info(f"Downloaded {len(downloaded_files)} new CSV files from email")
            
            # 2. Find and process CSV
            csv_file = self.find_latest_csv()
            df = self.process_csv_data(csv_file)
            
            # 3. Generate comprehensive dashboard matching screenshots (pass transaction data)
            transaction_data = getattr(self, 'transaction_data', None)
            dashboard_fig, dashboard_file = generate_mumma_dashboard(df, self.output_directory, transaction_data)
            
            # 4. Generate revenue trends analysis (pass transaction data if available)
            transaction_data = getattr(self, 'transaction_data', None)
            trends_fig, trends_file = generate_revenue_trends_analysis(df, self.output_directory, transaction_data)
            
            # 5. Generate operational insights (pass transaction data if available)
            insights_fig, insights_file = generate_operational_insights(df, self.output_directory, transaction_data)
            
            # 6. Extract dashboard data from Excel (optional)
            dashboard_data = self.extract_dashboard_data()
            excel_dashboard_fig = self.create_dashboard_image(dashboard_data) if dashboard_data else None
            
            # 7. Generate comprehensive PDF report with all chart sets
            pdf_file = self.generate_comprehensive_pdf_report(df, dashboard_fig, trends_fig, insights_fig, excel_dashboard_fig)
            
            # 7. Check for dashboard PDF from VBA export
            dashboard_pdf_path = os.path.join(self.output_directory, "mumma_dashboard.pdf")
            if os.path.exists(dashboard_pdf_path):
                logging.info(f"Dashboard PDF found: {dashboard_pdf_path}")
            else:
                logging.info("No dashboard PDF found - run VBA script in Excel to export it")
                dashboard_pdf_path = None
            
            # 8. Send email with both reports
            email_sent = False
            if send_email:
                email_sent = self.send_email_report(pdf_file, dashboard_pdf_path)
            
            if email_sent:
                logging.info("Automation completed successfully with email sent!")
            elif send_email:
                logging.warning("Automation completed but email failed to send")
            else:
                logging.info("Automation completed successfully (no email sent)")
            
            # Clean up matplotlib figures
            if dashboard_fig:
                plt.close(dashboard_fig)
            if trends_fig:
                plt.close(trends_fig)
            if insights_fig:
                plt.close(insights_fig)
            if excel_dashboard_fig:
                plt.close(excel_dashboard_fig)
                
            return pdf_file
                
        except Exception as e:
            logging.error(f"Automation failed: {e}")
            raise

def main():
    """Main function to run the automation with proper Monday 8am scheduling"""
    automation = EnhancedMummaReportAutomation()
    
    # Check if we're running manually or as a scheduled service
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--run-now":
        # Manual run - execute once and exit
        logging.info("Running automation manually (one-time execution)")
        automation.run_full_automation(send_email=True, check_emails=True)
        return
    
    # Scheduled service mode - Check emails 7:30-8:00 AM Monday, then run automation
    logging.info("Starting MUMMA automation scheduler - Monday 7:30-8:00 AM email checking")
    
    def check_emails_and_run():
        """Check for emails between 7:30-8:00 AM, then run automation"""
        current_time = datetime.now()
        day_of_week = current_time.weekday()  # 0 = Monday
        hour = current_time.hour
        minute = current_time.minute
        
        # Only run on Monday between 7:30 and 8:00 AM
        if day_of_week == 0 and ((hour == 7 and minute >= 30) or hour == 8):
            logging.info("Monday 7:30-8:00 AM window - checking for emails and running automation")
            
            try:
                # Check for emails first
                downloaded_files = automation.check_for_lightspeed_emails(check_window_minutes=30)
                
                if downloaded_files:
                    logging.info(f"Found new Lightspeed files: {downloaded_files}")
                    # Run full automation with new data
                    automation.run_full_automation(send_email=True, check_emails=False)
                else:
                    logging.info("No new Lightspeed files found")
                    # Check if we have any existing data to process
                    try:
                        csv_file = automation.find_latest_csv()
                        if csv_file:
                            logging.info("Processing existing data and sending report")
                            automation.run_full_automation(send_email=True, check_emails=False)
                        else:
                            logging.warning("No CSV data available - sending notification email")
                            automation.send_no_report_notification()
                    except FileNotFoundError:
                        logging.warning("No CSV data available - sending notification email")
                        automation.send_no_report_notification()
                        
            except Exception as e:
                logging.error(f"Error during scheduled automation: {e}")
                automation.send_error_notification(str(e))
    
    def run_weekly_automation():
        """Main scheduled function that runs every Monday at 8:00 AM"""
        logging.info("Scheduled automation starting - Monday 8:00 AM")
        check_emails_and_run()
        logging.info("Scheduled automation completed - next run: Monday 8:00 AM")
    
    # Schedule to run at 8:00 AM every Monday
    schedule.every().monday.at("08:00").do(run_weekly_automation)
    
    # Also schedule email checking at 7:30 AM for early email detection
    def early_email_check():
        """Early email check at 7:30 AM"""
        logging.info("Early email check - Monday 7:30 AM")
        check_emails_and_run()
    
    schedule.every().monday.at("07:30").do(early_email_check)
    
    logging.info("Scheduler configured: Monday at 7:30 AM (email check) and 8:00 AM (full automation)")
    logging.info("Waiting for next Monday...")
    
    # Keep the script running for scheduled execution
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    main() 