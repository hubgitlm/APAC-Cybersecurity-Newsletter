"""
generate_newsletter.py
Calls Claude with web_search to research each country, then assembles the
full HTML newsletter. Includes exponential backoff retry on 429 rate limit errors.

── Cost/token optimization notes ────────────────────────────────────────────
- Research calls (12x, one per country) use MODEL_RESEARCH — needs real
  writing quality + web search, so stays on a Sonnet-class model.
- The Regional Briefing synthesis call (1x) uses MODEL_SYNTHESIS — a cheaper
  model, since it's pure summarization of already-generated text, not fresh
  research. This is the single biggest lever, since it also has the largest
  input (all 12 country sections concatenated).
- web_search max_uses caps searches per country. Web search is billed per
  search ($10 / 1,000 searches) *in addition to* token cost, on top of the
  token cost of the returned results — so this bounds both, not just tokens.
- Prompt caching was evaluated but NOT enabled: the system prompt is well
  under the 1,024-token minimum cacheable block size for Sonnet-class models,
  so a cache_control breakpoint here would be silently ignored. Worth
  revisiting only if ANALYST_SYSTEM grows substantially longer.
"""

import anthropic
import os
import time
import random
from datetime import datetime
from email_template import build_html, build_plain_text

# ── Model selection ──────────────────────────────────────────────────────────
MODEL_RESEARCH   = "claude-sonnet-5"              # research + writing, needs web search
MODEL_SYNTHESIS  = "claude-haiku-4-5-20251001"    # pure summarization, cheaper model is enough

# Hard cap on searches per country call. Bounds both token cost (search
# results are billed as input tokens) and the flat per-search fee. The prompt
# suggests 5 search queries; this gives one spare without letting a country
# spiral into an unbounded search loop.
MAX_SEARCHES_PER_COUNTRY = 6

# Safety cap on agentic tool-use round trips per country. With max_uses
# already bounding search count, this rarely gets hit — it's a backstop
# against runaway loops, not the primary cost lever.
MAX_RESEARCH_ITERATIONS = 8

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
ANALYST_SYSTEM = """You are a senior cybersecurity risk advisor writing a monthly briefing
for company boards and executive leadership (CEOs, CFOs, general counsel, non-technical directors)
across the Asia-Pacific region. Your reader oversees risk and capital — they do not configure
firewalls and do not need to.

Your writing style:
- Business-first: lead every point with impact — cost, downtime, customer harm, legal/regulatory
  exposure, share-price or reputational effect — not attack mechanics.
- Plain English: if you must use a technical term (ransomware, zero-day, MFA, APT), immediately
  explain it in one short clause a non-technical reader understands. Never use a CVE number,
  malware family name, or technical jargon without that plain-English gloss attached.
- Concise and authoritative — no fluff, no filler.
- Factual: name real organisations and incidents, with dates, and be clear about financial or
  operational scale where reported (cost, records affected, days of downtime, etc).
- Frame regulation as exposure, not as a compliance bulletin: what does this new law or ruling
  mean for a board's liability, disclosure obligations, or duty of care.
- End with a decision the board should make or a question it should ask management — not a
  technical instruction to an IT team.

When you write HTML, use ONLY these tags (no inline styles, no classes):
<h3>, <h4>, <p>, <ul>, <li>, <strong>, <em>, <a href="...">, <hr>

Never write <html>, <head>, <body>, <style>, or <script> tags.
Never add disclaimers like "I am an AI". Write as the advisor directly.
"""

def country_prompt(country: str, month: str, year: int) -> str:
    return f"""Search the web and write the board-level cybersecurity briefing section for **{country}** covering **{month} {year}**.

Use web search to find real incidents. Search for terms like:
- "{country} cyber attack {month} {year}"
- "{country} data breach {month} {year}"
- "{country} ransomware {month} {year}"
- "{country} cybersecurity law regulation {month} {year}"
- "{country} APT hacking {month} {year}"

Then write the section in this exact HTML structure. Remember: this is for a board member,
not a security engineer — every point should answer "why should a director in {country} care
about this, and what could it cost the business?"

<h3>Executive Summary</h3>
<p>[2-3 sentence overview of what mattered for businesses in {country} during {month} {year},
in business-impact terms.]</p>

<h3>Major Incidents &amp; Breaches</h3>
<ul>
  <li><strong>[Organisation / incident name]</strong> — [Date if known]. [What happened, in plain
  English, and the business impact: cost, customers/records affected, downtime, reputational or
  legal consequence.]</li>
</ul>

<h3>Ransomware &amp; Extortion Activity</h3>
<p>[What board members need to know about ransomware trends this month — in terms of business
disruption risk, not technical campaign detail. If none reported, state that clearly.]</p>

<h3>Regulatory &amp; Legal Exposure</h3>
<p>[New laws, guidelines, or enforcement actions — framed as what changes for board liability,
disclosure timelines, or fines. If none, state that clearly.]</p>

<h3>Sector Watch</h3>
<p>[Which industries in {country} were most targeted or most at risk this month, and why that
matters for businesses in adjacent sectors.]</p>

<h3>Board Takeaway</h3>
<p>[One question the board should put to management, or one decision it should make, based on
this month's developments in {country}.]</p>

<h3>Sources</h3>
<ul>
  <li><a href="[URL]">[Publication name — article title]</a></li>
</ul>

Be specific. Use real incident names from your search results. In the Sources section, list the
actual URLs of the articles you found via web search that support the claims above — one link
per source, most relevant first, no more than 5. Only include URLs you actually retrieved via
search; never invent or guess a URL."""


# ── API call with exponential backoff retry ──────────────────────────────────
def api_call_with_retry(
    client, messages, system, max_retries=5,
    use_web_search=True, model=MODEL_RESEARCH, max_tokens=2500,
):
    """
    Wraps a Claude API call with exponential backoff on 429 errors.
    Waits 60s, 120s, 240s, 480s, 960s between retries.
    """
    tools = (
        [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES_PER_COUNTRY}]
        if use_web_search else []
    )
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
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

    for iteration in range(MAX_RESEARCH_ITERATIONS):
        response = api_call_with_retry(client, messages, ANALYST_SYSTEM)

        text_parts = [b.text for b in response.content if b.type == "text" and b.text.strip()]

        if response.stop_reason == "end_turn":
            return "\n".join(text_parts) if text_parts else _fallback(country["name"], month, year)

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
            return "\n".join(text_parts) if text_parts else _fallback(country["name"], month, year)

    return _fallback(country["name"], month, year)


def _fallback(country: str, month: str, year: int) -> str:
    return (
        f"<h3>Executive Summary</h3>"
        f"<p>Cybersecurity data for {country} in {month} {year} could not be retrieved at this time. "
        f"Please consult national CERT advisories and threat intelligence feeds directly.</p>"
    )


# ── Regional Briefing: cross-country synthesis (runs after all 12 countries) ─
REGIONAL_SYSTEM = """You are a senior cybersecurity risk advisor producing the lead section of a
monthly APAC-wide board briefing. You have already researched all 12 countries individually.
Your job now is pure synthesis — do NOT search the web, do NOT introduce new incidents. Only
draw conclusions from the country summaries you are given.

Your reader is a board member or executive overseeing a multi-country APAC business. They want
the regional pattern, not another repetition of the country details.

Writing style: plain English, business-impact first, concise, no jargon without a gloss.

When you write HTML, use ONLY these tags (no inline styles, no classes):
<h3>, <h4>, <p>, <ul>, <li>, <strong>, <em>, <hr>
Never write <html>, <head>, <body>, <style>, or <script> tags.
"""

def _strip_sources(content: str) -> str:
    """
    Removes the <h3>Sources</h3>...<ul>...</ul> block from a country section
    before it's fed into the Regional Briefing synthesis prompt. Source links
    matter for the reader in the final email but add nothing to cross-country
    pattern-spotting — stripping them meaningfully shrinks the input to the
    single largest API call in the pipeline (12 sections concatenated).
    """
    import re as _re
    return _re.sub(
        r"<h3>\s*Sources\s*</h3>\s*<ul>.*?</ul>\s*",
        "",
        content,
        flags=_re.IGNORECASE | _re.DOTALL,
    )


def _regional_prompt(month: str, year: int, sections: list) -> str:
    digest = "\n\n".join(
        f"### {c['name']}\n{_strip_sources(c['content'])}" for c in sections
    )
    return f"""Below are the 12 country briefings already written for {month} {year}. Read them and
write a single "Regional Executive Briefing" synthesizing the cross-market picture. Do not restate
every country — pull out the pattern.

Structure exactly like this:

<h3>The Big Picture</h3>
<p>[2-4 sentences: what was the defining regional theme this month across the 12 markets?]</p>

<h3>Where the Risk Concentrated</h3>
<ul>
  <li>[A pattern spanning 2+ countries — e.g. a sector, attack type, or actor active in multiple
  markets. Name the countries involved.]</li>
</ul>

<h3>Regulatory Direction of Travel</h3>
<p>[Is regulation across the region converging or diverging this month — e.g. multiple countries
tightening breach-notification rules, or one market moving out of step with its neighbours? What
should a multi-country board take from that?]</p>

<h3>What the Board Should Watch</h3>
<p>[The single most important cross-market takeaway for a board overseeing operations across
APAC this month.]</p>

Here are the country briefings:

{digest}"""


def synthesize_regional_briefing(client: anthropic.Anthropic, sections: list, month: str, year: int) -> str:
    """Single non-agentic call (no web search) that synthesizes the 12 country
    briefings into one regional executive summary.

    Tries MODEL_SYNTHESIS first (cheaper). If that call fails for any reason
    (model access issue, transient error, etc.) it retries once on
    MODEL_RESEARCH — the model that just successfully generated all 12
    country sections, so we know it works for this account — before giving
    up and returning the fallback text. Both failures are logged with full
    detail so the real cause is visible in the GitHub Actions log, not just
    the generic fallback message.
    """
    prompt = _regional_prompt(month, year, sections)
    attempts = [
        ("MODEL_SYNTHESIS", MODEL_SYNTHESIS, 1200),
        ("MODEL_RESEARCH (fallback)", MODEL_RESEARCH, 1200),
    ]

    last_error = None
    failed_labels = []
    for label, model, max_tokens in attempts:
        try:
            response = api_call_with_retry(
                client,
                [{"role": "user", "content": prompt}],
                REGIONAL_SYSTEM,
                use_web_search=False,
                model=model,
                max_tokens=max_tokens,
            )
            text_parts = [b.text for b in response.content if b.type == "text" and b.text.strip()]
            if text_parts:
                if failed_labels:
                    print(f"  ℹ  Regional briefing succeeded on {label} ({model}) "
                          f"after {', '.join(failed_labels)} failed.")
                return "\n".join(text_parts)
            print(f"  ⚠  {label} ({model}) returned no text content — trying next option if available.")
            failed_labels.append(label)
        except Exception as e:
            last_error = e
            failed_labels.append(label)
            print(f"  ⚠  Regional briefing synthesis failed on {label} ({model}): "
                  f"{type(e).__name__}: {e}")

    if last_error is not None:
        print(f"  ⚠  All regional briefing attempts failed. Last error: "
              f"{type(last_error).__name__}: {last_error}")
    return _regional_fallback(month, year)


def _regional_fallback(month: str, year: int) -> str:
    return (
        f"<h3>The Big Picture</h3>"
        f"<p>The regional synthesis for {month} {year} could not be generated this run. "
        f"See the individual country briefings below for details.</p>"
    )


def extract_headline(regional_briefing: str, max_len: int = 90) -> str:
    """
    Pulls a short, scroll-stopping headline out of the Regional Briefing's
    'The Big Picture' section for use in the email subject line.
    Costs no extra API call — parsed from content already generated.
    Falls back to a generic string if parsing fails.
    """
    import re as _re
    match = _re.search(
        r"<h3>\s*The Big Picture\s*</h3>\s*<p>(.*?)</p>",
        regional_briefing,
        _re.IGNORECASE | _re.DOTALL,
    )
    if not match:
        return ""

    text = _re.sub(r"<[^>]+>", "", match.group(1)).strip()
    # Use the first sentence only, trimmed to a subject-line-friendly length
    first_sentence = _re.split(r"(?<=[.!?])\s+", text)[0].strip()
    if len(first_sentence) > max_len:
        first_sentence = first_sentence[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return first_sentence


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

    print(f"  [--/--] Synthesizing Regional Executive Briefing ...", flush=True)
    regional_briefing = synthesize_regional_briefing(client, sections, month, year)
    print(f"         ✓ Done", flush=True)

    generated_at = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    html       = build_html(month, year, sections, generated_at, regional_briefing)
    plain_text = build_plain_text(month, year, sections, regional_briefing)
    headline   = extract_headline(regional_briefing)

    return html, plain_text, headline
