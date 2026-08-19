"""
email_template.py
Builds the full HTML email and plain-text fallback for the newsletter.

Compatibility strategy:
  - ALL layout/colour styles are INLINE on every element. This survives Gmail
    forwarding, Outlook, and any client that strips <style> blocks (most do
    on forward). A minimal <style> block remains only for @media rules,
    which cannot be inlined.
  - Emoji flags/icons are Unicode codepoints with a fallback font stack —
    no image assets needed for those.
  - Charts (severity donut per country, regional stacked bar) are rendered
    on demand by QuickChart.io and referenced as plain <img src="..."> URLs —
    no image hosting or base64 embedding required. If a country has no
    tagged incidents, chart_url is empty and the chart is simply omitted.
"""

import re

# ── Colour palette ───────────────────────────────────────────────────────────
DARK_BG    = "#0d1117"
CARD_BG    = "#161b22"
BORDER     = "#21262d"
ACCENT     = "#58a6ff"
TEXT_MAIN  = "#e6edf3"
TEXT_MUTED = "#8b949e"

SEVERITY_COLORS = {
    "critical": "#f85149",
    "high":     "#db6d28",
    "medium":   "#d29922",
    "low":      "#3fb950",
}

TREND_ARROWS = {
    "up":      ("▲", "#f85149"),
    "down":    ("▼", "#3fb950"),
    "flat":    ("→", "#8b949e"),
    "unknown": ("", "#8b949e"),
}

SECTION_ICONS = {
    "Executive Summary": "📋",
    "Major Incidents &amp; Breaches": "🛡",
    "Ransomware &amp; Extortion Activity": "🦠",
    "Regulatory &amp; Legal Exposure": "⚖",
    "Threat Intelligence &amp; Sector Risk": "🎯",
    "Board Takeaway": "✅",
    "Regional Executive Briefing": "🌏",
}


# ── Inline-style constants ───────────────────────────────────────────────────
_BODY_STYLE = (
    f"margin:0;padding:0;background-color:{DARK_BG};color:{TEXT_MAIN};"
    "font-family:'Segoe UI',Helvetica,Arial,sans-serif;"
    "font-size:15px;line-height:1.7;-webkit-text-size-adjust:100%;"
)
_WRAPPER_STYLE = "max-width:680px;margin:0 auto;padding:24px 16px;"
_HEADER_STYLE = (
    f"background-color:{CARD_BG};border:1px solid {BORDER};border-radius:10px;"
    "padding:32px 36px;margin-bottom:24px;"
)
_BADGE_STYLE = (
    f"display:inline-block;background-color:{ACCENT};color:#000000;"
    "font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;"
    "padding:3px 10px;border-radius:4px;margin-bottom:14px;"
)
_TITLE_STYLE = "font-size:26px;font-weight:800;color:#ffffff;line-height:1.2;margin:0 0 8px 0;"
_SUBTITLE_STYLE = f"color:{TEXT_MUTED};font-size:14px;margin:0;"

_TOC_BOX_STYLE = (
    f"background-color:{CARD_BG};border:1px solid {BORDER};border-radius:8px;"
    "padding:16px 20px;margin-bottom:24px;"
)
_TOC_LABEL_STYLE = (
    f"font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;"
    f"color:{TEXT_MUTED};margin:0 0 10px 0;"
)
_TOC_TILE_STYLE = (
    f"display:inline-block;background-color:{DARK_BG};border:1px solid {BORDER};"
    f"border-radius:6px;padding:8px 14px;margin:0 8px 8px 0;text-decoration:none;"
    f"color:{TEXT_MAIN};font-size:13px;"
)

_CARD_STYLE = (
    f"background-color:{CARD_BG};border:1px solid {BORDER};border-radius:10px;"
    "padding:28px 32px;margin-bottom:20px;"
)
_CARD_HEADER_STYLE = (
    f"display:table;width:100%;margin-bottom:16px;padding-bottom:14px;"
    f"border-bottom:2px solid {ACCENT};"
)
_FLAG_CELL_STYLE = (
    "display:table-cell;vertical-align:middle;font-size:28px;line-height:1;padding-right:10px;"
    "font-family:'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji','Twemoji Mozilla',sans-serif;"
)
_NAME_CELL_STYLE = "display:table-cell;vertical-align:middle;font-size:20px;font-weight:800;color:#ffffff;"

_STAT_CARD_STYLE = (
    f"display:table;width:100%;background-color:{DARK_BG};border:1px solid {BORDER};"
    "border-radius:8px;padding:14px 18px;margin-bottom:18px;"
)
_STAT_VALUE_STYLE = "font-size:22px;font-weight:800;color:#ffffff;"
_STAT_LABEL_STYLE = f"font-size:11px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:.04em;"
_STAT_CELL_STYLE = "display:table-cell;vertical-align:middle;"

_SEVERITY_PILL_STYLE = (
    "display:inline-block;font-size:10px;font-weight:800;letter-spacing:.05em;"
    "text-transform:uppercase;padding:2px 8px;border-radius:10px;margin-right:8px;color:#0d1117;"
)

_REGIONAL_STYLE = (
    f"background-color:{CARD_BG};border:1px solid {ACCENT};border-radius:10px;"
    "padding:28px 32px;margin-bottom:24px;"
)
_REGIONAL_HEADLINE_STYLE = "font-size:18px;font-weight:800;color:#ffffff;margin:0 0 16px 0;"

_FOOTER_STYLE = f"text-align:center;padding:24px 0;color:{TEXT_MUTED};font-size:12px;"

_TAG_STYLES = {
    "h3": (
        f"color:{ACCENT};font-size:14px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;"
        f"margin:22px 0 6px 0;padding-bottom:4px;border-bottom:1px solid {BORDER};"
    ),
    "h4": f"color:{TEXT_MAIN};font-size:14px;font-weight:600;margin:14px 0 4px 0;",
    "p":  f"color:{TEXT_MAIN};margin:0 0 10px 0;",
    "ul": "padding-left:18px;margin:0 0 12px 0;",
    "li": f"color:{TEXT_MAIN};margin-bottom:6px;",
    "strong": "color:#ffffff;",
    "hr": f"border:none;border-top:1px solid {BORDER};margin:28px 0;",
    "a":  f"color:{ACCENT};",
}


# ── Content post-processing (Claude writes bare, semantic HTML; we style it) ──
def _style_severity_li(html_fragment: str) -> str:
    """Converts <li data-severity="high">...</li> into a styled li with a colour pill."""
    def repl(m):
        sev = m.group(1).lower()
        inner = m.group(2)
        color = SEVERITY_COLORS.get(sev, "#8b949e")
        pill = f'<span style="{_SEVERITY_PILL_STYLE}background-color:{color};">{sev}</span>'
        return f"<li>{pill}{inner}</li>"
    return re.sub(r'<li data-severity="(\w+)">(.*?)</li>', repl, html_fragment, flags=re.DOTALL)


def _add_section_icons(html_fragment: str) -> str:
    def repl(m):
        text = m.group(1).strip()
        icon = SECTION_ICONS.get(text)
        return f"<h3>{icon} {text}</h3>" if icon else m.group(0)
    return re.sub(r"<h3>(.*?)</h3>", repl, html_fragment)


def _inject_inline_styles(html_fragment: str) -> str:
    """Adds inline styles to bare tags Claude wrote, skipping tags that already have style=."""
    def replacer(m: re.Match) -> str:
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        if tag not in _TAG_STYLES or "style=" in attrs.lower():
            return m.group(0)
        return f"<{tag}{attrs} style=\"{_TAG_STYLES[tag]}\">"
    return re.sub(r"<([a-zA-Z][a-zA-Z0-9]*)((?:\s[^>]*)?)?>", replacer, html_fragment)


def _style_content(html_fragment: str) -> str:
    styled = _style_severity_li(html_fragment)
    styled = _add_section_icons(styled)
    return _inject_inline_styles(styled)


# ── Stat card / donut chart per country ──────────────────────────────────────
def _stat_card(c: dict) -> str:
    stat = c.get("headline_stat")
    if not stat or not stat.get("value"):
        return ""

    cells = [f"""
      <div style="{_STAT_CELL_STYLE}">
        <div style="{_STAT_VALUE_STYLE}">{stat.get('value', '')}</div>
        <div style="{_STAT_LABEL_STYLE}">{stat.get('label', '')}</div>
      </div>"""]

    secondary = c.get("headline_stat_secondary")
    if secondary and secondary.get("value"):
        cells.append(f"""
      <div style="{_STAT_CELL_STYLE}padding-left:28px;">
        <div style="{_STAT_VALUE_STYLE}">{secondary.get('value', '')}</div>
        <div style="{_STAT_LABEL_STYLE}">{secondary.get('label', '')}</div>
      </div>""")

    arrow, arrow_color = TREND_ARROWS.get(c.get("trend", "unknown"), ("", "#8b949e"))
    if arrow:
        cells.append(f"""
      <div style="{_STAT_CELL_STYLE}padding-left:14px;color:{arrow_color};font-size:16px;">{arrow}</div>""")

    chart_url = c.get("chart_url")
    if chart_url:
        cells.append(f"""
      <div style="display:table-cell;vertical-align:middle;text-align:right;">
        <img src="{chart_url}" width="60" height="60" alt="Severity mix for {c.get('name','')}" style="display:inline-block;">
      </div>""")

    return f'<div style="{_STAT_CARD_STYLE}">{"".join(cells)}</div>'


# ── Public builders ──────────────────────────────────────────────────────────
def build_html(month: str, year: int, sections: list, generated_at: str,
                regional: dict = None, regional_chart_url: str = "") -> str:

    toc_items = "\n".join(
        f'<a href="#country-{c["code"]}" style="{_TOC_TILE_STYLE}">{c["flag"]} {c["name"]}</a>'
        for c in sections
    )
    country_blocks = "\n".join(_country_block(c) for c in sections)
    regional_block = _regional_block(regional, regional_chart_url)
    country_count = len(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>APAC Cybersecurity Newsletter — {month} {year}</title>
  <style>
    body, table, td, p, a, h1, h2, h3, h4, ul, li {{ margin:0; padding:0; border:0; }}
    @media print {{
      *, *::before, *::after {{
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }}
      body {{ background-color:{DARK_BG} !important; color:{TEXT_MAIN} !important; }}
      .no-break {{ page-break-inside: avoid; break-inside: avoid; }}
      .toc-box {{ display:none; }}
    }}
    @media screen and (max-width: 480px) {{
      .wrapper     {{ padding:12px 8px !important; }}
      .header-cell {{ padding:22px 20px !important; }}
      .card-cell   {{ padding:20px 18px !important; }}
      .title-text  {{ font-size:20px !important; }}
    }}
  </style>
</head>
<body style="{_BODY_STYLE}">
<div class="wrapper" style="{_WRAPPER_STYLE}">

  <!-- Header -->
  <div class="header-cell no-break" style="{_HEADER_STYLE}">
    <div style="{_BADGE_STYLE}">Monthly Intelligence Brief</div>
    <div class="title-text" style="{_TITLE_STYLE}">APAC Cybersecurity<br>Monthly Retrospective</div>
    <p style="{_SUBTITLE_STYLE}">{month} {year} &nbsp;&middot;&nbsp; {country_count} Countries &nbsp;&middot;&nbsp; Asia-Pacific Region</p>
  </div>

  <!-- Regional Executive Briefing -->
  {regional_block}

  <!-- Table of Contents -->
  <div class="toc-box" style="{_TOC_BOX_STYLE}">
    <p style="{_TOC_LABEL_STYLE}">Jump to Country</p>
    {toc_items}
  </div>

  <!-- Country sections -->
  {country_blocks}

  <!-- Footer -->
  <div style="{_FOOTER_STYLE}">
    <p style="margin:0 0 4px 0;color:{TEXT_MUTED};">APAC Cybersecurity Newsletter &nbsp;&middot;&nbsp; {month} {year}</p>
    <p style="margin:0 0 8px 0;color:{TEXT_MUTED};">Generated {generated_at}</p>
    <p style="font-size:11px;color:#555555;margin:0;">
      This newsletter is for informational purposes only. Verify all incidents with primary sources
      before acting on any information contained herein.
    </p>
  </div>

</div>
</body>
</html>"""


def _country_block(c: dict) -> str:
    styled_content = _style_content(c["content"])
    stat_card = _stat_card(c)
    return f"""
  <div class="no-break" id="country-{c['code']}" style="{_CARD_STYLE}">
    <div style="{_CARD_HEADER_STYLE}">
      <span style="{_FLAG_CELL_STYLE}">{c['flag']}</span>
      <span style="{_NAME_CELL_STYLE}">{c['name']}</span>
    </div>
    {stat_card}
    {styled_content}
  </div>"""


def _regional_block(regional: dict, chart_url: str) -> str:
    if not regional or not regional.get("content"):
        return ""
    styled = _style_content(regional["content"])
    headline = regional.get("headline", "")
    headline_html = f'<p style="{_REGIONAL_HEADLINE_STYLE}">{headline}</p>' if headline else ""
    chart_html = (
        f'<img src="{chart_url}" width="100%" alt="Regional severity breakdown by country" '
        f'style="max-width:600px;width:100%;display:block;margin:0 0 18px 0;border-radius:6px;">'
        if chart_url else ""
    )
    return f'<div class="no-break" style="{_REGIONAL_STYLE}">{headline_html}{chart_html}{styled}</div>'


def build_plain_text(month: str, year: int, sections: list, regional: dict = None) -> str:
    """Plain-text fallback for clients that don't render HTML."""
    lines = [
        f"APAC Cybersecurity Monthly Retrospective — {month} {year}",
        "=" * 62,
        "",
    ]

    if regional and regional.get("content"):
        if regional.get("headline"):
            lines.append(regional["headline"])
            lines.append("")
        text = re.sub(r"<[^>]+>", " ", regional["content"])
        text = re.sub(r"\s{2,}", " ", text).strip()
        lines.append(text)
        lines.append("")
        lines.append("─" * 62)
        lines.append("")

    for c in sections:
        lines.append(f"{c['flag']}  {c['name'].upper()}")
        lines.append("-" * 40)
        stat = c.get("headline_stat")
        if stat and stat.get("value"):
            lines.append(f"[{stat['value']} {stat.get('label', '')}]")
        text = re.sub(r"<[^>]+>", " ", c["content"])
        text = re.sub(r"\s{2,}", " ", text).strip()
        lines.append(text)
        lines.append("")
        lines.append("")

    lines.append("─" * 62)
    lines.append("APAC Cybersecurity Newsletter · For informational purposes only.")
    return "\n".join(lines)
