"""
send_email.py
Sends the newsletter via Gmail SMTP using an App Password.
Supports multiple recipients (BCC by default to protect privacy) and an
optional PDF attachment (the one-page infographic snapshot).
"""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid


def send_newsletter(
    subject: str,
    html_body: str,
    plain_body: str,
    recipients: list[str],
    bcc_mode: bool = True,
    attachment_bytes: bytes = None,
    attachment_filename: str = None,
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
        attachment_bytes:    Optional PDF (or other) file bytes to attach.
        attachment_filename: Filename for the attachment, e.g.
                              "apac_cyber_snapshot_july_2026.pdf".
                              Required if attachment_bytes is provided.
    """
    gmail_user     = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]

    if not recipients:
        raise ValueError("No recipients specified.")

    if bcc_mode:
        _send_batch(gmail_user, gmail_password, subject, html_body, plain_body,
                     recipients, attachment_bytes, attachment_filename)
    else:
        for recipient in recipients:
            _send_single(gmail_user, gmail_password, subject, html_body, plain_body,
                          recipient, attachment_bytes, attachment_filename)
            print(f"    ✉  Sent to {recipient}")


# ── Internal helpers ─────────────────────────────────────────────────────────

def _build_message(
    sender: str,
    to_field: str,
    subject: str,
    html_body: str,
    plain_body: str,
    attachment_bytes: bytes = None,
    attachment_filename: str = None,
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"APAC Cyber Newsletter <{sender}>"
    msg["To"]      = to_field
    msg["Date"]    = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])

    # Text/HTML alternative body, nested inside the outer "mixed" container
    # so an attachment can sit alongside it.
    body = MIMEMultipart("alternative")
    body.attach(MIMEText(plain_body, "plain", "utf-8"))
    body.attach(MIMEText(html_body,  "html",  "utf-8"))
    msg.attach(body)

    if attachment_bytes and attachment_filename:
        part = MIMEApplication(attachment_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=attachment_filename)
        msg.attach(part)

    return msg


def _send_batch(
    sender: str,
    password: str,
    subject: str,
    html_body: str,
    plain_body: str,
    recipients: list[str],
    attachment_bytes: bytes = None,
    attachment_filename: str = None,
):
    """Send one email with all recipients in BCC."""
    msg = _build_message(sender, sender, subject, html_body, plain_body,
                          attachment_bytes, attachment_filename)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

    attach_note = f" with {attachment_filename} attached" if attachment_bytes else ""
    print(f"    ✉  Batch sent to {len(recipients)} recipient(s) via BCC{attach_note}")


def _send_single(
    sender: str,
    password: str,
    subject: str,
    html_body: str,
    plain_body: str,
    recipient: str,
    attachment_bytes: bytes = None,
    attachment_filename: str = None,
):
    """Send individual email to a single recipient."""
    msg = _build_message(sender, recipient, subject, html_body, plain_body,
                          attachment_bytes, attachment_filename)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())
