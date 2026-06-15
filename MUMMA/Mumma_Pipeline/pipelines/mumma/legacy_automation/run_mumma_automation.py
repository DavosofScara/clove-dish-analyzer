#!/usr/bin/env python3
"""
MUMMA Automation Launcher
Simple script to run the MUMMA automation in different modes
"""

import sys
import os
from datetime import datetime

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def print_banner():
    """Print the MUMMA automation banner"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    MUMMA AUTOMATION SYSTEM                  ║
║                                                              ║
║  Automated Lightspeed Report Processing & Dashboard         ║
║  Generation with Email Distribution                         ║
║                                                              ║
║  CLOVE Analytics Platform                                   ║
╚══════════════════════════════════════════════════════════════╝
    """)

def show_menu():
    """Show the main menu options"""
    print("\n📋 AUTOMATION OPTIONS:")
    print("=" * 50)
    print("1. 🧪 Test System (No Email)")
    print("2. 🚀 Run Once Now (With Email)")
    print("3. ⏰ Start Scheduler (Monday 7:30-8:00 AM)")
    print("4. 📊 Generate Dashboard Only")
    print("5. 📧 Test Email Connection")
    print("6. ❌ Exit")
    print("=" * 50)

def run_test():
    """Run the test automation"""
    print("\n🧪 RUNNING TEST AUTOMATION...")
    print("This will generate reports without sending emails.")
    
    try:
        from test_complete_automation import main as test_main
        test_main()
    except Exception as e:
        print(f"❌ Test failed: {e}")

def run_once():
    """Run automation once with email"""
    print("\n🚀 RUNNING AUTOMATION ONCE...")
    print("This will check emails, generate reports, and send them.")
    
    response = input("\n⚠️  This will send emails! Continue? (y/N): ")
    if response.lower() != 'y':
        print("❌ Cancelled by user")
        return
    
    try:
        from mumma_report_automation_enhanced import EnhancedMummaReportAutomation
        automation = EnhancedMummaReportAutomation()
        automation.run_full_automation(send_email=True, check_emails=True)
        print("✅ Automation completed successfully!")
    except Exception as e:
        print(f"❌ Automation failed: {e}")

def start_scheduler():
    """Start the scheduled automation"""
    print("\n⏰ STARTING SCHEDULER...")
    print("This will run continuously and execute every Monday at 7:30-8:00 AM.")
    print("Press Ctrl+C to stop the scheduler.")
    
    response = input("\n⚠️  This will run continuously and send emails! Continue? (y/N): ")
    if response.lower() != 'y':
        print("❌ Cancelled by user")
        return
    
    try:
        from mumma_report_automation_enhanced import main as scheduler_main
        print("\n🔄 Scheduler started. Waiting for Monday 7:30-8:00 AM...")
        print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        scheduler_main()
    except KeyboardInterrupt:
        print("\n⏹️  Scheduler stopped by user")
    except Exception as e:
        print(f"❌ Scheduler failed: {e}")

def generate_dashboard_only():
    """Generate dashboard without email"""
    print("\n📊 GENERATING DASHBOARD ONLY...")
    
    try:
        from mumma_report_automation_enhanced import EnhancedMummaReportAutomation
        automation = EnhancedMummaReportAutomation()
        
        # Find and process CSV
        csv_file = automation.find_latest_csv()
        df = automation.process_csv_data(csv_file)
        
        # Generate dashboards
        from mumma_dashboard_generator import (
            generate_mumma_dashboard, 
            generate_revenue_trends_analysis, 
            generate_operational_insights
        )
        
        dashboard_fig, dashboard_file = generate_mumma_dashboard(df, automation.output_directory)
        trends_fig, trends_file = generate_revenue_trends_analysis(df, automation.output_directory)
        insights_fig, insights_file = generate_operational_insights(df, automation.output_directory)
        
        print(f"✅ Dashboard generated: {dashboard_file}")
        print(f"✅ Trends analysis: {trends_file}")
        print(f"✅ Operational insights: {insights_file}")
        
        # Clean up
        import matplotlib.pyplot as plt
        plt.close(dashboard_fig)
        plt.close(trends_fig)
        plt.close(insights_fig)
        
    except Exception as e:
        print(f"❌ Dashboard generation failed: {e}")

def test_email():
    """Test email connection"""
    print("\n📧 TESTING EMAIL CONNECTION...")
    
    try:
        from mumma_report_automation_enhanced import EnhancedMummaReportAutomation
        automation = EnhancedMummaReportAutomation()
        
        print("Testing email connectivity (read-only)...")
        downloaded_files = automation.check_for_lightspeed_emails()
        
        print("✅ Email connection successful!")
        if downloaded_files:
            print(f"Found {len(downloaded_files)} files")
        else:
            print("No new files found (this is normal)")
            
    except Exception as e:
        print(f"❌ Email test failed: {e}")
        print("\nTroubleshooting tips:")
        print("• Check email credentials in email_config.py")
        print("• Verify internet connection")
        print("• Ensure 2FA app passwords are used for Outlook")

def main():
    """Main launcher function"""
    print_banner()
    
    while True:
        show_menu()
        
        try:
            choice = input("\n👉 Select option (1-6): ").strip()
            
            if choice == '1':
                run_test()
            elif choice == '2':
                run_once()
            elif choice == '3':
                start_scheduler()
            elif choice == '4':
                generate_dashboard_only()
            elif choice == '5':
                test_email()
            elif choice == '6':
                print("\n👋 Goodbye!")
                break
            else:
                print("\n❌ Invalid choice. Please select 1-6.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
        
        # Pause before showing menu again
        input("\n📎 Press Enter to continue...")

if __name__ == "__main__":
    main()
