from __future__ import annotations

import base64
import logging
from typing import List

import requests

logger = logging.getLogger(__name__)


def send_email(
    subject: str,
    html: str,
    api_key: str,
    email_from: str,
    recipients: List[str],
    *,
    attach_html_copy: bool = True,
    html_attachment_filename: str = "rapport_evolution2_hebdomadaire.html",
) -> None:
    if not recipients:
        raise ValueError("No recipients: set RECIPIENT_EMAIL or RECIPIENT_EMAILS in .env")

    url = "https://api.resend.com/emails"
    payload: dict = {
        "from": email_from,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if attach_html_copy:
        # Forwards/replies often re-sanitize inline HTML; the attachment survives and opens at full fidelity in a browser.
        payload["attachments"] = [
            {
                "filename": html_attachment_filename,
                "content": base64.b64encode(html.encode("utf-8")).decode("ascii"),
                "content_type": "text/html; charset=utf-8",
            }
        ]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code >= 300:
        logger.error("Resend error (%s): %s", resp.status_code, resp.text)
        raise RuntimeError(f"Resend error: {resp.text}")

    logger.info("Email sent to %s", ", ".join(recipients))
