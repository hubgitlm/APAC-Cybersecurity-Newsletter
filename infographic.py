"""
infographic.py
Builds a two-page, landscape PDF snapshot of the newsletter.

Page 1 — Regional Executive Briefing: headline, the full board-level
synthesis paragraph, and the 3-point regional watch list (Highest Severity /
Cross-Border Pattern / Regulatory Watch).

Page 2 — Country Breakdown: a 12-tile grid, one per market, each showing
its dominant severity colour, headline stat, top (most severe) named
incident, and a compact severity count breakdown.

Visual language: white page, off-white card panels, thin borders, and a
single muted navy accent — restrained institutional research styling
rather than the earlier black/bold-yellow "security product" look — plus
the existing muted red/orange/gold/green severity palette (risk signal,
kept separate from the accent colour so severity meaning isn't diluted).

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

# ── Institutional palette ────────────────────────────────────────────────
# Replaces the earlier black/bold-yellow "security product" look, which
# read as a SIEM vendor's marketing page rather than institutional
# research (McKinsey/Deloitte one-pagers lean toward restrained, mostly
# white/navy palettes with a single muted accent, reserving colour for
# genuine signal — severity — rather than branding). White page, off-white
# card panels, thin borders instead of filled colour blocks, dark navy
# text instead of white-on-black.
PAGE_BG    = "#ffffff"
CARD_BG    = "#f6f7f9"
BORDER     = "#dde1e8"
ACCENT     = "#1d3461"
TEXT_MAIN  = "#1b2436"
TEXT_MUTED = "#5a6478"

# Risk signal palette — muted/desaturated versions of the standard
# red/orange/gold/green severity ramp, so severity is still immediately
# legible at a glance but doesn't compete visually with the accent colour
# or read as neon. Kept identical to generate_newsletter.py's
# SEVERITY_COLORS so charts, pills, and tiles all agree.
SEVERITY_COLORS = {
    "critical": "#a13529",
    "high":     "#b0692c",
    "medium":   "#9c7f2a",
    "low":      "#2f7a52",
}

SEVERITY_RANK = ("critical", "high", "medium", "low")

# Character budgets that keep page 1 guaranteed inside its available space at
# the font sizes/widths set in the CSS below. Combined with the CSS
# max-height + overflow:hidden backstops on the same elements, these two
# layers together guarantee the PDF is always exactly 2 pages regardless of
# how much text Claude writes in a given month.
# MAX_HEADLINE_CHARS was 115, but the regional_headline the model actually
# produced was routinely 200+ chars, so almost every issue's headline was
# hitting the truncate-with-ellipsis path mid-sentence. The prompt now
# explicitly asks for <=100 chars (see REGIONAL_SYSTEM in
# generate_newsletter.py); this ceiling is raised to 150 as a generous
# backstop rather than the primary length control, so an occasional overrun
# still gets a clean, readable cut instead of relying on a tight budget to
# never be exceeded.
MAX_HEADLINE_CHARS   = 150   # ~3 lines at 20pt over a 220mm-wide block, with room for the ellipsis
MAX_PARAGRAPH_CHARS  = 550   # ~6 lines at 11.5pt over a 210mm-wide block
MAX_BULLET_CHARS     = 170   # ~6 lines at 9pt in a ~1/3-width column


def _truncate(text: str, max_chars: int) -> str:
    """Truncates on a word boundary and appends an ellipsis, so long-form
    Claude output never silently overflows the fixed-size PDF layout."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0].rstrip(",.;:—-")
    return cut + "…"


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


def _extract_synthesis_paragraph(regional_content: str) -> str:
    """Pulls the intro <p> (the board-level synthesis paragraph) that sits
    before the <ul> in the Regional Briefing's content."""
    match = re.search(r"<p>(.*?)</p>", regional_content, re.DOTALL)
    if not match:
        return ""
    return re.sub(r"<[^>]+>", "", match.group(1)).strip()


def _extract_top_incident(content_html: str):
    """Finds the most severe named incident in a country's content, e.g.
    <li data-severity="critical"><strong>MegaCorp Holdings</strong> ...
    Returns the organisation/incident name, or None if nothing is tagged."""
    items = re.findall(r'<li data-severity="(\w+)"><strong>(.*?)</strong>', content_html, re.DOTALL)
    if not items:
        return None
    rank = {s: i for i, s in enumerate(SEVERITY_RANK)}
    items.sort(key=lambda x: rank.get(x[0].lower(), 99))
    return re.sub(r"<[^>]+>", "", items[0][1]).strip()


def _severity_breakdown_text(severity_counts: dict) -> str:
    parts = [f"{severity_counts[s]} {s.capitalize()}" for s in SEVERITY_RANK if severity_counts.get(s, 0) > 0]
    return " &middot; ".join(parts) if parts else "No incidents tagged"


def _page_header(month: str, year: int, country_count: int, section_label: str) -> str:
    return f"""
    <div class="header">
      <div class="badge">Monthly Snapshot</div>
      <div class="title">APAC Cybersecurity</div>
      <div class="subtitle">{month} {year} &middot; {country_count} Countries &middot; Asia-Pacific Region &middot; Board-Level Briefing</div>
      <hr class="header-rule">
      <div class="section-label">{section_label}</div>
    </div>"""


def _page_footer() -> str:
    return """
    <div class="footer">
      For informational purposes only — verify all incidents with primary sources.
    </div>"""


def _country_tile(c: dict) -> str:
    dom_color = SEVERITY_COLORS[_dominant_severity(c.get("severity_counts", {}))]
    stat = c.get("headline_stat") or {}
    severity_counts = c.get("severity_counts", {})
    total_tagged = sum(severity_counts.values())

    if stat.get("value"):
        value, label = stat["value"], stat.get("label", "Major Incidents")
    elif total_tagged > 0:
        # headline_stat can be missing even when the section content itself
        # is complete — e.g. if the ---METADATA--- block didn't parse for
        # some unrelated reason. Rather than show a bare "NO DATA" tile next
        # to a severity breakdown that clearly has real numbers in it,
        # derive a headline count directly from the tagged items so the
        # tile never contradicts itself.
        value, label = str(total_tagged), "Tagged Items"
    else:
        value, label = "—", "No data"
    chart_url = c.get("chart_url", "")
    chart_html = f'<img src="{chart_url}" class="tile-chart">' if chart_url else ""

    top_incident = _extract_top_incident(c.get("content", ""))
    top_incident_html = (
        f'Top: {top_incident}' if top_incident else 'No major incidents reported'
    )
    breakdown = _severity_breakdown_text(c.get("severity_counts", {}))

    return f"""
    <div class="tile">
      <div class="tile-header">
        <span class="tile-badge" style="border-color:{dom_color};">{c['code']}</span>
        <span class="tile-name">{c['name']}</span>
      </div>
      <div class="tile-body">
        <div class="tile-stat">
          <div class="tile-value">{value}</div>
          <div class="tile-label">{label}</div>
        </div>
        {chart_html}
      </div>
      <div class="tile-detail">
        <div class="tile-top-incident">{top_incident_html}</div>
        <div class="tile-breakdown">{breakdown}</div>
      </div>
    </div>"""


def build_infographic_html(month: str, year: int, sections: list,
                            regional: dict = None, regional_chart_url: str = "") -> str:
    regional_content = (regional or {}).get("content", "")
    raw_headline = (regional or {}).get("headline", "") or f"APAC Cybersecurity — {month} {year} Snapshot"
    headline = _truncate(raw_headline, MAX_HEADLINE_CHARS)
    synthesis_paragraph = _truncate(
        _extract_synthesis_paragraph(regional_content) if regional else "", MAX_PARAGRAPH_CHARS
    )
    bullets = _extract_regional_bullets(regional_content) if regional else []
    bullets_html = "\n".join(
        f'<div class="bullet">'
        f'{"<div class=\'bullet-divider\'></div>" if i > 0 else ""}'
        f'<span class="bullet-label">{label}</span>'
        f'<span class="bullet-text">{_truncate(text, MAX_BULLET_CHARS)}</span></div>'
        for i, (label, text) in enumerate(bullets)
    )
    regional_chart_html = f'<img src="{regional_chart_url}" class="regional-chart">' if regional_chart_url else ""
    tiles_html = "\n".join(_country_tile(c) for c in sections)
    country_count = len(sections)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>APAC Cybersecurity Snapshot — {month} {year}</title>
<style>
  @page {{ size: A4 landscape; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin:0; padding:0; background-color:{PAGE_BG}; color:{TEXT_MAIN};
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  }}

  .page {{
    min-height:210mm; padding: 8mm 14mm 0 14mm;
    display:flex; flex-direction:column;
    page-break-after: always;
  }}
  .page:last-child {{ page-break-after: auto; }}
  .page-content {{ flex: 1 0 auto; }}

  .header {{ margin-bottom:5mm; position:relative; }}
  .badge {{
    display:inline-block; color:{ACCENT}; font-size:8pt; font-weight:800;
    letter-spacing:0.12em; text-transform:uppercase; padding:0 0 1.5mm 0; margin-bottom:2.5mm;
    border-bottom:0.5mm solid {ACCENT};
  }}
  .title {{
    font-size:22pt; font-weight:700; color:{TEXT_MAIN}; margin:0; text-transform:uppercase;
    letter-spacing:0.01em; line-height:1.05;
  }}
  .subtitle {{ font-size:9.5pt; color:{TEXT_MUTED}; margin-top:1.5mm; }}
  .header-rule {{ border:none; border-top:0.4mm solid {ACCENT}; margin:3.5mm 0 3mm 0; }}
  .section-label {{
    font-size:9pt; font-weight:800; color:{ACCENT}; letter-spacing:0.08em; text-transform:uppercase;
  }}

  /* ── Page 1: Regional Briefing ── */
  .briefing {{ padding-top:6mm; }}
  .regional-headline {{
    font-size:20pt; font-weight:700; color:{TEXT_MAIN}; margin:0 0 6mm 0; line-height:1.3; max-width:220mm;
    max-height:29mm; overflow:hidden;
  }}
  .regional-paragraph {{
    font-size:11.5pt; color:{TEXT_MAIN}; line-height:1.65; max-width:210mm; margin:0 0 8mm 0;
    max-height:42mm; overflow:hidden;
  }}
  .watch-card {{
    background-color:{CARD_BG}; border:0.3mm solid {BORDER}; padding:7mm 9mm; display:flex; align-items:flex-start;
  }}
  .bullets {{ display:flex; width:100%; }}
  .bullet {{ flex:1; font-size:9pt; color:{TEXT_MUTED}; position:relative; padding:0 8mm; }}
  .bullet:first-child {{ padding-left:0; }}
  .bullet-divider {{
    position:absolute; left:0; top:0.5mm; bottom:0.5mm; width:0.5mm; background-color:{ACCENT};
  }}
  .bullet-label {{
    display:block; color:{ACCENT}; font-weight:800; font-size:8.5pt;
    text-transform:uppercase; letter-spacing:0.05em; margin-bottom:2.5mm;
  }}
  .bullet-text {{ color:{TEXT_MAIN}; line-height:1.5; max-height:30mm; overflow:hidden; display:block; }}
  .regional-chart {{ width:60mm; height:auto; flex-shrink:0; margin-left:6mm; }}

  /* ── Page 2: Country grid ── */
  .grid {{
    display:grid; grid-template-columns: repeat(4, 1fr); grid-template-rows: repeat(3, 1fr);
    gap:3mm; padding-top:5mm; padding-bottom:5mm;
  }}
  .tile {{
    background-color:{CARD_BG}; border:0.3mm solid {BORDER}; padding:3mm 3.5mm;
    display:flex; flex-direction:column;
  }}
  .tile-header {{ display:flex; align-items:center; gap:2.5mm; margin-bottom:2mm; }}
  .tile-badge {{
    display:inline-flex; align-items:center; justify-content:center;
    width:9mm; height:9mm; border-radius:50%; border:0.7mm solid; background-color:{PAGE_BG};
    font-size:7pt; font-weight:800; color:{TEXT_MAIN}; letter-spacing:0.02em; flex-shrink:0;
  }}
  .tile-name {{ font-size:8.5pt; font-weight:700; color:{TEXT_MAIN}; }}
  .tile-body {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:2mm; }}
  .tile-value {{ font-size:13pt; font-weight:800; color:{ACCENT}; }}
  .tile-label {{ font-size:5.5pt; color:{TEXT_MUTED}; text-transform:uppercase; letter-spacing:0.03em; max-width:20mm; }}
  .tile-chart {{ width:11mm; height:11mm; flex-shrink:0; }}
  .tile-detail {{
    border-top:0.25mm solid {BORDER}; padding-top:1.8mm; margin-top:auto;
  }}
  .tile-top-incident {{
    font-size:6.3pt; font-weight:700; color:{TEXT_MAIN}; line-height:1.3; margin-bottom:1mm;
    overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  }}
  .tile-breakdown {{ font-size:5.8pt; color:{TEXT_MUTED}; }}

  .footer {{
    border-top:0.3mm solid {BORDER}; color:{TEXT_MUTED}; text-align:center; font-size:7.5pt; font-weight:600;
    padding:3mm 0; margin:0 -14mm; margin-top:auto;
  }}
</style></head>
<body>

  <!-- ═══════════ PAGE 1 — Regional Executive Briefing ═══════════ -->
  <div class="page">
    <div class="page-content">
      {_page_header(month, year, country_count, "Regional Executive Briefing")}
      <div class="briefing">
        <p class="regional-headline">{headline}</p>
        <p class="regional-paragraph">{synthesis_paragraph}</p>
        <div class="watch-card">
          <div class="bullets">{bullets_html}</div>
          {regional_chart_html}
        </div>
      </div>
    </div>
    {_page_footer()}
  </div>

  <!-- ═══════════ PAGE 2 — Country Breakdown ═══════════ -->
  <div class="page">
    <div class="page-content">
      {_page_header(month, year, country_count, "Country Breakdown")}
      <div class="grid">
        {tiles_html}
      </div>
    </div>
    {_page_footer()}
  </div>

</body></html>"""


def render_infographic_pdf(html: str) -> bytes:
    """Renders infographic HTML to PDF bytes. Raises on failure — callers should catch."""
    return HTML(string=html).write_pdf()
