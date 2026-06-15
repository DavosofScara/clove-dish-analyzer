# Outlook Authentication Troubleshooting Guide

## 🔑 **Current Issue**
The system is generating reports successfully but failing to send emails due to Outlook authentication issues.

## 🚨 **Error Details**
```
SMTP authentication failed: (535, b'5.7.3 Authentication unsuccessful')
```

## 🔍 **Common Causes & Solutions**

### 1. **Two-Factor Authentication (2FA) Enabled**
**Problem**: If 2FA is enabled, regular passwords won't work.
**Solution**: Generate an "App Password"
- Go to Microsoft Account → Security → Advanced Security Options
- Generate an app password for "Mail"
- Use this app password instead of your regular password

### 2. **Modern Authentication Required**
**Problem**: Outlook requires OAuth2 instead of basic authentication.
**Solution**: Use an app password or enable "Less secure app access"

### 3. **Account Security Settings**
**Problem**: Microsoft blocks "less secure apps" by default.
**Solution**: 
- Check if "Less secure app access" is enabled
- Or use an app-specific password

### 4. **Password Format Issues**
**Problem**: Special characters in password causing issues.
**Solution**: 
- Try URL-encoding special characters
- Use an app password instead

## 🛠️ **Immediate Solutions to Try**

### Option 1: App Password (Recommended)
1. Go to [Microsoft Account Security](https://account.microsoft.com/security)
2. Enable 2FA if not already enabled
3. Generate an app password for "Mail"
4. Update `email_config.py` with the app password

### Option 2: Enable Less Secure Apps
1. Go to [Microsoft Account Security](https://account.microsoft.com/security)
2. Look for "Less secure app access"
3. Enable it temporarily for testing

### Option 3: Check Account Status
1. Verify your account isn't locked
2. Check if you can log into Outlook web normally
3. Ensure the password is correct

## 📧 **Alternative Email Solutions**

### Option 1: Gmail SMTP
If Outlook continues to fail, we can switch to Gmail:
```python
EMAIL_CREDENTIALS = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'your_gmail@gmail.com',
    'sender_password': 'your_app_password',
    'use_tls': True
}
```

### Option 2: SendGrid or Mailgun
Professional email services with better deliverability.

## 🔧 **Testing Steps**

1. **Verify password manually**:
   ```bash
   # Test with a simple Python script
   python3 -c "
   import smtplib
   server = smtplib.SMTP('smtp.office365.com', 587)
   server.starttls()
   try:
       server.login('dave@clove.solutions', 'your_password')
       print('Login successful!')
   except Exception as e:
       print(f'Login failed: {e}')
   server.quit()
   "
   ```

2. **Check account status**:
   - Try logging into Outlook web
   - Check for any security notifications
   - Verify account isn't suspended

## 📋 **Next Steps**

1. **Try app password first** (most likely solution)
2. **Check Microsoft account security settings**
3. **Test with simple Python script**
4. **Consider alternative email service if needed**

## 📞 **Microsoft Support**

If issues persist:
- [Microsoft Account Help](https://support.microsoft.com/account-billing)
- [Outlook Support](https://support.microsoft.com/outlook)
- Check for any account-specific security requirements

---

**Note**: The automation system is working perfectly - it's generating reports and charts successfully. Only the email delivery needs to be resolved. 