# APAC Cybersecurity Newsletter — Monthly Automation

Automated monthly cybersecurity newsletter covering **12 Asia-Pacific countries**, 
powered by **Claude claude-sonnet-4-6 + web search**, delivered via **Gmail**, 
orchestrated by **GitHub Actions**.

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
    │       └─► Claude claude-sonnet-4-6 + web_search (×12 countries)
    │               └─► Agentic research loop per country
    │
    ├─► email_template.py  →  Builds styled HTML + plain-text
    │
    └─► send_email.py  →  Gmail SMTP → Recipients
```

Each country section includes:
- **Executive Summary** — what mattered this month
- **Major Incidents & Breaches** — named incidents with dates and impact
- **Ransomware & Malware Activity** — active campaigns
- **Regulatory & Policy Updates** — laws, advisories, enforcement
- **Threat Intelligence Highlights** — APTs, CVEs, sector threats
- **Key Takeaway** — actionable guidance for organisations

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
3. Ensure your account has access to `claude-sonnet-4-6` and the `web_search` tool

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
cp .env.example .env
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

## Customisation

### Add or remove countries

Edit the `COUNTRIES` list in `generate_newsletter.py`:

```python
COUNTRIES = [
    {"name": "Singapore", "flag": "🇸🇬", "code": "SG"},
    # add or remove entries here
]
```

### Change the schedule

Edit `.github/workflows/newsletter.yml`:

```yaml
schedule:
  - cron: "0 6 2 * *"   # 2nd of month, 06:00 UTC
```
Use [crontab.guru](https://crontab.guru) to build cron expressions.

### Change the research depth / tone

Edit `ANALYST_SYSTEM` and `country_prompt()` in `generate_newsletter.py`.

### Add an attachment (PDF version)

Install `weasyprint` and add a conversion step in `main.py` after the HTML is written.

---

## Cost Estimate

Each run calls the Claude API 12 times (one per country) with web search enabled.  
Approximate monthly cost: **$0.50 – $2.00 USD** depending on response length.

---

## File Structure

```
apac-cyber-newsletter/
├── .github/
│   └── workflows/
│       └── newsletter.yml      # GitHub Actions schedule + secrets
├── main.py                     # Orchestrator (entry point)
├── generate_newsletter.py      # Claude API + web search research loop
├── email_template.py           # HTML & plain-text email builder
├── send_email.py               # Gmail SMTP sender
├── requirements.txt
├── .env.example                # Copy to .env for local dev
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
| Workflow not triggering | Check Actions is enabled; schedule runs are on UTC time. |
| Rate limit errors | The script sleeps 2s between countries. Increase in `generate_newsletter.py` if needed. |

---

## License

MIT — use freely, attribution appreciated.
