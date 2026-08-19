#!/usr/bin/env python3
"""
smoke_test.py
Zero-cost pipeline validation — stubs the Anthropic API so the ENTIRE
pipeline (main.py -> generate_newsletter.py -> email_template.py) runs
end-to-end with fake data, including the exact code path that failed
in production last time (main.py's unpack of generate_newsletter()'s
return values).

Run this locally before every deploy:
    python smoke_test.py

It's also wired into the GitHub Actions workflow as a required step before
any real API calls, so a broken deploy fails for $0 instead of burning a
full run's worth of credits.

Exit code 0 = safe to run the real workflow. Non-zero = do NOT run it yet.
"""
import os
import sys
import traceback

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake-not-a-real-key")

import anthropic

# ── Canned Claude responses that mimic the real prompt contract exactly ─────
COUNTRY_RAW = """<h3>Executive Summary</h3>
<p>Smoke-test summary paragraph for validation purposes only.</p>

<h3>Major Incidents &amp; Breaches</h3>
<ul>
  <li data-severity="critical"><strong>Test Corp</strong> — 1 Jan 2026. Simulated incident for testing.</li>
  <li data-severity="medium"><strong>Test Bank</strong> — 5 Jan 2026. Simulated incident for testing.</li>
</ul>

<h3>Ransomware &amp; Extortion Activity</h3>
<p>No significant activity reported (simulated).</p>

<h3>Regulatory &amp; Legal Exposure</h3>
<p>No significant updates reported (simulated).</p>

<h3>Threat Intelligence &amp; Sector Risk</h3>
<ul>
  <li data-severity="high"><strong>Test APT</strong> — simulated threat intel item.</li>
</ul>

<h3>Board Takeaway</h3>
<p>This is a simulated takeaway for smoke-test purposes.</p>

---METADATA---
{"headline_stat": {"value": "2", "label": "Major Incidents"}, "headline_stat_secondary": {"value": "$1M", "label": "Estimated Losses"}, "trend_vs_last_month": "flat"}
---END---
"""

REGIONAL_RAW = """<h3>Regional Executive Briefing</h3>
<p>Simulated regional synthesis paragraph for smoke-test validation.</p>
<ul>
  <li><strong>Highest Severity:</strong> Simulated.</li>
  <li><strong>Cross-Border Pattern:</strong> None identified.</li>
  <li><strong>Regulatory Watch:</strong> None identified.</li>
</ul>

---METADATA---
{"regional_headline": "SMOKE TEST \u2014 Simulated regional headline."}
---END---
"""


class _FakeTextBlock:
    type = "text"
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]
        self.stop_reason = "end_turn"


def _fake_create(self, **kwargs):
    # Route on the real structural difference between the two call sites,
    # not prompt wording: research_country() always passes tools=[web_search],
    # _generate_regional_briefing() always passes tools=None. Matching on
    # system-prompt text content is fragile — a prompt edit that happens to
    # mention the other section's name (as ANALYST_SYSTEM legitimately does,
    # to describe tone consistency) can silently misroute the stub and mask
    # real bugs. This happened once already; keying off `tools` instead of
    # text content is what fixed it.
    if kwargs.get("tools"):
        return _FakeResponse(COUNTRY_RAW)
    return _FakeResponse(REGIONAL_RAW)


def _report(checks: dict) -> bool:
    print("\n=== SMOKE TEST RESULTS (zero API cost) ===")
    all_pass = True
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
        all_pass = all_pass and ok
    print("\n✅ SAFE TO RUN THE REAL WORKFLOW" if all_pass
          else "\n🛑 DO NOT RUN THE REAL WORKFLOW — fix the failures above first")
    return all_pass


def run():
    # Patch before anything imports/instantiates the real client.
    anthropic.resources.messages.Messages.create = _fake_create

    import generate_newsletter as gn
    gn.SLEEP_BETWEEN_COUNTRIES = 0  # no need to wait between stubbed calls

    checks = {}

    # ── Run the exact path that broke last time: main.py's --dry-run flow ──
    sys.argv = ["main.py", "--dry-run"]
    try:
        import main as main_module
        main_module.main()
        checks["main.py --dry-run completes without error"] = True
    except Exception as e:
        checks["main.py --dry-run completes without error"] = False
        print(f"\n[FATAL] main.py raised: {e}")
        traceback.print_exc()
        _report(checks)
        sys.exit(1)

    # ── Inspect the files main.py just wrote ─────────────────────────────────
    written_html = [f for f in os.listdir(".") if f.startswith("newsletter_") and f.endswith(".html")]
    written_pdf = [f for f in os.listdir(".") if f.startswith("newsletter_") and f.endswith(".pdf")]
    checks["newsletter HTML file was written"] = len(written_html) == 1
    checks["infographic PDF file was written"] = len(written_pdf) == 1

    if not written_html:
        _report(checks)
        sys.exit(1)

    html_path = written_html[0]
    html = open(html_path, encoding="utf-8").read()
    os.remove(html_path)  # clean up the test artifact

    if written_pdf:
        pdf_bytes = open(written_pdf[0], "rb").read()
        checks["infographic PDF starts with valid PDF header"] = pdf_bytes[:4] == b"%PDF"
        checks["infographic PDF is a reasonable size (>1KB)"] = len(pdf_bytes) > 1000
        os.remove(written_pdf[0])

    checks["all 12 country cards rendered"] = html.count('id="country-') == 12
    checks["no leftover data-severity attributes"] = "data-severity" not in html
    checks["no leftover ---METADATA--- markers"] = "---METADATA---" not in html
    checks["severity pill styling present"] = "background-color:#f85149" in html
    checks["regional briefing section present"] = "Regional Executive Briefing" in html
    checks["at least one QuickChart image URL present"] = "quickchart.io/chart?c=" in html

    ok = _report(checks)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run()
