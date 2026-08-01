#!/usr/bin/env python3
"""
APAC Cybersecurity Newsletter — Monthly Automation
Runs via GitHub Actions on the 1st of each month.
"""

import os
import sys
from datetime import datetime, timedelta
from generate_newsletter import generate_newsletter
from send_email import send_newsletter

def get_previous_month():
    today = datetime.now()
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)
    return last_month.strftime("%B"), last_month.year

def mask_email(email: str) -> str:
    """Masks an email address for safe logging, e.g. j***@gmail.com"""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = local + "***"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"

def print_recipients_preview():
    """Prints a masked recipient list/count from RECIPIENTS, if set. Safe for dry-runs and live runs."""
    raw = os.getenv("RECIPIENTS", "")
    recipients = [r.strip() for r in raw.split(",") if r.strip()]
    if not recipients:
        print("\n📧  RECIPIENTS: (not set / empty)")
        return recipients
    masked = [mask_email(r) for r in recipients]
    print(f"\n📧  RECIPIENTS ({len(recipients)}): {', '.join(masked)}")
    return recipients

def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("  APAC Cybersecurity Newsletter — Monthly Automation")
    if dry_run:
        print("  ⚠  DRY RUN — email will NOT be sent")
    print("=" * 60)

    # Dry runs still need ANTHROPIC_API_KEY; email vars only needed for live runs
    required = ["ANTHROPIC_API_KEY"]
    if not dry_run:
        required += ["GMAIL_USER", "GMAIL_APP_PASSWORD", "RECIPIENTS"]

    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Masked recipient preview — printed on every run (dry-run or live) so you
    # can always sanity-check who's configured without exposing full addresses
    # in the logs.
    print_recipients_preview()

    month, year = get_previous_month()
    print(f"\n📅  Generating newsletter for: {month} {year}\n")

    html, plain_text = generate_newsletter(month, year)

    output_path = f"newsletter_{month.lower()}_{year}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅  Newsletter saved to {output_path}")

    if dry_run:
        print("\n⏭  Dry run complete — skipping email send.")
        return

    recipients = [r.strip() for r in os.environ["RECIPIENTS"].split(",") if r.strip()]
    subject = f"APAC Cybersecurity — {month} {year} Monthly Retrospective"

    print(f"\n📧  Sending to {len(recipients)} recipient(s)...")
    print(f"    Masked list: {', '.join(mask_email(r) for r in recipients)}")
    send_newsletter(subject, html, plain_text, recipients)
    print("\n🎉  Done! Newsletter sent successfully.")

if __name__ == "__main__":
    main()
