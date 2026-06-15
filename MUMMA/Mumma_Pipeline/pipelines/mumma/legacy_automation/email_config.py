"""
Legacy Mumma automation email configuration.

IMPORTANT: Do not commit real email credentials. Populate the environment
variables below (via 1Password/Secrets Manager) and keep this file checked in
without plaintext secrets.

Supports both Hover (mail.hover.com) and Outlook SMTP.
Defaults to Hover if MUMMA_EMAIL_HOST is set, otherwise falls back to Outlook.
"""
import os


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


# Determine email provider: Gmail > Hover > Outlook
_use_gmail = bool(os.getenv("MUMMA_GMAIL_USER"))
_use_hover = bool(os.getenv("MUMMA_EMAIL_HOST") and "hover" in os.getenv("MUMMA_EMAIL_HOST", "").lower())

if _use_gmail:
    # Gmail SMTP configuration (recommended for sending to Gmail recipients)
    EMAIL_CREDENTIALS = {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_email": _env("MUMMA_GMAIL_USER"),
        "sender_password": _env("MUMMA_GMAIL_APP_PASSWORD"),  # Gmail app password required
        "recipient_email": os.getenv("MUMMA_EMAIL_RECIPIENT", "davevondavrosh@gmail.com"),
        "use_tls": True,
        "alternative_smtp": "smtp.gmail.com",
    }
elif _use_hover:
    # Hover SMTP configuration
    EMAIL_CREDENTIALS = {
        "smtp_server": os.getenv("MUMMA_EMAIL_SMTP_HOST", "mail.hover.com"),
        "smtp_port": int(os.getenv("MUMMA_EMAIL_SMTP_PORT", "587")),
        "sender_email": _env("MUMMA_EMAIL_USER"),  # Same as IMAP username
        "sender_password": _env("MUMMA_EMAIL_PASS"),  # Same as IMAP password (regular password, not app password)
        "recipient_email": os.getenv("MUMMA_EMAIL_RECIPIENT", "davevondavrosh@gmail.com"),
        "use_tls": os.getenv("MUMMA_EMAIL_SMTP_USE_TLS", "True").lower() == "true",
        "alternative_smtp": os.getenv("MUMMA_EMAIL_SMTP_ALT", "mail.hover.com"),
    }
else:
    # Outlook SMTP configuration (legacy fallback)
    EMAIL_CREDENTIALS = {
        "smtp_server": os.getenv("MUMMA_OUTLOOK_SMTP", "smtp.office365.com"),
        "smtp_port": int(os.getenv("MUMMA_OUTLOOK_PORT", "587")),
        "sender_email": _env("MUMMA_OUTLOOK_SENDER"),
        "sender_password": _env("MUMMA_OUTLOOK_APP_PASSWORD"),
        "recipient_email": os.getenv("MUMMA_OUTLOOK_RECIPIENT", "ops@clove.solutions"),
        "use_tls": True,
        "alternative_smtp": os.getenv("MUMMA_OUTLOOK_ALT_SMTP", "smtp-mail.outlook.com"),
    }

TEST_EMAIL = {
    "enabled": os.getenv("MUMMA_EMAIL_TEST_MODE", "false").lower() == "true",
    "test_recipient": os.getenv("MUMMA_EMAIL_TEST_RECIPIENT", EMAIL_CREDENTIALS["recipient_email"]),
}

EMAIL_TEMPLATES = {
    "subject": "MUMMA Sales Report - {date}",
    "body": (
        "Dear Team,\n\n"
        "Please find attached the MUMMA sales analysis report for {date}.\n\n"
        "This report contains:\n"
        "- Sales performance analysis\n"
        "- Top performing products\n"
        "- Revenue and quantity metrics\n"
        "- Visual charts and analysis\n"
        "- Dashboard data integration\n\n"
        "Best regards,\n"
        "MUMMA Automation System\n"
    ),
    "test_subject": "TEST - MUMMA Sales Report - {date}",
    "test_body": (
        "This is a TEST email from the MUMMA automation system.\n\n"
        "Please find attached the MUMMA sales analysis report for {date}.\n\n"
        "Best regards,\n"
        "MUMMA Automation System (TEST MODE)\n"
    ),
}

