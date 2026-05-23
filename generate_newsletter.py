"""
generate_newsletter.py
Calls Claude (claude-sonnet-4-6) with web_search to research each country,
then assembles the full HTML newsletter.
"""

import anthropic
import os
import time
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

# ── System prompt for the analyst persona ───────────────────────────────────
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

# ── Per-country research prompt ──────────────────────────────────────────────
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
<p>[2–3 sentence overview of the cybersecurity landscape in {country} during {month} {year}.]</p>

<h3>Major Incidents &amp; Breaches</h3>
<ul>
  <li><strong>[Incident name / organisation]</strong> — [Date if known]. [What happened, scale, impact. Include CVE or malware family if relevant.]</li>
  <!-- repeat for each notable incident; minimum 2, maximum 6 -->
</ul>

<h3>Ransomware &amp; Malware Activity</h3>
<p>[Notable ransomware groups, malware campaigns, or phishing waves targeting {country} organisations. 
If nothing significant, write "No major ransomware incidents were publicly reported in {country} during this period."]</p>

<h3>Regulatory &amp; Policy Updates</h3>
<p>[Any new cybersecurity laws, guidelines, government advisories, or notable enforcement actions. 
If none, write "No significant regulatory changes were announced during this period."]</p>

<h3>Threat Intelligence Highlights</h3>
<p>[State-sponsored groups, APT activity, vulnerability disclosures, or sector-specific threats relevant 
to {country}. Mention CVEs or threat actor names where confirmed.]</p>

<h3>Key Takeaway for Organisations</h3>
<p>[1–2 actionable sentences: what should organisations operating in {country} prioritise this month?]</p>

Be specific. Use real incident names from your search. If search results are sparse, note that openly 
rather than inventing details. Today's date context: you are writing about {month} {year}."""


# ── Agentic loop: handles tool_use blocks (web_search is server-side) ────────
def research_country(client: anthropic.Anthropic, country: dict, month: str, year: int) -> str:
    """
    Calls Claude with web_search enabled. Runs the tool-use loop until
    stop_reason == 'end_turn', then returns the final text content.
    """
    messages = [{"role": "user", "content": country_prompt(country["name"], month, year)}]

    for iteration in range(12):  # safety ceiling
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            system=ANALYST_SYSTEM,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )

        # Collect any text blocks from this turn
        text_parts = [b.text for b in response.content if b.type == "text" and b.text.strip()]

        if response.stop_reason == "end_turn":
            return "\n".join(text_parts) if text_parts else _fallback(country["name"], month, year)

        # stop_reason == "tool_use" — feed results back and continue
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
            # No tool calls but not end_turn — return what we have
            return "\n".join(text_parts) if text_parts else _fallback(country["name"], month, year)

    return _fallback(country["name"], month, year)


def _fallback(country: str, month: str, year: int) -> str:
    return (
        f"<h3>Executive Summary</h3>"
        f"<p>Cybersecurity data for {country} in {month} {year} could not be retrieved at this time. "
        f"Please consult national CERT advisories and threat intelligence feeds directly.</p>"
    )


# ── Main generation entry point ──────────────────────────────────────────────
def generate_newsletter(month: str, year: int):
    """
    Iterates over all countries, researches each one, builds final HTML + plain text.
    Returns (html_string, plain_text_string).
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    sections = []
    total = len(COUNTRIES)

    for i, country in enumerate(COUNTRIES, 1):
        print(f"  [{i:02d}/{total}] Researching {country['flag']}  {country['name']} ...", flush=True)
        try:
            content = research_country(client, country, month, year)
        except anthropic.APIError as e:
            print(f"         ⚠  API error for {country['name']}: {e}")
            content = _fallback(country["name"], month, year)

        sections.append({**country, "content": content})

        # Polite pacing — avoid burst rate limits
        if i < total:
            time.sleep(30)

    generated_at = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    html       = build_html(month, year, sections, generated_at)
    plain_text = build_plain_text(month, year, sections)

    return html, plain_text
