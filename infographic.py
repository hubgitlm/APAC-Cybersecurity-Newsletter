"""
infographic.py
Builds a single-page, landscape "snapshot" PDF summarizing the entire
newsletter — regional headline, the 3-point regional watch list, and a
12-tile country grid with each market's dominant severity colour and
headline stat.

Rendered with WeasyPrint: pure Python, no headless browser required, so it
runs reliably in GitHub Actions with just a handful of system libraries
(see newsletter.yml). Country/regional chart images reuse the same
QuickChart.io URLs already built for the HTML email — WeasyPrint fetches
them over the network at render time.

If PDF generation fails for any reason, callers should treat it as
non-fatal: the HTML email is the primary deliverable, the PDF is a bonus
attachment.
"""

import re
from weasyprint import HTML

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

SEVERITY_RANK = ("critical", "high", "medium", "low")


def _dominant_severity(severity_counts: dict) -> str:
    for sev in SEVERITY_RANK:
        if severity_counts.get(sev, 0) > 0:
            return sev
    return "low"


def _extract_regional_bullets(regional_content: str) -> list:
    """Pulls the 3 labelled <li> items out of the Regional Briefing's <ul>,
    e.g. <li><strong>Highest Severity:</strong> ...</li> -> ("Highest Severity", "...")."""
    items = re.findall(r"<li><strong>(.*?):?</strong>\s*(.*?)</li>", regional_content, re.DOTALL)
    bullets = []
    for label, text in items:
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        bullets.append((label.strip().rstrip(":"), clean_text))
    return bullets


def _country_tile(c: dict) -> str:
    dom_color = SEVERITY_COLORS[_dominant_severity(c.get("severity_counts", {}))]
    stat = c.get("headline_stat") or {}
    value = stat.get("value", "—")
    label = stat.get("label", "No data")
    chart_url = c.get("chart_url", "")
    chart_html = f'<img src="{chart_url}" class="tile-chart">' if chart_url else ""

    return f"""
    <div class="tile" style="border-top-color:{dom_color};">
      <div class="tile-header">
        <span class="tile-code">{c['code']}</span>
        <span class="tile-name">{c['name']}</span>
      </div>
      <div class="tile-body">
        <div class="tile-stat">
          <div class="tile-value">{value}</div>
          <div class="tile-label">{label}</div>
        </div>
        {chart_html}
      </div>
    </div>"""


def build_infographic_html(month: str, year: int, sections: list,
                            regional: dict = None, regional_chart_url: str = "") -> str:
    tiles_html = "\n".join(_country_tile(c) for c in sections)

    headline = (regional or {}).get("headline", "") or f"APAC Cybersecurity — {month} {year} Snapshot"
    bullets = _extract_regional_bullets((regional or {}).get("content", "")) if regional else []
    bullets_html = "\n".join(
        f'<div class="bullet"><span class="bullet-label">{label}</span>'
        f'<span class="bullet-text">{text}</span></div>'
        for label, text in bullets
    )
    regional_chart_html = f'<img src="{regional_chart_url}" class="regional-chart">' if regional_chart_url else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>APAC Cybersecurity Snapshot — {month} {year}</title>
<style>
  @page {{ size: A4 landscape; margin: 10mm; }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin:0; padding:0; background-color:{DARK_BG}; color:{TEXT_MAIN};
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  }}
  .header {{ margin-bottom:6mm; }}
  .badge {{
    display:inline-block; background-color:{ACCENT}; color:#000000; font-size:8pt; font-weight:800;
    letter-spacing:0.08em; text-transform:uppercase; padding:1.5mm 4mm; border-radius:1mm; margin-bottom:2mm;
  }}
  .title {{ font-size:20pt; font-weight:800; color:#ffffff; margin:0; }}
  .subtitle {{ font-size:10pt; color:{TEXT_MUTED}; margin-top:1.5mm; }}

  .regional {{
    background-color:{CARD_BG}; border:0.3mm solid {BORDER}; border-radius:3mm;
    padding:5mm 7mm; margin-bottom:6mm; display:flex; align-items:center; gap:8mm;
  }}
  .regional-text {{ flex:1; }}
  .regional-headline {{ font-size:13pt; font-weight:700; color:#ffffff; margin:0 0 3mm 0; }}
  .regional-chart {{ width:75mm; height:auto; flex-shrink:0; }}
  .bullets {{ display:flex; gap:6mm; }}
  .bullet {{ flex:1; font-size:8pt; color:{TEXT_MUTED}; }}
  .bullet-label {{
    display:block; color:{ACCENT}; font-weight:700; font-size:7pt;
    text-transform:uppercase; letter-spacing:0.04em; margin-bottom:1mm;
  }}
  .bullet-text {{ color:{TEXT_MAIN}; }}

  .grid {{ display:grid; grid-template-columns: repeat(4, 1fr); grid-template-rows: repeat(3, 1fr); gap:4mm; }}
  .tile {{
    background-color:{CARD_BG}; border:0.3mm solid {BORDER}; border-top:1.4mm solid;
    border-radius:2mm; padding:3mm 4mm;
  }}
  .tile-header {{ display:flex; align-items:baseline; gap:2.5mm; margin-bottom:2mm; }}
  .tile-code {{
    font-size:9pt; font-weight:800; color:{ACCENT}; letter-spacing:0.04em;
    background-color:{DARK_BG}; padding:0.5mm 2mm; border-radius:1mm;
  }}
  .tile-name {{ font-size:9pt; font-weight:700; color:#ffffff; }}
  .tile-body {{ display:flex; align-items:center; justify-content:space-between; }}
  .tile-value {{ font-size:15pt; font-weight:800; color:#ffffff; }}
  .tile-label {{ font-size:6.5pt; color:{TEXT_MUTED}; text-transform:uppercase; letter-spacing:0.03em; max-width:22mm; }}
  .tile-chart {{ width:15mm; height:15mm; flex-shrink:0; }}

  .footer {{ margin-top:5mm; text-align:center; font-size:7pt; color:#555555; }}
</style></head>
<body>
  <div class="header">
    <div class="badge">Monthly Snapshot</div>
    <div class="title">APAC Cybersecurity — {month} {year}</div>
    <div class="subtitle">{len(sections)} Countries &middot; Asia-Pacific Region &middot; Board-Level Briefing</div>
  </div>

  <div class="regional">
    <div class="regional-text">
      <p class="regional-headline">{headline}</p>
      <div class="bullets">{bullets_html}</div>
    </div>
    {regional_chart_html}
  </div>

  <div class="grid">
    {tiles_html}
  </div>

  <div class="footer">
    Generated by Claude + Web Search &middot; For informational purposes only — verify all incidents with primary sources.
  </div>
</body></html>"""


def render_infographic_pdf(html: str) -> bytes:
    """Renders infographic HTML to PDF bytes. Raises on failure — callers should catch."""
    return HTML(string=html).write_pdf()
