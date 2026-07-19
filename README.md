# APAC Cybersecurity Newsletter — Monthly Automation

Automated monthly cybersecurity **board briefing** covering **12 Asia-Pacific countries**,
written for executives and directors, powered by **Claude + web search**, delivered via
**Gmail**, orchestrated by **GitHub Actions**.

## Countries Covered

🇸🇬 Singapore · 🇭🇰 Hong Kong · 🇨🇳 China · 🇮🇳 India · 🇵🇭 Philippines · 🇻🇳 Vietnam  
🇲🇾 Malaysia · 🇦🇺 Australia · 🇰🇷 South Korea · 🇮🇩 Indonesia · 🇯🇵 Japan · 🇹🇼 Taiwan

---

## Who This Is Written For

This newsletter is written for **boards and executive leadership** (CEOs, CFOs, general
counsel, non-technical directors) — not security engineers. Every section leads with business
impact (cost, downtime, legal exposure, reputational risk), explains any technical term in
plain English on first use, and ends with a decision or question for the board rather than a
technical instruction for an IT team.

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
    │       ├─► Claude (MODEL_RESEARCH) + web_search  (×12 countries)
    │       │       └─► Agentic research loop per country, capped search budget
    │       │
    │       └─► Claude (MODEL_SYNTHESIS)  (×1, after all 12 countries)
    │               └─► Pure synthesis — no web search — cross-country pattern-spotting
    │
    ├─► email_template.py  →  Builds styled HTML + plain-text
    │
    └─► send_email.py  →  Gmail SMTP → Recipients
```

The pipeline makes **13 Claude API calls per run**: 12 country research calls, plus one
Regional Briefing synthesis call that reads all 12 finished sections and pulls out the
cross-market pattern — it does not search the web itself, only reasons over what the country
calls already found.

### Each country section includes

- **Executive Summary** — what mattered for businesses this month, in business terms
- **Major Incidents & Breaches** — named incidents with dates and business-impact scale
  (cost, records affected, downtime)
- **Ransomware & Extortion Activity** — disruption risk, explained in plain English
- **Regulatory & Legal Exposure** — new laws/enforcement, framed as board liability
- **Sector Watch** — which industries were most targeted this month
- **Board Takeaway** — one question or decision for the board
- **Sources** — up to 5 real article links Claude actually retrieved via web search

### The newsletter also includes

- **Regional Executive Briefing** (lead section, amber accent) — synthesizes the 12 country
  sections into: the defining regional theme, where risk concentrated across markets,
  whether regulation is converging or diverging region-wide, and the one thing a
  multi-country board should watch this month.

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
3. Ensure your account has access to the models set in `generate_newsletter.py`
   (`MODEL_RESEARCH`, `MODEL_SYNTHESIS`) and the `web_search` tool

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

### Step 5 — Enable GitHub Actions

1. Go to your repo → **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"** (if prompted)

That's it. The newsletter runs automatically on the **2nd of every month**.

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

The generated HTML is always uploaded as a **GitHub Actions artifact** (90-day retention)
so you can download and inspect it even after a dry run.

---

## Subject Line

The email subject line is generated dynamically from the Regional Briefing's "Big Picture"
section — no extra API call, it's parsed from content already generated:

```
APAC Cybersecurity — June 2026 — Ransomware attacks against financial services
surged across four APAC markets this…
```

If parsing fails for any reason, it falls back to a generic subject
(`APAC Cybersecurity — {Month} {Year} Monthly Retrospective`).

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

### Change the models

Model selection lives at the top of `generate_newsletter.py`:

```python
MODEL_RESEARCH  = "claude-sonnet-5"              # per-country research + writing
MODEL_SYNTHESIS = "claude-haiku-4-5-20251001"    # Regional Briefing synthesis (cheaper — no search)
```

`MODEL_RESEARCH` needs web search and strong writing quality. `MODEL_SYNTHESIS` only
summarizes text Claude already wrote, so a cheaper model is intentionally used there —
this is the single biggest cost lever in the pipeline, since the synthesis call also has the
largest input (all 12 country sections concatenated).

### Change the schedule

Edit `.github/workflows/newsletter.yml`:

```yaml
schedule:
  - cron: "0 6 2 * *"   # 2nd of month, 06:00 UTC
```
Use [crontab.guru](https://crontab.guru) to build cron expressions.

### Change the research depth / tone

Edit `ANALYST_SYSTEM` and `country_prompt()` for per-country content, or `REGIONAL_SYSTEM`
and `_regional_prompt()` for the cross-market synthesis, in `generate_newsletter.py`.

### Add an attachment (PDF version)

Install `weasyprint` and add a conversion step in `main.py` after the HTML is written.

---

## Cost & Token Optimization

Each run makes **13 Claude API calls**: 12 country research calls on `MODEL_RESEARCH`
(Sonnet-class, needs web search) and 1 Regional Briefing synthesis call on `MODEL_SYNTHESIS`
(Haiku-class, pure summarization). Several optimizations keep this cheap:

| Lever | What it does |
|---|---|
| Cheaper model for synthesis | Regional Briefing runs on Haiku instead of Sonnet — it's summarizing text Claude already wrote, not researching |
| `max_uses` cap on web search | Bounds both the token cost of search results *and* the flat per-search fee ($10 / 1,000 searches) |
| Sources stripped from synthesis input | The 12-country digest fed to the Regional Briefing drops each country's Sources list before synthesis — those links matter for the reader but add nothing to cross-country pattern-spotting |
| Lower agentic loop cap | `MAX_RESEARCH_ITERATIONS` caps tool-use round trips per country as a backstop against runaway search loops |
| Smaller output cap on synthesis | Regional Briefing output is capped lower than country sections, since it's meant to be short |

**Prompt caching was evaluated but not enabled** — the system prompt is under the
1,024-token minimum cacheable block size for Sonnet-class models, so a cache breakpoint
would currently be silently ignored. Worth revisiting if the prompts grow substantially.

**Estimated monthly cost:** well under $5/month at current model pricing, depending on
response length and search volume. Actual pricing can change — check
[Anthropic's pricing page](https://www.anthropic.com/pricing) for current rates.

**Note on Claude subscriptions:** this pipeline runs on **API pay-as-you-go billing**, not
a claude.ai subscription (Free/Pro/Max/Team/Enterprise) — those are for chat usage in a
browser or app and don't apply to an automated script like this one.

---

## Email Client Compatibility

- **All layout/colour styles are inline** on every element — survives Gmail forwarding,
  Outlook, and any client that strips `<style>` blocks.
- **"Jump to Country" links** use both `id="country-XX"` and `<a name="country-XX">` for
  the widest client compatibility. **Known limitation:** Outlook desktop (the Word-based
  rendering engine) does not reliably support in-page anchor jumps in HTML email at all,
  regardless of markup — if a link doesn't jump there, all the content is still present
  below in order, so nothing is lost.
- **Print / Save-as-PDF** uses `print-color-adjust: exact` to preserve the dark theme and
  accent colours when printed.
- **Country flag emoji** use an explicit font stack (`Apple Color Emoji`, `Segoe UI Emoji`,
  `Noto Color Emoji`, `Twemoji Mozilla`) so they render as colour flags, not boxes.

---

## File Structure

```
apac-cyber-newsletter/
├── .github/
│   └── workflows/
│       └── newsletter.yml      # GitHub Actions schedule + secrets
├── main.py                     # Orchestrator (entry point, builds subject line)
├── generate_newsletter.py      # Claude API + web search research + regional synthesis
├── email_template.py           # HTML & plain-text email builder
├── send_email.py               # Gmail SMTP sender
├── requirements.txt
├── env.example                 # Copy to .env for local dev
├── download                    # .gitignore (see note below)
└── README.md
```

> **Note:** the file named `download` in this repo is the `.gitignore` file — GitHub's
> web uploader saved it without a leading dot. If you clone locally and want proper
> git-ignore behaviour, rename it to `.gitignore`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `SMTPAuthenticationError` | Use an **App Password**, not your Gmail password. Ensure 2FA is on. |
| `AuthenticationError` from Anthropic | Check `ANTHROPIC_API_KEY` is set correctly as a secret. |
| Empty country section | The web search found no results, or `MAX_SEARCHES_PER_COUNTRY` / `MAX_RESEARCH_ITERATIONS` was too tight for that month. This is rare — try re-running. |
| `max_uses_exceeded` on a country | That country hit the search cap in `generate_newsletter.py`. Raise `MAX_SEARCHES_PER_COUNTRY` if this becomes frequent. |
| Regional Briefing missing / fallback text | The synthesis call failed after retries — check logs for the specific error; the rest of the newsletter still sends normally. |
| "Jump to Country" links don't work in Outlook | Expected — Outlook desktop doesn't support in-page anchor jumps in HTML email. Content is still all present in order below. |
| Workflow not triggering | Check Actions is enabled; schedule runs are on UTC time. |
| Rate limit errors | Exponential backoff retry is built in (60s, 120s, 240s...). If persistent, increase `SLEEP_BETWEEN_COUNTRIES` in `generate_newsletter.py`. |

---

## License

MIT — use freely, attribution appreciated.
