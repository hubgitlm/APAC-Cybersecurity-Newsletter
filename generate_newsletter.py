"""
generate_newsletter.py
Calls Claude (claude-sonnet-4-6) with web_search to research each country,
then assembles the full HTML newsletter.
Includes exponential backoff retry on 429 rate limit errors.
"""

import anthropic
import os
import time
import random
from datetime import datetime
from email_template import build_html, build_plain_text

# ── Countries & display config ──────────────────────────────────────────────
COUNTRIES = [
    {"name": "Singapore",    "flag": "🇸🇬", "code": "SG"},
    {"name": "Hong Kong",    "flag": "🇭🇰", "code": "HK"},
    {"name": "China",        "flag": "🇨🇳", "code": "CN"},
    {"name": "India",        "flag": "🇮🇳", "code": "IN"},
    {"name": "Philippines",  "flag": "🇵🇭", "code": "PH"},
    {"name": "Vietnam",      "flag": "🇻🇳", "code": "VN"},
    {"name": "Malaysia",     "flag": "🇲🇾", "code": "MY"},
    {"name": "Australia",    "flag": "🇦🇺", "code": "AU"},
    {"name": "South Korea",  "flag": "🇰🇷", "code": "KR"},
    {"name": "Indonesia",    "flag": "🇮🇩", "code": "ID"},
    {"name": "Japan",        "flag": "🇯🇵", "code": "JP"},
    {"name": "Taiwan",       "flag": "🇹🇼", "code": "TW"},
]

# Seconds to wait between countries (respects 30k tokens/min limit)
SLEEP_BETWEEN_COUNTRIES = 60

# ── System prompt ────────────────────────────────────────────────────────────
ANALYST_SYSTEM = """You are a senior cybersecurity analyst writing a professional monthly newsletter
for CISOs, security teams, and IT professionals across the Asia-Pacific region.

Your writing style:
- Clear, authoritative, and concise — no fluff
- Factual: cite incident names, affected organisations, dates, and CVE numbers where known
- Balanced: cover both public/private sector incidents
- Actionable: always end with a practical takeaway

When you write HTML, use ONLY these tags (no inline styles, no classes):
<h3>, <h4>, <p>, <ul>, <li>, <strong>, <em>, <a href="...">, <hr>

Never write <html>, <head>, <body>, <style>, or <script> tags.
Never add disclaimers like "I am an AI". Write as the analyst directly.
"""

def country_prompt(country: str, month: str, year: int) -> str:
    return f"""Search the web and write the cybersecurity retrospective section for **{country}** covering **{month} {year}**.

Use web search to find real incidents. Search for terms like:
- "{country} cyber attack {month} {year}"
- "{country} data breach {month} {year}"
- "{country} ransomware {month} {year}"
- "{country} cybersecurity law regulation {month} {year}"
- "{country} APT hacking {month} {year}"

Then write the section in this exact HTML structure:

<h3>Executive Summary</h3>
<p>[2-3 sentence overview of the cybersecurity landscape in {country} during {month} {year}.]</p>

<h3>Major Incidents &amp; Breaches</h3>
<ul>
  <li><strong>[Incident name / organisation]</strong> — [Date if known]. [What happened, scale, impact.]</li>
</ul>

<h3>Ransomware &amp; Malware Activity</h3>
<p>[Notable ransomware groups or malware campaigns. If none reported, state that clearly.]</p>

<h3>Regulatory &amp; Policy Updates</h3>
<p>[New cybersecurity laws, guidelines, or enforcement actions. If none, state that clearly.]</p>

<h3>Threat Intelligence Highlights</h3>
<p>[APT activity, CVEs, or sector-specific threats relevant to {country}.]</p>

<h3>Key Takeaway for Organisations</h3>
<p>[1-2 actionable sentences for organisations operating in {country}.]</p>

Be specific. Use real incident names from your search results."""


# ── API call with exponential backoff retry ──────────────────────────────────
def api_call_with_retry(client, messages, system, max_retries=5):
    """
    Wraps a Claude API call with exponential backoff on 429 errors.
    Waits 60s, 120s, 240s, 480s, 960s between retries.
    """
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=system,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages,
            )
        except anthropic.RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            wait = (60 * (2 ** attempt)) + random.uniform(0, 10)
            print(f"         ⏳ Rate limited. Waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}...", flush=True)
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code == 429:
                if attempt == max_retries - 1:
                    raise
                wait = (60 * (2 ** attempt)) + random.uniform(0, 10)
                print(f"         ⏳ Rate limited (429). Waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}...", flush=True)
                time.sleep(wait)
            else:
                raise


# ── Agentic research loop per country ───────────────────────────────────────
def research_country(client: anthropic.Anthropic, country: dict, month: str, year: int) -> str:
    messages = [{"role": "user", "content": country_prompt(country["name"], month, year)}]

    for iteration in range(12):
        response = api_call_with_retry(client, messages, ANALYST_SYSTEM)

        text_parts = [b.text for b in response.content if b.type == "text" and b.text.strip()]

        if response.stop_reason == "end_turn":
            return "\n".join(text_parts) if text_parts else _fallback(country["name"], month, year)

        if response.stop_reason == "max_tokens":
            print(f"         ⚠  Hit max_tokens on iteration {iteration + 1} "
                  f"({len(text_parts)} text block(s) so far)", flush=True)

        messages.append({"role": "assistant", "content": response.content})
        tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": getattr(block, "content", "") or "",
            }
            for block in response.content
            if block.type == "tool_use"
        ]
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            if not text_parts:
                print(f"         ⚠  No tool calls and no text on iteration {iteration + 1} "
                      f"(stop_reason={response.stop_reason})", flush=True)
            return "\n".join(text_parts) if text_parts else _fallback(country["name"], month, year)

    print(f"         ⚠  Exhausted all {iteration + 1} iterations without end_turn", flush=True)
    return _fallback(country["name"], month, year)


def _fallback(country: str, month: str, year: int) -> str:
    return (
        f"<h3>Executive Summary</h3>"
        f"<p>Cybersecurity data for {country} in {month} {year} could not be retrieved at this time. "
        f"Please consult national CERT advisories and threat intelligence feeds directly.</p>"
    )


# ── Main entry point ─────────────────────────────────────────────────────────
def generate_newsletter(month: str, year: int):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    sections = []
    total = len(COUNTRIES)

    for i, country in enumerate(COUNTRIES, 1):
        print(f"  [{i:02d}/{total}] Researching {country['flag']}  {country['name']} ...", flush=True)
        try:
            content = research_country(client, country, month, year)
            print(f"         ✓ Done", flush=True)
        except Exception as e:
            print(f"         ⚠  Failed for {country['name']}: {e}")
            content = _fallback(country["name"], month, year)

        sections.append({**country, "content": content})

        if i < total:
            print(f"         💤 Waiting {SLEEP_BETWEEN_COUNTRIES}s before next country...", flush=True)
            time.sleep(SLEEP_BETWEEN_COUNTRIES)

    generated_at = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    html       = build_html(month, year, sections, generated_at)
    plain_text = build_plain_text(month, year, sections)

    return html, plain_text
