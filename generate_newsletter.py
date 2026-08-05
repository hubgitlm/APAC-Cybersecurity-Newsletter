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
SEVERITY_COLORS = {
    "critical": "#f85149",
    "high":     "#db6d28",
    "medium":   "#d29922",
    "low":      "#3fb950",
}

CATEGORY_SECTION_MAP = [
    ("Major Incidents", "incidents"),
    ("Ransomware", "ransomware"),
    ("Regulatory", "regulatory"),
    ("Threat Intelligence", "threat_intel"),
]

# ── System prompt ────────────────────────────────────────────────────────────
ANALYST_SYSTEM = """You are a senior cybersecurity analyst writing a professional monthly newsletter
for CISOs, security teams, and IT professionals across the Asia-Pacific region.

Your writing style:
- Clear, authoritative, and concise — no fluff
- Factual: cite incident names, affected organisations, dates, and CVE numbers where known
- Balanced: cover both public/private sector incidents
- Actionable: always end with a practical takeaway

When you write HTML, use ONLY these tags (no inline styles beyond what is specified below, no classes):
<h3>, <h4>, <p>, <ul>, <li>, <strong>, <em>, <a href="...">, <hr>

Every <li> inside "Major Incidents & Breaches", "Ransomware & Malware Activity" (only if you list
specific campaigns), and "Threat Intelligence Highlights" MUST carry a data-severity attribute
reflecting the real-world impact of that item, e.g.:
<li data-severity="critical"><strong>Org Name</strong> — 12 Mar 2026. What happened...</li>

Allowed severity values, choose the one that best matches the item: critical, high, medium, low.
Base the rating on scale of impact (records exposed, sectors affected, criticality of systems),
not on how dramatic the write-up sounds. Never omit data-severity from a tagged <li>.

Never write <html>, <head>, <body>, <style>, or <script> tags.
Never add disclaimers like "I am an AI". Write as the analyst directly.

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
  <li data-severity="[critical|high|medium|low]"><strong>[Incident name / organisation]</strong> — [Date if known]. [What happened, scale, impact.]</li>
</ul>

<h3>Ransomware &amp; Malware Activity</h3>
<p>[Notable ransomware groups or malware campaigns. If none reported, state that clearly.]</p>

<h3>Regulatory &amp; Policy Updates</h3>
<p>[New cybersecurity laws, guidelines, or enforcement actions. If none, state that clearly.]</p>

<h3>Threat Intelligence Highlights</h3>
<p>[APT activity, CVEs, or sector-specific threats relevant to {country}.]</p>

<h3>Key Takeaway for Organisations</h3>
<p>[1-2 actionable sentences for organisations operating in {country}.]</p>

Then append the ---METADATA--- block as instructed in your system prompt.

Be specific. Use real incident names from your search results."""


# ── Regional briefing (Haiku, no web search — reasons over the digest only) ──
REGIONAL_SYSTEM = """You are a senior cybersecurity analyst producing the lead section of a
monthly APAC cybersecurity board briefing. You are given a compact digest of per-country
severity counts, category counts, and executive summaries that another analyst already
researched this month. You do not have web search — reason only from the digest provided.

Write in this exact HTML structure, using ONLY these tags: <h3>, <p>, <ul>, <li>, <strong>.

<h3>Regional Executive Briefing</h3>
<p>[3-4 sentence cross-market synthesis of the region's cybersecurity posture this month.]</p>
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

Never invent incidents or figures not present in the digest. If the digest doesn't support a
cross-border pattern or regulatory pattern, say "None identified" rather than fabricating one.
Never add disclaimers like "I am an AI".
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
    config = {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "scales": {
                "xAxes": [{"stacked": True, "ticks": {"fontColor": "#8b949e"}}],
                "yAxes": [{"stacked": True, "ticks": {"fontColor": "#8b949e", "precision": 0}}],
            },
            "legend": {"position": "bottom", "labels": {"fontColor": "#e6edf3"}},
        },
    }
    return _quickchart_url(config, width=640, height=280, bg="%230d1117")


# ── Agentic research loop per country ───────────────────────────────────────
def research_country(client: anthropic.Anthropic, country: dict, month: str, year: int) -> dict:
    messages = [{"role": "user", "content": country_prompt(country["name"], month, year)}]

    for _iteration in range(12):
        response = api_call_with_retry(
            client, messages, ANALYST_SYSTEM,
            model="claude-sonnet-4-6", max_tokens=2500,
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
            raw = "\n".join(text_parts) if text_parts else None
            return _build_country_result(raw, country["name"], month, year)

    return _build_country_result(None, country["name"], month, year)


def _build_country_result(raw, country: str, month: str, year: int) -> dict:
    if not raw:
        return _fallback(country, month, year)

    content, metadata = _extract_metadata(raw)
    if not content.strip():
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

    attempts = [("claude-haiku-4-5-20251001", 1200), ("claude-sonnet-4-6", 1200)]
    for model, max_tokens in attempts:
        try:
            response = api_call_with_retry(
                client, [{"role": "user", "content": prompt}], REGIONAL_SYSTEM,
                model=model, max_tokens=max_tokens, tools=None, max_retries=2,
            )
            raw = "\n".join(b.text for b in response.content if b.type == "text" and b.text.strip())
            content, metadata = _extract_metadata(raw)
            if content.strip():
                return {"content": content, "headline": metadata.get("regional_headline", "")}
            print(f"    ⚠  Regional briefing from {model} was empty after parsing.")
        except Exception as e:
            print(f"    ⚠  Regional briefing attempt failed ({model}): {e}")

    print("    ⚠  Regional briefing omitted — all attempts failed.")
    return None


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

    return html, plain_text, headline
