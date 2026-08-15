# APAC Cybersecurity Newsletter — Monthly Automation

Automated monthly cybersecurity newsletter covering **12 Asia-Pacific countries**,
powered by **Claude `claude-sonnet-4-6` + web search** for country research and
**Claude `claude-haiku-4-5-20251001`** for cross-market synthesis, delivered via
**Gmail**, orchestrated by **GitHub Actions**.

## Countries Covered

🇸🇬 Singapore · 🇭🇰 Hong Kong · 🇨🇳 China · 🇮🇳 India · 🇵🇭 Philippines · 🇻🇳 Vietnam
🇲🇾 Malaysia · 🇦🇺 Australia · 🇰🇷 South Korea · 🇮🇩 Indonesia · 🇯🇵 Japan · 🇹🇼 Taiwan

---

## How It Works

```
GitHub Actions (2nd of month, 06:00 UTC)
    │
    ▼
main.py
    │
    ├─► generate_newsletter.py
    │       │
    │       ├─► Claude claude-sonnet-4-6 + web_search (×12 countries)
    │       │       └─► Agentic research loop per country
    │       │           → tags each incident with a severity level
    │       │           → returns a headline stat + structured metadata
    │       │
    │       └─► Claude claude-haiku-4-5-20251001 (Regional Briefing, ×1)
    │               → synthesizes cross-market patterns from all 12 countries'
    │                 severity/category counts + executive summaries
    │               → Sonnet fallback if Haiku's output is empty/fails
    │
    ├─► email_template.py  →  Builds styled HTML + plain-text
    │       → severity pills, stat cards, section icons, TOC tile grid
    │       → QuickChart.io donut + stacked-bar charts (rendered on demand,
    │         no image hosting required)
    │
    ├─► infographic.py  →  Builds a two-page landscape PDF snapshot
    │       → page 1: regional headline, full board-level synthesis paragraph,
    │         3-column regional watch list
    │       → page 2: 12-tile country grid — dominant severity, headline stat,
    │         top named incident, severity breakdown per tile
    │       → rendered with WeasyPrint (pure Python, no headless browser)
    │
    └─► send_email.py  →  Gmail SMTP → Recipients (subject = regional headline,
                            PDF snapshot attached)
```

Each country section includes:
- **Executive Summary** — what mattered this month
- **Major Incidents & Breaches** — named incidents, dates, impact, each tagged
  with a severity level (critical / high / medium / low)
- **Ransomware & Malware Activity** — active campaigns
- **Regulatory & Policy Updates** — laws, advisories, enforcement
- **Threat Intelligence Highlights** — APTs, CVEs, sector threats
- **Key Takeaway** — actionable guidance for organisations

A **Regional Executive Briefing** sits above the country sections and aggregates
patterns across all 12 markets — shared threat actors, regulatory trends, and
which markets had the sharpest severity spike this month.

---

## Visual Design

The newsletter is built for scanability, not just readability:

| Element | What it shows | How it's built |
|---|---|---|
| **Severity pills** | Colour-coded CRITICAL / HIGH / MEDIUM / LOW tag on each incident | Inline CSS, parsed from Claude's `data-severity` attribute |
| **Stat cards** | Headline number (e.g. "3 Major Incidents"), optional $ figure, trend arrow | Parsed from a small JSON metadata block Claude appends after each section |
| **Severity donut** | Per-country breakdown of incident severity | [QuickChart.io](https://quickchart.io) — rendered as a plain `<img>` URL, no hosting needed |
| **Regional stacked bar** | Severity mix across all 12 countries side by side | Same QuickChart mechanism, built from aggregated country data |
| **Section icons** | 🛡 Incidents · 🦠 Ransomware · ⚖ Regulatory · 🎯 Threat Intel | Static mapping in `email_template.py` |
| **TOC tile grid** | Flag + country name tiles instead of a plain link list | Inline CSS |

**Why QuickChart instead of hosted images:** this repo is a private GitHub repo,
so `raw.githubusercontent.com` image links wouldn't be publicly viewable by email
recipients. QuickChart takes a chart config as URL parameters and renders the PNG
on their servers on request — no image hosting, no base64 embedding, and no data
beyond aggregate incident counts ever leaves the URL.

All styling is **inline on every element** (not just in a `<style>` block), so the
newsletter survives Gmail/Outlook forwarding and clients that strip `<style>` tags
on forward.

---

## Infographic PDF Snapshot

Every run also generates a **two-page landscape PDF** — a board-readable snapshot
of the entire newsletter — and attaches it to the email alongside the HTML body.

**Page 1 — Regional Executive Briefing:**
- Section label, regional headline (same one used as the email subject), and the
  full board-level synthesis paragraph Claude writes for the Regional Briefing
- The 3-column Regional Watch list (Highest Severity / Cross-Border Pattern /
  Regulatory Watch), separated by yellow divider rules, in a bordered card

**Page 2 — Country Breakdown:**
- A 12-tile grid, one per country, each with a circular badge ringed in that
  country's dominant severity colour (red = critical present, orange = high,
  yellow = medium, green = low)
- Each tile's headline stat (e.g. "4 Major Incidents") and severity donut
- The **top (most severe) named incident** for that country, pulled from the
  same `data-severity`-tagged `<li>` elements used for the severity pills in
  the HTML email
- A compact severity breakdown line (e.g. "1 Critical &middot; 2 High &middot; 1 Medium")

Both pages share the same header (badge/title/subtitle/rule) and yellow footer
band, pinned to the bottom of each page via a flexbox layout regardless of how
much content is on that page.

**Visual language:** black/near-navy background (`#0e1526`) with a bold yellow
(`#f8e71c`) brand accent used purely for structural elements — rules, badges,
stat numbers, the footer band — kept deliberately separate from the
red/orange/amber/green severity palette so risk signal isn't diluted by the
brand colour. Modelled after a Canva design explored earlier in this project;
rebuilt natively in WeasyPrint after Canva's Autofill automation turned out to
require a Teams/Enterprise-tier plan not worth the cost for a single monthly
newsletter (see project history for that evaluation).

**How it's built:** `infographic.py` builds the layout as HTML/CSS and renders it
to PDF with [WeasyPrint](https://doc.courtbouillon.org/weasyprint/) — a pure-Python
rendering engine (no headless Chrome/Playwright needed), which keeps the GitHub
Actions job lightweight. It reuses the same QuickChart.io chart URLs as the email,
so no extra chart-rendering logic is needed.

**Known limitation:** WeasyPrint's text engine can't reliably render multi-codepoint
flag emoji (the two-letter "regional indicator" sequences behind 🇸🇬, 🇭🇰, etc.) —
they render as a broken glyph. The infographic tiles use the country code + name
instead of a flag for this reason. The HTML email is unaffected (browsers/email
clients render flag emoji fine).

**If PDF generation fails**, it's treated as non-fatal — `generate_newsletter()`
logs a warning and returns `None` for the PDF, and the email still sends normally
without an attachment. The HTML email is always the primary deliverable.

**Filename:** `newsletter_<month>_<year>_snapshot.pdf` (or with `_partialN` if
run with `--countries=N`), uploaded as part of the same GitHub Actions artifact
as the HTML file.


---

## Setup (15 minutes)

### Step 1 — Fork / clone this repository

```bash
git clone https://github.com/YOUR_USERNAME/apac-cyber-newsletter.git
cd apac-cyber-newsletter
```

### Step 2 — Get an Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an API key
3. Ensure your account has access to `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`, and the `web_search` tool

### Step 3 — Create a Gmail App Password

1. Enable **2-Step Verification** on your Gmail account
   → [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create a new App Password (name it "Newsletter")
4. Copy the 16-character password — you won't see it again

### Step 4 — Add GitHub Secrets

In your repository: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name        | Value                                              |
|--------------------|----------------------------------------------------|
| `ANTHROPIC_API_KEY`  | `sk-ant-...`                                       |
| `GMAIL_USER`         | `you@gmail.com`                                    |
| `GMAIL_APP_PASSWORD` | `xxxx xxxx xxxx xxxx` (the 16-char app password)  |
| `RECIPIENTS`         | `a@example.com,b@example.com` (comma-separated)   |

> **Note:** GitHub Secrets are write-only after saving — updating `RECIPIENTS`
> fully replaces the value, it doesn't append. Always include every intended
> recipient when updating.

### Step 5 — Enable GitHub Actions

1. Go to your repo → **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"** (if prompted)

That's it. The newsletter runs automatically on the **2nd of every month**.

---

## Reducing Wasted API Spend

Two safeguards catch problems *before* they burn real API credits:

### 1. Zero-cost smoke test (`smoke_test.py`)

Stubs the Anthropic client with canned responses and runs the **entire**
pipeline — `main.py` → `generate_newsletter.py` → `email_template.py`,
including the exact `main.py` code path (the return-value unpack, file
write, etc.) — with fake data. No real API calls, no cost.

It's wired into `newsletter.yml` as a required step that runs **before**
any real generation step. If it fails, the job stops immediately and
nothing downstream (dry run or live send) executes.

Run it locally before pushing any change to `generate_newsletter.py`,
`email_template.py`, or `main.py`:

```bash
python smoke_test.py
```

Exit code `0` = safe to deploy. Non-zero = a structural bug was caught —
fix it before running the real workflow.

### 2. Cheap real-API test runs with `--countries=N`

For catching things a stub *can't* — like Claude's actual output drifting
from the expected HTML/metadata format — run against just 1–2 countries
instead of all 12:

```bash
python main.py --dry-run --countries=2
```

This costs a fraction of a full run (~2 country calls instead of 12, and
skips the Regional Briefing call entirely when fewer than 2 countries are
requested, since single-country digests have nothing to synthesize across).

From GitHub Actions: **Run workflow** → set *country_limit* to `1` or `2`
→ set *dry run* to `true` or `false` as needed. Live sends with a country
limit get `[TEST — N countries]` prepended to the subject line so a
partial test run is never mistaken for the real newsletter.

Recommended workflow before a real monthly send: run the smoke test
locally → run a `--countries=2` dry run in Actions → inspect that
artifact → then run the full dry run → then send live.

---

## Manual / Test Run

### Run locally

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in your credentials
cp env.example .env
# edit .env with your values

# Set env vars (macOS/Linux)
export $(grep -v '^#' .env | xargs)

# Generate only (no email sent)
python main.py --dry-run

# Generate and send
python main.py
```

### Trigger manually from GitHub

1. Go to **Actions** → **APAC Cybersecurity Newsletter**
2. Click **Run workflow**
3. Set *Dry run* to `true` to preview without sending, or `false` to send

The generated HTML is always uploaded as a **GitHub Actions artifact** (90-day
retention) so you can download and inspect it — including the charts and stat
cards — even after a dry run, without needing to send an email.

---

## Customisation

### Add or remove countries

Edit the `COUNTRIES` list in `generate_newsletter.py`:

```python
COUNTRIES = [
    {"name": "Singapore", "flag": "🇸🇬", "code": "SG"},
    # add or remove entries here
]
```

### Change severity colours or section icons

Edit `SEVERITY_COLORS` in `generate_newsletter.py` and `SECTION_ICONS` in
`email_template.py`. Both are simple dictionaries.

### Change the research depth / tone

Edit `ANALYST_SYSTEM` and `country_prompt()` in `generate_newsletter.py`. If you
change the six-section HTML structure, also update `CATEGORY_SECTION_MAP` and
the regex in `_parse_category_counts()` / `_extract_executive_summary()` so
parsing stays in sync.

### Change the Regional Briefing tone or focus

Edit `REGIONAL_SYSTEM` and `regional_prompt()` in `generate_newsletter.py`.

### Change the schedule

Edit `.github/workflows/newsletter.yml`:

```yaml
schedule:
  - cron: "0 6 2 * *"   # 2nd of month, 06:00 UTC
```
Use [crontab.guru](https://crontab.guru) to build cron expressions.

### PDF snapshot customisation

Edit `infographic.py` — `build_infographic_html()` controls the two-page layout,
`YELLOW`/`DARK_BG`/`CARD_BG` control the brand palette and `SEVERITY_COLORS`
controls the per-tile risk colours (both defined locally in `infographic.py`,
separate from `generate_newsletter.py`'s own copy used for chart colours). If
you change the Regional Briefing's `<h3>`/`<p>`/`<ul>` structure in
`generate_newsletter.py`, check `_extract_synthesis_paragraph()` and
`_extract_regional_bullets()` in `infographic.py` stay in sync — both parse
that HTML by pattern-matching the exact tag structure Claude is prompted to
produce.

---

## Cost Estimate

Each run calls the Claude API 13 times: 12 country research calls (Sonnet +
web search) and 1 regional synthesis call (Haiku, falling back to Sonnet only
if Haiku's output fails). Charts are rendered externally by QuickChart, and
the infographic PDF is rendered locally by WeasyPrint — neither adds to your
Claude API usage.

Approximate monthly cost: **$0.50 – $2.00 USD** depending on response length.

---

## File Structure

```
apac-cyber-newsletter/
├── .github/
│   └── workflows/
│       └── newsletter.yml      # GitHub Actions schedule + secrets + WeasyPrint system deps
├── main.py                     # Orchestrator (entry point), supports --countries=N
├── smoke_test.py                # Zero-cost pipeline validation (stubs the Claude API)
├── generate_newsletter.py      # Claude API + web search research loop,
│                                #   severity/metadata parsing, regional
│                                #   briefing, QuickChart URL builders
├── email_template.py           # HTML & plain-text email builder,
│                                #   stat cards, severity pills, charts
├── infographic.py              # One-page PDF snapshot builder (WeasyPrint)
├── send_email.py               # Gmail SMTP sender, supports PDF attachment
├── requirements.txt
├── env.example                 # Copy to .env for local dev
├── .gitignore
└── README.md
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `SMTPAuthenticationError` | Use an **App Password**, not your Gmail password. Ensure 2FA is on. |
| `AuthenticationError` from Anthropic | Check `ANTHROPIC_API_KEY` is set correctly as a secret. |
| Empty country section | The web search found no results. This is rare — try re-running. |
| `ValueError: not enough values to unpack` | `main.py` and `generate_newsletter.py` are out of sync on how many values `generate_newsletter()` returns — make sure both files are updated together. Running `python smoke_test.py` locally catches this for $0 before it reaches Actions. |
| Actions job stops at "Smoke test pipeline" step | A structural bug was caught before any real API calls were made — no cost incurred. Check the step's log output for which assertion failed, fix it, and re-run. |
| Charts show as broken image icons (in the email) | QuickChart.io may be temporarily unreachable, or an email client is blocking remote images by default (common on first open — click "Show images"). |
| "⚠ Regional briefing omitted" in logs | Both the Haiku and Sonnet attempts failed — check the logged exception. The newsletter still sends without the Regional Briefing section. |
| "⚠ Infographic PDF failed" in logs | Non-fatal — check the logged exception. Usually a missing system library locally (see the apt-get step in `newsletter.yml` for the full list) or a transient QuickChart timeout. The email still sends without the attachment. |
| `OSError: cannot load library ... libpango` (local runs only) | WeasyPrint's system libraries aren't installed on your machine. See the `apt-get install` line in `newsletter.yml` for the package list (Debian/Ubuntu); check WeasyPrint's install docs for macOS/Windows. |
| Workflow not triggering | Check Actions is enabled; schedule runs are on UTC time. |
| Rate limit errors | The script sleeps 60s between countries. Increase `SLEEP_BETWEEN_COUNTRIES` in `generate_newsletter.py` if needed. |

---

## License

MIT — use freely, attribution appreciated.
