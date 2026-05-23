"""
email_template.py
Builds the full HTML email and plain-text fallback for the newsletter.
Designed to render well in Gmail, Outlook, and Apple Mail.
"""

from html import escape

# ── Colour palette ───────────────────────────────────────────────────────────
DARK_BG     = "#0d1117"
CARD_BG     = "#161b22"
BORDER      = "#21262d"
ACCENT      = "#58a6ff"
ACCENT2     = "#3fb950"
TEXT_MAIN   = "#e6edf3"
TEXT_MUTED  = "#8b949e"
RED         = "#f85149"


def build_html(month: str, year: int, sections: list, generated_at: str) -> str:
    toc_items = "\n".join(
        f'<a href="#country-{c["code"]}" style="color:{ACCENT};text-decoration:none;'
        f'display:inline-block;margin:4px 10px 4px 0;font-size:13px;">'
        f'{c["flag"]} {c["name"]}</a>'
        for c in sections
    )

    country_blocks = "\n".join(_country_block(c) for c in sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>APAC Cybersecurity Newsletter — {month} {year}</title>
  <style>
    /* Reset */
    body,table,td,p,a,h1,h2,h3,h4,ul,li {{margin:0;padding:0;border:0;}}
    body {{
      background:{DARK_BG};
      color:{TEXT_MAIN};
      font-family:'Segoe UI',Helvetica,Arial,sans-serif;
      font-size:15px;
      line-height:1.7;
      -webkit-text-size-adjust:100%;
    }}
    a {{color:{ACCENT};}}
    h3 {{color:{ACCENT};font-size:14px;font-weight:700;letter-spacing:.06em;
         text-transform:uppercase;margin:22px 0 6px;padding-bottom:4px;
         border-bottom:1px solid {BORDER};}}
    h4 {{color:{TEXT_MAIN};font-size:14px;margin:14px 0 4px;}}
    p  {{color:{TEXT_MAIN};margin:0 0 10px;}}
    ul {{padding-left:18px;margin:0 0 12px;}}
    li {{color:{TEXT_MAIN};margin-bottom:6px;}}
    strong {{color:#ffffff;}}
    hr {{border:none;border-top:1px solid {BORDER};margin:28px 0;}}

    /* Layout */
    .wrapper   {{max-width:680px;margin:0 auto;padding:24px 16px;}}
    .header    {{background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;
                 padding:32px 36px;margin-bottom:24px;}}
    .badge     {{display:inline-block;background:{ACCENT};color:#000;
                 font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;
                 padding:3px 10px;border-radius:4px;margin-bottom:14px;}}
    .title     {{font-size:26px;font-weight:800;color:#ffffff;line-height:1.2;margin-bottom:8px;}}
    .subtitle  {{color:{TEXT_MUTED};font-size:14px;}}
    .toc-box   {{background:{CARD_BG};border:1px solid {BORDER};border-radius:8px;
                 padding:16px 20px;margin-bottom:28px;}}
    .toc-label {{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                 color:{TEXT_MUTED};margin-bottom:10px;}}
    .country-card {{
      background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;
      padding:28px 32px;margin-bottom:20px;
    }}
    .country-header {{display:flex;align-items:center;gap:10px;margin-bottom:18px;
                      padding-bottom:14px;border-bottom:2px solid {ACCENT};}}
    .country-flag  {{font-size:28px;line-height:1;}}
    .country-name  {{font-size:20px;font-weight:800;color:#ffffff;}}
    .footer {{text-align:center;padding:24px 0;color:{TEXT_MUTED};font-size:12px;}}
    .footer a {{color:{TEXT_MUTED};}}

    /* Responsive */
    @media (max-width:480px) {{
      .wrapper  {{padding:12px 8px;}}
      .header   {{padding:22px 20px;}}
      .country-card {{padding:20px 18px;}}
      .title    {{font-size:20px;}}
    }}
  </style>
</head>
<body>
<div class="wrapper">

  <!-- Header -->
  <div class="header">
    <div class="badge">Monthly Intelligence Brief</div>
    <div class="title">APAC Cybersecurity<br>Monthly Retrospective</div>
    <div class="subtitle">{month} {year} &nbsp;·&nbsp; 12 Countries &nbsp;·&nbsp; Asia-Pacific Region</div>
  </div>

  <!-- Table of Contents -->
  <div class="toc-box">
    <div class="toc-label">Jump to Country</div>
    {toc_items}
  </div>

  <!-- Country sections -->
  {country_blocks}

  <!-- Footer -->
  <div class="footer">
    <p>APAC Cybersecurity Newsletter &nbsp;·&nbsp; {month} {year}</p>
    <p style="margin-top:4px;">Generated {generated_at} &nbsp;·&nbsp; Powered by Claude + Web Search</p>
    <p style="margin-top:8px;font-size:11px;color:#555;">
      This newsletter is for informational purposes only. Verify all incidents with primary sources
      before acting on any information contained herein.
    </p>
  </div>

</div>
</body>
</html>"""


def _country_block(c: dict) -> str:
    return f"""
  <div class="country-card" id="country-{c['code']}">
    <div class="country-header">
      <span class="country-flag">{c['flag']}</span>
      <span class="country-name">{c['name']}</span>
    </div>
    {c['content']}
  </div>"""


def build_plain_text(month: str, year: int, sections: list) -> str:
    """Generates a plain-text fallback (used by some email clients)."""
    import re
    lines = [
        f"APAC Cybersecurity Monthly Retrospective — {month} {year}",
        "=" * 62,
        "",
    ]
    for c in sections:
        lines.append(f"{c['flag']}  {c['name'].upper()}")
        lines.append("-" * 40)
        # Strip HTML tags for plain text
        text = re.sub(r"<[^>]+>", " ", c["content"])
        text = re.sub(r"\s{2,}", " ", text).strip()
        lines.append(text)
        lines.append("")
        lines.append("")
    lines.append("─" * 62)
    lines.append("APAC Cybersecurity Newsletter · For informational purposes only.")
    return "\n".join(lines)
