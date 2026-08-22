"""
generate_newsletter.py
Calls Claude (claude-sonnet-4-6) with web_search to research each country,
then a Haiku call to synthesize a cross-market "Regional Executive Briefing",
then assembles the full HTML newsletter.

Visual data model (Phase 1-2):
  - Country prompts ask Claude to tag each incident/ransomware/threat-intel
    <li> with a data-severity="critical|high|medium|low" attribute, and to
    append a small ---METADATA--- JSON block after the HTML.
  - generate_newsletter.py parses that HTML + metadata into a derived
    per-country dict (severity_counts, category_counts, headline stats).
  - QuickChart.io renders the small donut / stacked-bar charts on demand as
    plain <img> URLs — no image hosting or base64 embedding required.

Reliability layers (added after the July 2026 issue shipped with leaked
process narration and several mid-sentence truncations):
  1. Prompt-level: both system prompts explicitly forbid narration and
     markdown code fences.
  2. Per-response: _clean_content() strips anything before the first <h3>
     structurally (not by matching wording); _is_complete_country_section() /
     _is_complete_regional_section() / _ends_with_terminal_punctuation()
     reject any response that's missing a required heading or stops
     mid-sentence, falling back to clean placeholder content instead.
  3. Pre-send gate: validate_assembled_newsletter() runs once more over the
     fully stitched-together HTML as a final, independent check before
     main.py is allowed to call send_newsletter().

Includes exponential backoff retry on 429 rate limit errors.
"""

import anthropic
import os
import re
import json
import time
import random
import urllib.parse
from datetime import datetime
from email_template import build_html, build_plain_text
from infographic import build_infographic_html, render_infographic_pdf

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

SEVERITY_ORDER  = ["critical", "high", "medium", "low"]
# Muted, institutional-report palette rather than saturated "security
# product" tones — desaturated red/orange/gold/green that still carries
# clear severity signal (colour-coded risk indicators are standard in
# McKinsey/Deloitte-style research) without reading as a SIEM dashboard.
# Kept identical across generate_newsletter.py, infographic.py, and
# email_template.py so charts, pills, and tiles all agree visually.
SEVERITY_COLORS = {
    "critical": "#a13529",
    "high":     "#b0692c",
    "medium":   "#9c7f2a",
    "low":      "#2f7a52",
}

CATEGORY_SECTION_MAP = [
    ("Major Incidents", "incidents"),
    ("Ransomware", "ransomware"),
    ("Regulatory", "regulatory"),
    ("Threat Intelligence", "threat_intel"),
]

# ── System prompt ────────────────────────────────────────────────────────────
ANALYST_SYSTEM = """You are a senior cybersecurity risk advisor writing the country-level sections of
a monthly APAC board briefing for company boards and executive leadership (CEOs, CFOs, general
counsel, non-technical directors) — not for CISOs or security teams. This must read consistently
with the regional synthesis section that sits above it in the same document, which is written
for the same board audience.

Your writing style:
- Business-first: lead every point with impact — cost, downtime, customer harm, legal/regulatory
  exposure, reputational effect — not attack mechanics.
- Plain English: if you must use a technical term (ransomware, zero-day, MFA, APT, double-extortion,
  RaaS, supply-chain risk, credential-based attack, OT/ICS), immediately gloss it in one short clause
  a non-technical reader understands — every time it first appears in THIS section, even if you
  believe an earlier country's section already defined it. Each country section is read
  independently and must stand alone. Where the term appears in the STANDARD GLOSSARY below, use
  that exact definition (or a very close paraphrase of it) rather than improvising your own wording
  — this keeps definitions worded consistently across all twelve countries in the same issue, so a
  reader who jumps between sections isn't given two different explanations of the same term.

STANDARD GLOSSARY — use these definitions verbatim or near-verbatim on first use of each term:
- Ransomware: malicious software that locks an organisation's systems and/or steals its data, then
  demands payment to restore access or to prevent the data being published.
- Double-extortion: when attackers both encrypt a victim's systems AND steal data before demanding
  payment — meaning restoring from backup alone does not remove the risk of stolen data being leaked.
- Ransomware-as-a-Service (RaaS): a criminal business model where ransomware tools are rented out to
  other attackers, which is why the same ransomware "brand" can strike many unrelated victims at once.
- Zero-day: a software flaw that attackers exploit before the vendor has issued a fix, meaning no
  patch was available at the time of the attack.
- Multi-factor authentication (MFA): a login security step beyond a password (e.g. a code sent to a
  phone) that significantly reduces the risk of a stolen password being used to break in.
- Advanced Persistent Threat (APT): a sophisticated, typically state-linked attacker group that
  maintains long-term, hard-to-detect access to a target's systems, usually for espionage rather than
  quick financial gain.
- OT/ICS (Operational Technology / Industrial Control Systems): the computer systems that run
  physical equipment — power grids, factory lines, water treatment — where an attack can cause
  physical disruption or a safety incident, not just data loss.
- Supply-chain risk: exposure that comes from a vendor, contractor, or software provider being
  compromised, even when the organisation's own systems were never directly breached.
- Credential-based attack: an intrusion that starts from a stolen, guessed, or purchased password or
  login session, rather than a technical flaw in software.
- Phishing: deceptive emails or messages designed to trick an employee into revealing credentials or
  installing malicious software.
- DDoS (Distributed Denial-of-Service): flooding a website or system with traffic to knock it
  offline — disrupting service rather than stealing data.
- Data exfiltration: the unauthorised copying or removal of data from an organisation's systems —
  often the real risk in a ransomware incident, distinct from the systems being locked.
- Dark web: hidden parts of the internet, not indexed by ordinary search engines, often used by
  criminals to sell stolen data or coordinate attacks.
- Third-party/vendor risk: exposure that arises because a supplier, contractor, or service provider
  holding an organisation's data or with access to its systems has been compromised.
- Business Email Compromise (BEC): a scam where attackers impersonate an executive or supplier by
  email to trick staff into making a fraudulent payment or transfer.

- Clear, authoritative, and concise — no fluff.
- Factual: cite incident names, affected organisations, dates, and financial/operational scale
  where reported (cost, records affected, days of downtime) — not CVE numbers or technical
  campaign detail, which belong in a security team's briefing, not a board's.
- Balanced: cover both public/private sector incidents.
- End with a decision the board should make or a question it should ask management — not a
  technical instruction to an IT team.

When you write HTML, use ONLY these tags (no inline styles beyond what is specified below, no classes):
<h3>, <h4>, <p>, <ul>, <li>, <strong>, <em>, <a href="...">, <hr>

Every <li> inside "Major Incidents & Breaches", "Ransomware & Extortion Activity" (only if you list
specific campaigns), and "Threat Intelligence & Sector Risk" MUST carry a data-severity attribute
reflecting the real-world impact of that item, e.g.:
<li data-severity="critical"><strong>Org Name</strong> — 12 Mar 2026. What happened...</li>

Allowed severity values, choose the one that best matches the item: critical, high, medium, low.
Base the rating on scale of impact (records exposed, sectors affected, criticality of systems),
not on how dramatic the write-up sounds. Never omit data-severity from a tagged <li>.

Never write <html>, <head>, <body>, <style>, or <script> tags.
Never add disclaimers like "I am an AI". Write as the advisor directly.

CRITICAL OUTPUT RULE: Your response must contain ONLY the HTML section content described below,
followed by the metadata block. Do not narrate your research process, do not describe what you are
about to do or have just done (e.g. "I'll search for...", "Let me compile...", "I now have..."), and
do not wrap the output in markdown code fences (no ``` anywhere in your response). Your first
character must be the opening `<` of the first `<h3>` tag — nothing before it.

After the HTML, append a metadata block in exactly this format (real JSON, no markdown fences):

---METADATA---
{"headline_stat": {"value": "3", "label": "Major Incidents"}, "headline_stat_secondary": null, "trend_vs_last_month": "unknown"}
---END---

Rules for the metadata block:
- headline_stat.value/label: the single most newsworthy count from this month (e.g. incident count,
  breach count). Always populate this.
- headline_stat_secondary: only populate with a real reported dollar/financial figure if one was
  found in your research (e.g. {"value": "$14M", "label": "Estimated Losses"}). Otherwise use null.
  Never invent a number.
- trend_vs_last_month: always "unknown" unless you were explicitly given last month's figures to
  compare against.
"""

def country_prompt(country: str, month: str, year: int) -> str:
    return f"""Search the web and write the board-level cybersecurity briefing section for **{country}** covering **{month} {year}**.

Use web search to find real incidents. Search for terms like:
- "{country} cyber attack {month} {year}"
- "{country} data breach {month} {year}"
- "{country} ransomware {month} {year}"
- "{country} cybersecurity law regulation {month} {year}"
- "{country} APT hacking {month} {year}"

Then write the section in this exact HTML structure. Remember: this is for a board member, not a
security engineer — every point should answer "why should a director in {country} care about
this, and what could it cost the business?"

<h3>Executive Summary</h3>
<p>[2-3 sentence overview of what mattered for businesses in {country} during {month} {year}, in
business-impact terms.]</p>

<h3>Major Incidents &amp; Breaches</h3>
<ul>
  <li data-severity="[critical|high|medium|low]"><strong>[Organisation / incident name]</strong> — [Date if known]. [What happened, in plain English, and the business impact: cost, customers/records affected, downtime, reputational or legal consequence.]</li>
</ul>

<h3>Ransomware &amp; Extortion Activity</h3>
<p>[What board members need to know about ransomware trends this month — in terms of business
disruption risk, not technical campaign detail. If none reported, state that clearly.]</p>

<h3>Regulatory &amp; Legal Exposure</h3>
<p>[New laws, guidelines, or enforcement actions — framed as what changes for board liability,
disclosure timelines, or fines. If none, state that clearly.]</p>

<h3>Threat Intelligence &amp; Sector Risk</h3>
<p>[Which industries in {country} were most targeted or most at risk this month, and why that
matters for businesses in adjacent sectors — plain English, no unexplained technical jargon.
Structure this section to explicitly address, where the month's research supports it: financial
services; healthcare (framed around patient safety and care continuity, not only data privacy);
energy, utilities & transport (framed around physical/operational safety and service continuity
where relevant — not only IT breach impact); and government & public sector. Do not let financial
services crowd out the other three — if a sector had no material development this month, say so in
one short clause rather than omitting it entirely.]</p>

<h3>Board Takeaway</h3>
<p>[One question the board should put to management, or one decision it should make, based on
this month's developments in {country}.]</p>

Then append the ---METADATA--- block as instructed in your system prompt.

Be specific. Use real incident names from your search results."""


# ── Regional briefing (Haiku, no web search — reasons over the digest only) ──
REGIONAL_SYSTEM = """You are a senior cybersecurity risk advisor producing the lead section of a
monthly APAC cybersecurity board briefing. You are given a compact digest of per-country
severity counts, category counts, and executive summaries that another advisor already
researched this month, writing in the same board-first voice you use here. You do not have web
search — reason only from the digest provided.

Write in this exact HTML structure, using ONLY these tags: <h3>, <p>, <ul>, <li>, <strong>.

<h3>Regional Executive Briefing</h3>
<p>[3-4 sentence cross-market synthesis of the region's cybersecurity posture this month. Write for
a board of directors, not a security team: plain business language, no unexplained technical jargon
(gloss any term you must use), and frame implications in terms of business risk, liability, and
operational impact rather than technical mechanics. This paragraph is displayed on its own on a
board-briefing document, so it must stand alone and read as a complete executive summary.]</p>
<ul>
  <li><strong>Highest Severity:</strong> [country/countries] — [why, based on the digest].</li>
  <li><strong>Cross-Border Pattern:</strong> [a shared threat actor, campaign, or vector appearing
      in multiple countries' summaries, or "None identified" if genuinely none stands out].</li>
  <li><strong>Regulatory Watch:</strong> [a regulatory pattern spanning multiple countries, or
      "None identified"].</li>
</ul>

Then append exactly:
---METADATA---
{"regional_headline": "[a single punchy sentence, board-readable, summarising the region's risk this month]"}
---END---

The regional_headline must be a genuinely short, complete sentence — 100 characters or fewer,
including spaces. It appears on its own on a one-page printed snapshot with no room to wrap beyond
two lines, so do not write a long compound sentence and expect it to be cut off; write it short in
the first place.

Never invent incidents or figures not present in the digest. If the digest doesn't support a
cross-border pattern or regulatory pattern, say "None identified" rather than fabricating one.
Never add disclaimers like "I am an AI".

CRITICAL OUTPUT RULE: Your response must contain ONLY the HTML content described above, followed by
the metadata block. Do not narrate your process (no "Let me compile...", "I now have..."), and do
not wrap your output in markdown code fences. Your first character must be the opening `<` of
`<h3>Regional Executive Briefing</h3>` — nothing before it.
"""

def regional_prompt(digest: str) -> str:
    return f"""Here is this month's per-country digest:

{digest}

Write the Regional Executive Briefing section as instructed in your system prompt."""


# ── API call with exponential backoff retry ──────────────────────────────────
def api_call_with_retry(client, messages, system, model="claude-sonnet-4-6",
                         max_tokens=2500, tools=None, max_retries=5):
    """
    Wraps a Claude API call with exponential backoff on 429 errors.
    Waits 60s, 120s, 240s, 480s, 960s between retries.
    """
    kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
    if tools:
        kwargs["tools"] = tools

    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
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


# ── Parsing helpers ──────────────────────────────────────────────────────────

REQUIRED_COUNTRY_HEADINGS = [
    "<h3>Executive Summary</h3>",
    "<h3>Major Incidents &amp; Breaches</h3>",
    "<h3>Ransomware &amp; Extortion Activity</h3>",
    "<h3>Regulatory &amp; Legal Exposure</h3>",
    "<h3>Threat Intelligence &amp; Sector Risk</h3>",
    "<h3>Board Takeaway</h3>",
]

_CODE_FENCE_RE = re.compile(r"```(?:html)?", re.IGNORECASE)


def _clean_content(raw: str) -> str:
    """
    Strips process narration ("I'll run all five searches...", "Let me
    compile...") and stray markdown code fences that sometimes wrap
    Claude's HTML output, using STRUCTURE as the anchor point rather than
    matching on wording — consistent with how the smoke-test stub routes on
    the `tools` kwarg instead of prompt text (a wording-based filter is
    fragile and silently breaks the next time Claude phrases the same
    narration slightly differently).

    The prompt contract guarantees real content always starts with the
    first <h3> tag, so anything before that first <h3> — preamble sentences
    or a leading ```html fence — is always safe to discard.
    """
    text = _CODE_FENCE_RE.sub("", raw).strip()
    first_heading = text.find("<h3")
    if first_heading > 0:
        text = text[first_heading:]
    return text.strip()


def _is_complete_country_section(content: str) -> bool:
    """Structural completeness check: every required heading must be
    present. Catches truncation (stop_reason == 'max_tokens') even when the
    response still parses as non-empty HTML — a partial section with 4 of 6
    headings is not something we ship to a board audience."""
    return all(h in content for h in REQUIRED_COUNTRY_HEADINGS)


def _is_complete_regional_section(content: str) -> bool:
    return (
        "<h3>Regional Executive Briefing</h3>" in content
        and "Highest Severity" in content
        and "Cross-Border Pattern" in content
        and "Regulatory Watch" in content
    )


def _ends_with_terminal_punctuation(content: str) -> bool:
    """
    A section that hit max_tokens mid-sentence can still contain every
    required heading (e.g. truncation lands right after 'Board Takeaway'
    opens but before its sentence finishes) — heading-completeness alone
    won't catch that. This checks the very last visible character of the
    section, so a response that ends "...the board" with no closing
    punctuation is caught even when _is_complete_country_section() passes.
    """
    plain = re.sub(r"<[^>]+>", "", content).strip()
    return bool(plain) and plain[-1] in ".!?\u201d\""


def _extract_metadata(raw: str):
    """Splits off the ---METADATA--- {...} ---END--- block. Returns (content, metadata_dict)."""
    match = re.search(r"---METADATA---\s*(\{.*?\})\s*---END---", raw, re.DOTALL)
    if not match:
        return raw.strip(), {}
    content = raw[:match.start()].strip()
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError:
        metadata = {}
    return content, metadata


def _parse_severity_counts(html: str) -> dict:
    counts = {k: 0 for k in SEVERITY_ORDER}
    for sev in re.findall(r'data-severity="(\w+)"', html):
        sev = sev.lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def _parse_category_counts(html: str) -> dict:
    """Rough count of <li> items within each named h3 section."""
    categories = {"incidents": 0, "ransomware": 0, "regulatory": 0, "threat_intel": 0}
    chunks = re.split(r"<h3>", html)
    for chunk in chunks:
        for keyword, key in CATEGORY_SECTION_MAP:
            if chunk.strip().startswith(keyword):
                categories[key] = len(re.findall(r"<li", chunk))
    return categories


def _extract_executive_summary(html: str) -> str:
    match = re.search(r"<h3>Executive Summary</h3>\s*<p[^>]*>(.*?)</p>", html, re.DOTALL)
    if not match:
        return ""
    return re.sub(r"<[^>]+>", "", match.group(1)).strip()


def _extract_tagged_items(html: str) -> list:
    """
    Returns every severity-tagged incident as plain text, in document order:
    [{"severity": "critical", "text": "Org Name — 5 Mar 2026. What happened..."}, ...]
    Feeds the infographic's watchlist without needing a separate API call.
    """
    items = []
    for m in re.finditer(r'<li data-severity="(\w+)">(.*?)</li>', html, re.DOTALL):
        severity = m.group(1).lower()
        if severity not in SEVERITY_ORDER:
            continue
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        text = re.sub(r"\s+", " ", text)
        items.append({"severity": severity, "text": text})
    return items


def _extract_labeled_items(html: str) -> dict:
    """
    Parses <li><strong>Label:</strong> text</li> items (used in the Regional
    Briefing's Highest Severity / Cross-Border Pattern / Regulatory Watch
    bullets) into {label: text}.
    """
    result = {}
    for m in re.finditer(r"<li><strong>([^<:]+):</strong>\s*(.*?)</li>", html, re.DOTALL):
        label = m.group(1).strip()
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        result[label] = text
    return result


# ── QuickChart URL builders (no hosting needed — chart config lives in the URL) ──
def _quickchart_url(chart_config: dict, width=140, height=140, bg="transparent") -> str:
    encoded = urllib.parse.quote(json.dumps(chart_config, separators=(",", ":")))
    return f"https://quickchart.io/chart?c={encoded}&backgroundColor={bg}&width={width}&height={height}&devicePixelRatio=2"


def build_donut_chart_url(severity_counts: dict) -> str:
    total = sum(severity_counts.values())
    if total == 0:
        return ""
    config = {
        "type": "doughnut",
        "data": {
            "labels": [s.capitalize() for s in SEVERITY_ORDER],
            "datasets": [{
                "data": [severity_counts.get(s, 0) for s in SEVERITY_ORDER],
                "backgroundColor": [SEVERITY_COLORS[s] for s in SEVERITY_ORDER],
                "borderWidth": 0,
            }],
        },
        "options": {
            "plugins": {"legend": {"display": False}, "datalabels": {"display": False}},
            "cutoutPercentage": 68,
        },
    }
    return _quickchart_url(config, width=120, height=120)


def build_regional_bar_url(sections: list) -> str:
    labels = [f"{c['flag']} {c['code']}" for c in sections]
    datasets = [
        {
            "label": sev.capitalize(),
            "data": [c["severity_counts"].get(sev, 0) for c in sections],
            "backgroundColor": SEVERITY_COLORS[sev],
        }
        for sev in SEVERITY_ORDER
    ]
    # Horizontal, not vertical: 12 country labels crammed onto an x-axis
    # were illegible at the width this chart actually renders in an email
    # client (especially on mobile, where most executives read). As a
    # horizontal bar, each country gets its own labeled row instead of a
    # squeezed tick label, and it scales down gracefully on narrow screens.
    config = {
        "type": "horizontalBar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "scales": {
                "xAxes": [{"stacked": True, "ticks": {"fontColor": "#5a6478", "fontSize": 12, "precision": 0}}],
                "yAxes": [{"stacked": True, "ticks": {"fontColor": "#1b2436", "fontSize": 13}}],
            },
            "legend": {"position": "bottom", "labels": {"fontColor": "#1b2436", "fontSize": 12}},
        },
    }
    return _quickchart_url(config, width=680, height=460, bg="white")


# ── Agentic research loop per country ───────────────────────────────────────
def research_country(client: anthropic.Anthropic, country: dict, month: str, year: int) -> dict:
    messages = [{"role": "user", "content": country_prompt(country["name"], month, year)}]

    for _iteration in range(12):
        response = api_call_with_retry(
            client, messages, ANALYST_SYSTEM,
            # 2500 was too tight for a 6-section, severity-tagged report plus
            # the trailing metadata block — Sonnet was hitting the ceiling
            # mid-sentence and the loop was shipping the partial text as
            # final output. Raised back to 4000 (the previously-established
            # budget) now that _is_complete_country_section() also exists as
            # a backstop if a section is still ever too long to finish here.
            model="claude-sonnet-4-6", max_tokens=4000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )

        text_parts = [b.text for b in response.content if b.type == "text" and b.text.strip()]

        if response.stop_reason == "end_turn":
            raw = "\n".join(text_parts) if text_parts else None
            return _build_country_result(raw, country["name"], month, year)

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
            if response.stop_reason != "end_turn":
                print(
                    f"         ⚠  {country['name']} stopped early "
                    f"(stop_reason={response.stop_reason}) — likely hit the "
                    f"max_tokens ceiling. Output will be checked for "
                    f"completeness and may fall back if truncated.",
                    flush=True,
                )
            raw = "\n".join(text_parts) if text_parts else None
            return _build_country_result(raw, country["name"], month, year)

    print(f"         ⚠  {country['name']} exhausted the 12-iteration research loop without finishing.", flush=True)
    return _build_country_result(None, country["name"], month, year)


def _build_country_result(raw, country: str, month: str, year: int) -> dict:
    if not raw:
        return _fallback(country, month, year)

    raw = _clean_content(raw)
    content, metadata = _extract_metadata(raw)

    if (
        not content.strip()
        or not _is_complete_country_section(content)
        or not _ends_with_terminal_punctuation(content)
    ):
        print(
            f"         ⚠  {country} output was empty, incomplete (missing a "
            f"required section), or didn't end on a finished sentence — "
            f"using fallback content instead of shipping a truncated section.",
            flush=True,
        )
        return _fallback(country, month, year)

    return {
        "content": content,
        "severity_counts": _parse_severity_counts(content),
        "category_counts": _parse_category_counts(content),
        "executive_summary": _extract_executive_summary(content),
        "headline_stat": metadata.get("headline_stat"),
        "headline_stat_secondary": metadata.get("headline_stat_secondary"),
        "trend": metadata.get("trend_vs_last_month", "unknown"),
    }


def _fallback(country: str, month: str, year: int) -> dict:
    content = (
        f"<h3>Executive Summary</h3>"
        f"<p>Cybersecurity data for {country} in {month} {year} could not be retrieved at this time. "
        f"Please consult national CERT advisories and threat intelligence feeds directly.</p>"
    )
    return {
        "content": content,
        "severity_counts": {k: 0 for k in SEVERITY_ORDER},
        "category_counts": {"incidents": 0, "ransomware": 0, "regulatory": 0, "threat_intel": 0},
        "executive_summary": f"Data unavailable for {country} this month.",
        "headline_stat": None,
        "headline_stat_secondary": None,
        "trend": "unknown",
    }


# ── Regional Executive Briefing (Haiku primary, Sonnet fallback) ────────────
def _generate_regional_briefing(client: anthropic.Anthropic, sections: list):
    digest_lines = [
        f"{c['name']}: severity={c['severity_counts']}, categories={c['category_counts']}, "
        f"summary=\"{c.get('executive_summary', '')}\""
        for c in sections
    ]
    digest = "\n".join(digest_lines)
    prompt = regional_prompt(digest)

    # 1200 -> 1800: leaves headway for the 3-4 sentence synthesis paragraph,
    # three detailed watch-list bullets, and the metadata block without
    # crowding the regional_headline out or truncating the last bullet.
    attempts = [("claude-haiku-4-5-20251001", 1800), ("claude-sonnet-4-6", 1800)]
    for model, max_tokens in attempts:
        try:
            response = api_call_with_retry(
                client, [{"role": "user", "content": prompt}], REGIONAL_SYSTEM,
                model=model, max_tokens=max_tokens, tools=None, max_retries=2,
            )
            raw = "\n".join(b.text for b in response.content if b.type == "text" and b.text.strip())
            raw = _clean_content(raw)
            content, metadata = _extract_metadata(raw)
            if (
                content.strip()
                and _is_complete_regional_section(content)
                and _ends_with_terminal_punctuation(content)
            ):
                return {"content": content, "headline": metadata.get("regional_headline", "")}
            print(f"    ⚠  Regional briefing from {model} was empty, incomplete, or didn't end on a finished sentence.")
        except Exception as e:
            print(f"    ⚠  Regional briefing attempt failed ({model}): {e}")

    print("    ⚠  Regional briefing omitted — all attempts failed.")
    return None


# ── Pre-send validation gate ─────────────────────────────────────────────────
# Per-section checks above (_is_complete_country_section,
# _ends_with_terminal_punctuation) catch problems with a single model
# response. This is a second, independent layer that runs on the FULLY
# ASSEMBLED newsletter — it catches anything that could only surface once
# everything is stitched together (an assembly bug dropping a card,
# duplicate leakage the per-section checks missed) rather than trusting
# that per-section checks alone are sufficient. main.py treats a non-empty
# result from this as a hard stop before send_newsletter() is ever called.
LEAK_PHRASES = [
    "i'll run", "i will run", "i now have", "let me compile", "let me now compile",
    "now let me do", "let me search", "i'll search", "i will search",
    "let me write the", "here is the complete", "i'll now", "let me now write",
    "let me do one more", "i'll also", "let me also",
]


def validate_assembled_newsletter(html: str, sections: list, regional: dict | None) -> list[str]:
    """Returns a list of human-readable problems; an empty list means the
    assembled newsletter is safe to send."""
    problems = []
    lowered = html.lower()

    for phrase in LEAK_PHRASES:
        if phrase in lowered:
            problems.append(f'Possible leaked process narration in assembled HTML: "{phrase}"')

    if "```" in html:
        problems.append("Leftover markdown code fence (```) found in assembled HTML.")
    if "---metadata---" in lowered:
        problems.append("Leftover ---METADATA--- marker found in assembled HTML.")
    if "data-severity=" in html:
        problems.append("Unstyled data-severity attribute leaked into assembled HTML (should have become a severity pill).")

    expected_cards = len(sections)
    actual_cards = html.count('id="country-')
    if actual_cards != expected_cards:
        problems.append(f"Expected {expected_cards} country cards in assembled HTML, found {actual_cards}.")

    if regional and regional.get("content") and "Regional Executive Briefing" not in html:
        problems.append("Regional briefing was generated but is missing from the assembled HTML.")

    return problems


# ── Main entry point ─────────────────────────────────────────────────────────
def generate_newsletter(month: str, year: int, country_limit: int | None = None):
    """
    country_limit: if set, only researches the first N countries in COUNTRIES
    and skips the regional briefing if fewer than 2 countries are present
    (a single-country digest isn't useful for cross-market synthesis).
    Intended for cheap real-API smoke runs — leave as None for full runs.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    countries_to_run = COUNTRIES[:country_limit] if country_limit else COUNTRIES
    sections = []
    total = len(countries_to_run)

    for i, country in enumerate(countries_to_run, 1):
        print(f"  [{i:02d}/{total}] Researching {country['flag']}  {country['name']} ...", flush=True)
        try:
            result = research_country(client, country, month, year)
            print(f"         ✓ Done", flush=True)
        except Exception as e:
            print(f"         ⚠  Failed for {country['name']}: {e}")
            result = _fallback(country["name"], month, year)

        section = {**country, **result}
        section["chart_url"] = build_donut_chart_url(section["severity_counts"])
        sections.append(section)

        if i < total:
            print(f"         💤 Waiting {SLEEP_BETWEEN_COUNTRIES}s before next country...", flush=True)
            time.sleep(SLEEP_BETWEEN_COUNTRIES)

    if len(sections) >= 2:
        print("  [Regional] Synthesizing cross-market briefing ...", flush=True)
        regional = _generate_regional_briefing(client, sections)
        regional_chart_url = build_regional_bar_url(sections)
        print("         ✓ Done" if regional else "         ⚠  Skipped", flush=True)
    else:
        print("  [Regional] Skipped — need at least 2 countries for cross-market synthesis.", flush=True)
        regional = None
        regional_chart_url = ""

    generated_at = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    html = build_html(
        month, year, sections, generated_at,
        regional=regional, regional_chart_url=regional_chart_url,
    )
    plain_text = build_plain_text(month, year, sections, regional=regional)

    headline = ""
    if regional and regional.get("headline"):
        headline = regional["headline"].strip()
    if not headline:
        headline = f"APAC Cybersecurity — {month} {year} Monthly Retrospective"

    print("  [Infographic] Rendering one-page PDF snapshot ...", flush=True)
    infographic_pdf = None
    try:
        infographic_html = build_infographic_html(month, year, sections, regional, regional_chart_url)
        infographic_pdf = render_infographic_pdf(infographic_html)
        print(f"         ✓ Done ({len(infographic_pdf):,} bytes)", flush=True)
    except Exception as e:
        print(f"         ⚠  Infographic PDF failed, continuing without it: {e}", flush=True)
        infographic_pdf = None

    validation_problems = validate_assembled_newsletter(html, sections, regional)
    if validation_problems:
        print("  [Validation] ⚠  Pre-send checks found issues:", flush=True)
        for problem in validation_problems:
            print(f"                - {problem}", flush=True)
    else:
        print("  [Validation] ✓ Pre-send checks passed.", flush=True)

    return html, plain_text, headline, infographic_pdf, validation_problems
