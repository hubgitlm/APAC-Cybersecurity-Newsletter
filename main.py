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


def _parse_country_limit(argv):
    """
    Parses --countries=N from argv, for cheap real-API smoke runs against
    only the first N countries instead of all 12. Returns None (= all
    countries) if the flag isn't present or isn't a valid positive int.
    """
    for arg in argv:
        if arg.startswith("--countries="):
            raw = arg.split("=", 1)[1].strip()
            if not raw:
                return None
            try:
                n = int(raw)
            except ValueError:
                print(f"[WARN] Ignoring invalid --countries value: {raw!r}")
                return None
            return n if n > 0 else None
    return None


def main():
    dry_run = "--dry-run" in sys.argv
    country_limit = _parse_country_limit(sys.argv)

    print("=" * 60)
    print("  APAC Cybersecurity Newsletter — Monthly Automation")
    if dry_run:
        print("  ⚠  DRY RUN — email will NOT be sent")
    if country_limit:
        print(f"  ⚠  LIMITED RUN — only the first {country_limit} countr{'y' if country_limit == 1 else 'ies'} will be researched")
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

    html, plain_text, headline, infographic_pdf = generate_newsletter(month, year, country_limit=country_limit)

    suffix = f"_partial{country_limit}" if country_limit else ""
    output_path = f"newsletter_{month.lower()}_{year}{suffix}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅  Newsletter saved to {output_path}")

    pdf_filename = None
    if infographic_pdf:
        pdf_filename = f"newsletter_{month.lower()}_{year}{suffix}_snapshot.pdf"
        with open(pdf_filename, "wb") as f:
            f.write(infographic_pdf)
        print(f"✅  Infographic snapshot saved to {pdf_filename}")
    else:
        print("⚠  No infographic snapshot was generated this run — email will send without a PDF attachment.")

    if dry_run:
        print("\n⏭  Dry run complete — skipping email send.")
        return

    recipients = [r.strip() for r in os.environ["RECIPIENTS"].split(",") if r.strip()]
    subject = headline.strip() if headline and headline.strip() else f"APAC Cybersecurity — {month} {year} Monthly Retrospective"
    if country_limit:
        subject = f"[TEST — {country_limit} countries] {subject}"

    print(f"\n📧  Sending to {len(recipients)} recipient(s)...")
    print(f"    Masked list: {', '.join(mask_email(r) for r in recipients)}")
    send_newsletter(
        subject, html, plain_text, recipients,
        attachment_bytes=infographic_pdf,
        attachment_filename=pdf_filename,
    )
    print("\n🎉  Done! Newsletter sent successfully.")


if __name__ == "__main__":
    main()
