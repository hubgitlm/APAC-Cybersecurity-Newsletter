"""
email_template.py
Builds the full HTML email and plain-text fallback for the newsletter.

Compatibility strategy:
  - ALL layout/colour styles are INLINE on every element.
    This survives Gmail forwarding, Outlook, Apple Mail, and any client
    that strips <style> blocks (which most do when forwarding).
  - A minimal <style> block remains ONLY for:
      • @media print  — forces background colours when printing to PDF
      • @media (max-width:480px) — responsive tweaks that must live in <style>
      • tag-level resets (margin/padding) that are impractical to inline
  - Emoji country flags are Unicode codepoints — no images needed.
    They render on every modern OS (Windows 10+, macOS, iOS, Android, Linux).
    A fallback font stack is declared so they never fall back to □ boxes.
"""

import re

# ── Colour palette ───────────────────────────────────────────────────────────
DARK_BG   = "#0d1117"
CARD_BG   = "#161b22"
BORDER    = "#21262d"
ACCENT    = "#58a6ff"
TEXT_MAIN = "#e6edf3"
TEXT_MUTED = "#8b949e"

# Regional Briefing accent — sets the lead synthesis section apart from the
# blue country cards so it visually reads as "the big picture" up top.
REGIONAL_ACCENT = "#f0b429"


# ── Inline-style constants (reused across elements) ──────────────────────────
_BODY_STYLE = (
    f"margin:0;padding:0;background-color:{DARK_BG};"
    f"color:{TEXT_MAIN};"
    "font-family:'Segoe UI',Helvetica,Arial,sans-serif;"
    "font-size:15px;line-height:1.7;"
    "-webkit-text-size-adjust:100%;"
)

_WRAPPER_STYLE = (
    "max-width:680px;margin:0 auto;padding:24px 16px;"
)

_HEADER_STYLE = (
    f"background-color:{CARD_BG};"
    f"border:1px solid {BORDER};"
    "border-radius:10px;"
    "padding:32px 36px;"
    "margin-bottom:24px;"
)

_BADGE_STYLE = (
    f"display:inline-block;background-color:{ACCENT};color:#000000;"
    "font-size:11px;font-weight:800;letter-spacing:.1em;"
    "text-transform:uppercase;padding:3px 10px;"
    "border-radius:4px;margin-bottom:14px;"
)

_TITLE_STYLE = (
    "font-size:26px;font-weight:800;color:#ffffff;"
    "line-height:1.2;margin:0 0 8px 0;"
)

_SUBTITLE_STYLE = (
    f"color:{TEXT_MUTED};font-size:14px;margin:0;"
)

_TOC_BOX_STYLE = (
    f"background-color:{CARD_BG};"
    f"border:1px solid {BORDER};"
    "border-radius:8px;"
    "padding:16px 20px;"
    "margin-bottom:28px;"
)

_TOC_LABEL_STYLE = (
    f"font-size:11px;font-weight:700;letter-spacing:.12em;"
    f"text-transform:uppercase;color:{TEXT_MUTED};"
    "margin:0 0 10px 0;"
)

_TOC_LINK_STYLE = (
    f"color:{ACCENT};text-decoration:none;"
    "display:inline-block;margin:4px 10px 4px 0;font-size:13px;"
)

_CARD_STYLE = (
    f"background-color:{CARD_BG};"
    f"border:1px solid {BORDER};"
    "border-radius:10px;"
    "padding:28px 32px;"
    "margin-bottom:20px;"
)

_CARD_HEADER_STYLE = (
    "display:table;width:100%;"   # table trick works in Outlook too
    "margin-bottom:18px;"
    "padding-bottom:14px;"
    f"border-bottom:2px solid {ACCENT};"
)

_FLAG_CELL_STYLE = (
    "display:table-cell;vertical-align:middle;"
    "font-size:28px;line-height:1;padding-right:10px;"
    # Emoji font stack: ensures flags render as coloured emoji, not □
    "font-family:'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',"
    "'Twemoji Mozilla',sans-serif;"
)

_NAME_CELL_STYLE = (
    "display:table-cell;vertical-align:middle;"
    "font-size:20px;font-weight:800;color:#ffffff;"
)

_FOOTER_STYLE = (
    f"text-align:center;padding:24px 0;color:{TEXT_MUTED};font-size:12px;"
)

# ── Per-card navigation strip (repeated inside every country card) ──────────
# Lets readers jump directly to another country from wherever they're
# currently reading, instead of having to scroll back up to the top TOC.
_NAV_STRIP_STYLE = (
    f"margin:0 0 18px 0;padding-bottom:14px;"
    f"border-bottom:1px solid {BORDER};"
    f"font-size:12px;line-height:1.9;"
)

_NAV_STRIP_LABEL_STYLE = (
    f"color:{TEXT_MUTED};font-size:11px;font-weight:700;"
    "letter-spacing:.1em;text-transform:uppercase;margin-right:6px;"
)

_NAV_STRIP_LINK_STYLE = (
    f"color:{ACCENT};text-decoration:none;margin:0 8px 0 0;"
)

_NAV_STRIP_CURRENT_STYLE = (
    f"color:{TEXT_MUTED};margin:0 8px 0 0;"  # current country: muted, not a link
)

_NAV_STRIP_TOP_LINK_STYLE = (
    f"color:{TEXT_MUTED};text-decoration:none;font-size:11px;float:right;"
)

# ── References (consolidated source links, end of newsletter) ───────────────
_REFERENCES_CARD_STYLE = (
    f"background-color:{CARD_BG};"
    f"border:1px solid {BORDER};"
    "border-radius:10px;"
    "padding:28px 32px;"
    "margin-bottom:24px;"
)

_REFERENCES_BADGE_STYLE = (
    f"display:inline-block;background-color:{TEXT_MUTED};color:#000000;"
    "font-size:11px;font-weight:800;letter-spacing:.1em;"
    "text-transform:uppercase;padding:3px 10px;"
    "border-radius:4px;margin-bottom:14px;"
)

_REFERENCES_COUNTRY_HEADING_STYLE = (
    "font-size:13px;font-weight:700;color:#ffffff;margin:16px 0 6px 0;"
)

# ── Regional Briefing (lead section) card/badge styles ──────────────────────
_REGIONAL_CARD_STYLE = (
    f"background-color:{CARD_BG};"
    f"border:1px solid {REGIONAL_ACCENT};"
    "border-radius:10px;"
    "padding:28px 32px;"
    "margin-bottom:28px;"
)

_REGIONAL_BADGE_STYLE = (
    f"display:inline-block;background-color:{REGIONAL_ACCENT};color:#000000;"
    "font-size:11px;font-weight:800;letter-spacing:.1em;"
    "text-transform:uppercase;padding:3px 10px;"
    "border-radius:4px;margin-bottom:14px;"
)

# ── Inline styles injected into Claude-generated content ────────────────────
# Claude writes bare <h3>, <p>, <ul>, <li> etc.  We post-process these to add
# inline styles so they survive <style>-stripping email clients.

_TAG_STYLES = {
    "h3": (
        f"color:{ACCENT};font-size:14px;font-weight:700;"
        "letter-spacing:.06em;text-transform:uppercase;"
        f"margin:22px 0 6px 0;padding-bottom:4px;"
        f"border-bottom:1px solid {BORDER};"
    ),
    "h4": (
        f"color:{TEXT_MAIN};font-size:14px;font-weight:600;"
        "margin:14px 0 4px 0;"
    ),
    "p": (
        f"color:{TEXT_MAIN};margin:0 0 10px 0;"
    ),
    "ul": (
        "padding-left:18px;margin:0 0 12px 0;"
    ),
    "li": (
        f"color:{TEXT_MAIN};margin-bottom:6px;"
    ),
    "strong": (
        "color:#ffffff;"
    ),
    "hr": (
        f"border:none;border-top:1px solid {BORDER};margin:28px 0;"
    ),
    "a": (
        f"color:{ACCENT};"
    ),
}

# Same tag styles, but with the amber regional accent on <h3> so the Regional
# Briefing section reads as visually distinct from the blue country cards.
_REGIONAL_TAG_STYLES = {
    **_TAG_STYLES,
    "h3": (
        f"color:{REGIONAL_ACCENT};font-size:14px;font-weight:700;"
        "letter-spacing:.06em;text-transform:uppercase;"
        f"margin:22px 0 6px 0;padding-bottom:4px;"
        f"border-bottom:1px solid {BORDER};"
    ),
}


def _extract_sources(content: str) -> tuple:
    """
    Splits a country's content into (content_without_sources, sources_ul_html).
    The Sources <h3>/<ul> block Claude writes per-country is pulled out here so
    it can be rendered once, consolidated, in a References section at the end
    of the newsletter — rather than repeated inline inside every country card.
    Returns sources_ul_html as "" if no Sources section was found.
    """
    match = re.search(
        r"<h3>\s*Sources\s*</h3>\s*(<ul>.*?</ul>)",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return content, ""
    sources_html = match.group(1)
    remaining = content[:match.start()] + content[match.end():]
    return remaining.strip(), sources_html


def _inject_inline_styles(html_fragment: str, tag_styles: dict = _TAG_STYLES) -> str:
    """
    Post-processes Claude's HTML output and adds inline styles to bare tags.
    Skips tags that already carry a style attribute.
    """
    def replacer(m: re.Match) -> str:
        tag = m.group(1).lower()
        attrs = m.group(2)
        if tag not in tag_styles:
            return m.group(0)
        # Don't double-up if Claude already added a style attr
        if 'style=' in attrs.lower():
            return m.group(0)
        return f"<{tag}{attrs} style=\"{tag_styles[tag]}\">"

    return re.sub(r'<([a-zA-Z][a-zA-Z0-9]*)((?:\s[^>]*)?)?>', replacer, html_fragment)


# ── Public builders ──────────────────────────────────────────────────────────

def build_html(month: str, year: int, sections: list, generated_at: str, regional_briefing: str = "") -> str:

    toc_items = "\n".join(
        f'<a href="#country-{c["code"]}" style="{_TOC_LINK_STYLE}">'
        f'{c["flag"]} {c["name"]}</a>'
        for c in sections
    )

    # Extract each country's Sources block so it can be consolidated into a
    # single References section at the end, instead of repeated inline.
    stripped_sections = []
    references = []  # list of (country dict, sources_ul_html)
    for c in sections:
        remaining, sources_html = _extract_sources(c["content"])
        stripped_sections.append({**c, "content": remaining})
        if sources_html:
            references.append((c, sources_html))

    country_blocks = "\n".join(_country_block(c, sections) for c in stripped_sections)
    regional_block = _regional_block(regional_briefing) if regional_briefing else ""
    references_block = _references_block(references) if references else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>APAC Cybersecurity Newsletter \u2014 {month} {year}</title>
  <style>
    /*
     * This <style> block is intentionally minimal.
     * All colours & layout use inline styles (survive email forwarding + Outlook).
     *
     * This block handles ONLY things that CANNOT be inlined:
     *   1. @media print  \u2014 forces background colours when printing / saving as PDF
     *   2. @media screen (responsive) \u2014 small-screen tweaks
     *   3. Basic tag resets
     */

    /* ── Tag resets ─────────────────────────────────────────────── */
    body, table, td, p, a, h1, h2, h3, h4, ul, li {{
      margin: 0; padding: 0; border: 0;
    }}

    /* ── Print / Save-as-PDF ────────────────────────────────────── */
    @media print {{
      *,
      *::before,
      *::after {{
        -webkit-print-color-adjust: exact !important;   /* Chrome, Safari, Edge */
                print-color-adjust: exact !important;   /* Firefox, W3C standard */
      }}
      body {{
        background-color: {DARK_BG} !important;
        color: {TEXT_MAIN} !important;
      }}
      /* Prevent cards from splitting across page breaks */
      .no-break {{
        page-break-inside: avoid;
        break-inside: avoid;
      }}
      /* Hide the TOC jump links and per-card nav strips \u2014 anchors don\u2019t work in PDF */
      .toc-box {{ display: none; }}
      .nav-strip {{ display: none; }}
    }}

    /* ── Responsive (screen only) ───────────────────────────────── */
    @media screen and (max-width: 480px) {{
      .wrapper      {{ padding: 12px 8px !important; }}
      .header-cell  {{ padding: 22px 20px !important; }}
      .card-cell    {{ padding: 20px 18px !important; }}
      .title-text   {{ font-size: 20px !important; }}
    }}
  </style>
</head>
<body style="{_BODY_STYLE}">
<div class="wrapper" id="top" style="{_WRAPPER_STYLE}">
<a name="top"></a>

  <!-- ════════════════════ HEADER ════════════════════ -->
  <div class="header-cell no-break" style="{_HEADER_STYLE}">
    <div style="{_BADGE_STYLE}">Monthly Intelligence Brief</div>
    <div class="title-text" style="{_TITLE_STYLE}">
      APAC Cybersecurity<br>Monthly Retrospective
    </div>
    <p style="{_SUBTITLE_STYLE}">
      {month} {year} &nbsp;&middot;&nbsp; 12 Countries &nbsp;&middot;&nbsp; Asia-Pacific Region
    </p>
  </div>

  <!-- ════════════════════ REGIONAL EXECUTIVE BRIEFING ════════════════════ -->
  {regional_block}

  <!-- ════════════════════ TABLE OF CONTENTS ════════════════════ -->
  <div class="toc-box" style="{_TOC_BOX_STYLE}">
    <p style="{_TOC_LABEL_STYLE}">Jump to Country</p>
    {toc_items}
  </div>

  <!-- ════════════════════ COUNTRY SECTIONS ════════════════════ -->
  {country_blocks}

  <!-- ════════════════════ REFERENCES ════════════════════ -->
  {references_block}

  <!-- ════════════════════ FOOTER ════════════════════ -->
  <div style="{_FOOTER_STYLE}">
    <p style="margin:0 0 4px 0;color:{TEXT_MUTED};">
      APAC Cybersecurity Newsletter &nbsp;&middot;&nbsp; {month} {year}
    </p>
    <p style="margin:0 0 8px 0;color:{TEXT_MUTED};">
      Generated {generated_at}
    </p>
    <p style="font-size:11px;color:#555555;margin:0;">
      This newsletter is for informational purposes only.
      Verify all incidents with primary sources before acting on any information herein.
    </p>
  </div>

</div>
</body>
</html>"""


def _regional_block(regional_briefing: str) -> str:
    """
    Renders the cross-country synthesis as the lead section, styled distinctly
    (amber accent) from the blue country cards below it.
    """
    styled_content = _inject_inline_styles(regional_briefing, _REGIONAL_TAG_STYLES)
    return f"""
  <div class="no-break" id="regional-briefing" style="{_REGIONAL_CARD_STYLE}">
    <div style="{_REGIONAL_BADGE_STYLE}">Regional Executive Briefing</div>
    {styled_content}
  </div>"""


def _country_nav_strip(all_sections: list, current_code: str) -> str:
    """
    Small repeated navigation row inside every country card, so a reader can
    jump directly to another country from wherever they currently are,
    instead of scrolling back up to the top-of-newsletter TOC each time.
    Current country is shown muted/plain (not a link); a "Back to top" link
    sits on the right for reaching the main TOC or Regional Briefing.
    """
    links = []
    for c in all_sections:
        if c["code"] == current_code:
            links.append(f'<span style="{_NAV_STRIP_CURRENT_STYLE}"><strong>{c["flag"]} {c["name"]}</strong></span>')
        else:
            links.append(
                f'<a href="#country-{c["code"]}" style="{_NAV_STRIP_LINK_STYLE}">{c["flag"]} {c["name"]}</a>'
            )
    links_html = "".join(links)
    return f"""
    <div class="nav-strip" style="{_NAV_STRIP_STYLE}">
      <a href="#top" style="{_NAV_STRIP_TOP_LINK_STYLE}">&uarr; Top</a>
      <span style="{_NAV_STRIP_LABEL_STYLE}">Jump to:</span>{links_html}
    </div>"""


def _country_block(c: dict, all_sections: list) -> str:
    """
    Wraps a country section in a styled card.
    Claude's HTML content is post-processed to add inline styles on bare tags.

    Anchor compatibility note: TOC "jump to country" links use #id anchors.
    Some email clients (older Gmail, Yahoo) only honour the legacy
    <a name="..."> anchor pattern rather than an element id, so both are
    included here for maximum compatibility. Outlook desktop (the Word-based
    rendering engine) does not reliably support in-page anchor jumps in HTML
    email at all — this is a known Outlook limitation, not something fixable
    from the HTML side. In Outlook, jump links may just scroll to the top or
    do nothing; the country cards are still all present below, in order, so
    nothing is lost — it's a navigation convenience, not content.
    """
    styled_content = _inject_inline_styles(c["content"])
    nav_strip = _country_nav_strip(all_sections, c["code"])
    return f"""
  <div class="no-break" id="country-{c['code']}" style="{_CARD_STYLE}">
    <a name="country-{c['code']}"></a>
    <div style="{_CARD_HEADER_STYLE}">
      <span style="{_FLAG_CELL_STYLE}">{c['flag']}</span>
      <span style="{_NAME_CELL_STYLE}">{c['name']}</span>
    </div>
    {nav_strip}
    {styled_content}
  </div>"""


def _references_block(references: list) -> str:
    """
    Consolidated source links for every country, rendered once at the end of
    the newsletter (before the footer) rather than repeated inline per card.
    `references` is a list of (country_dict, sources_ul_html) tuples.
    """
    sections_html = []
    for c, sources_html in references:
        styled_sources = _inject_inline_styles(sources_html)
        sections_html.append(
            f'<div style="{_REFERENCES_COUNTRY_HEADING_STYLE}">{c["flag"]} {c["name"]}</div>'
            f'{styled_sources}'
        )
    return f"""
  <div class="no-break" id="references" style="{_REFERENCES_CARD_STYLE}">
    <a name="references"></a>
    <div style="{_REFERENCES_BADGE_STYLE}">References</div>
    {''.join(sections_html)}
  </div>"""


def _plain_text_links(sources_html: str) -> list:
    """Extracts (title, url) pairs from a Sources <ul> block for plain-text rendering,
    where tag-stripping alone would silently discard the href."""
    return re.findall(r'<a\s+href="([^"]+)">(.*?)</a>', sources_html, re.DOTALL)


def build_plain_text(month: str, year: int, sections: list, regional_briefing: str = "") -> str:
    """Plain-text fallback for email clients that don't render HTML."""
    lines = [
        f"APAC Cybersecurity Monthly Retrospective \u2014 {month} {year}",
        "=" * 62,
        "",
    ]

    if regional_briefing:
        lines.append("REGIONAL EXECUTIVE BRIEFING")
        lines.append("-" * 40)
        text = re.sub(r"<[^>]+>", " ", regional_briefing)
        text = re.sub(r"\s{2,}", " ", text).strip()
        lines.append(text)
        lines.append("")
        lines.append("=" * 62)
        lines.append("")

    references = []  # (country dict, [(title, url), ...])
    for c in sections:
        remaining, sources_html = _extract_sources(c["content"])
        if sources_html:
            references.append((c, _plain_text_links(sources_html)))

        lines.append(f"{c['flag']}  {c['name'].upper()}")
        lines.append("-" * 40)
        text = re.sub(r"<[^>]+>", " ", remaining)
        text = re.sub(r"\s{2,}", " ", text).strip()
        lines.append(text)
        lines.append("")
        lines.append("")

    if references:
        lines.append("=" * 62)
        lines.append("REFERENCES")
        lines.append("-" * 40)
        for c, links in references:
            lines.append(f"{c['flag']}  {c['name']}")
            for title, url in links:
                clean_title = re.sub(r"\s{2,}", " ", title).strip()
                lines.append(f"  - {clean_title}: {url}")
            lines.append("")

    lines.append("\u2500" * 62)
    lines.append("APAC Cybersecurity Newsletter \u00b7 For informational purposes only.")
    return "\n".join(lines)
