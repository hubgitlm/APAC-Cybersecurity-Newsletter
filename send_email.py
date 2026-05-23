"""
send_email.py
Sends the newsletter via Gmail SMTP using an App Password.
Supports multiple recipients (BCC by default to protect privacy).
"""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid


def send_newsletter(
    subject: str,
    html_body: str,
    plain_body: str,
    recipients: list[str],
    bcc_mode: bool = True,
):
    """
    Send the newsletter email.

    Args:
        subject:     Email subject line.
        html_body:   Full HTML content.
        plain_body:  Plain-text fallback.
        recipients:  List of recipient email addresses.
        bcc_mode:    If True, sends all recipients as BCC (recommended).
                     If False, each recipient gets an individual email.
    """
    gmail_user     = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]

    if not recipients:
        raise ValueError("No recipients specified.")

    if bcc_mode:
        _send_batch(gmail_user, gmail_password, subject, html_body, plain_body, recipients)
    else:
        for recipient in recipients:
            _send_single(gmail_user, gmail_password, subject, html_body, plain_body, recipient)
            print(f"    ✉  Sent to {recipient}")


# ── Internal helpers ─────────────────────────────────────────────────────────

def _build_message(
    sender: str,
    to_field: str,
    subject: str,
    html_body: str,
    plain_body: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"APAC Cyber Newsletter <{sender}>"
    msg["To"]      = to_field
    msg["Date"]    = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])

    # Plain-text first, HTML second (email clients prefer the last part)
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))
    return msg


def _send_batch(
    sender: str,
    password: str,
    subject: str,
    html_body: str,
    plain_body: str,
    recipients: list[str],
):
    """Send one email with all recipients in BCC."""
    msg = _build_message(sender, sender, subject, html_body, plain_body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

    print(f"    ✉  Batch sent to {len(recipients)} recipient(s) via BCC")


def _send_single(
    sender: str,
    password: str,
    subject: str,
    html_body: str,
    plain_body: str,
    recipient: str,
):
    """Send individual email to a single recipient."""
    msg = _build_message(sender, recipient, subject, html_body, plain_body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())
