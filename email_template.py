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


def _inject_inline_styles(html_fragment: str) -> str:
    """
    Post-processes Claude's HTML output and adds inline styles to bare tags.
    Skips tags that already carry a style attribute.
    """
    def replacer(m: re.Match) -> str:
        tag = m.group(1).lower()
        attrs = m.group(2)
        if tag not in _TAG_STYLES:
            return m.group(0)
        # Don't double-up if Claude already added a style attr
        if 'style=' in attrs.lower():
            return m.group(0)
        return f"<{tag}{attrs} style=\"{_TAG_STYLES[tag]}\">"

    return re.sub(r'<([a-zA-Z][a-zA-Z0-9]*)((?:\s[^>]*)?)?>', replacer, html_fragment)


# ── Public builders ──────────────────────────────────────────────────────────

def build_html(month: str, year: int, sections: list, generated_at: str) -> str:

    toc_items = "\n".join(
        f'<a href="#country-{c["code"]}" style="{_TOC_LINK_STYLE}">'
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
    /*
     * Browsers suppress background-color by default when printing.
     * These three vendor-prefixed properties override that behaviour
     * so the dark theme, card backgrounds, and accent colours all
     * appear in the PDF exactly as they do on screen.
     *
     * Also re-declares the body background because some print engines
     * ignore the inline style on <body> but honour a print rule.
     */
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
      /* Hide the TOC jump links \u2014 anchors don\u2019t work in PDF */
      .toc-box {{ display: none; }}
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
<div class="wrapper" style="{_WRAPPER_STYLE}">

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

  <!-- ════════════════════ TABLE OF CONTENTS ════════════════════ -->
  <div class="toc-box" style="{_TOC_BOX_STYLE}">
    <p style="{_TOC_LABEL_STYLE}">Jump to Country</p>
    {toc_items}
  </div>

  <!-- ════════════════════ COUNTRY SECTIONS ════════════════════ -->
  {country_blocks}

  <!-- ════════════════════ FOOTER ════════════════════ -->
  <div style="{_FOOTER_STYLE}">
    <p style="margin:0 0 4px 0;color:{TEXT_MUTED};">
      APAC Cybersecurity Newsletter &nbsp;&middot;&nbsp; {month} {year}
    </p>
    <p style="margin:0 0 8px 0;color:{TEXT_MUTED};">
      Generated {generated_at} &nbsp;&middot;&nbsp; Powered by Claude + Web Search
    </p>
    <p style="font-size:11px;color:#555555;margin:0;">
      This newsletter is for informational purposes only.
      Verify all incidents with primary sources before acting on any information herein.
    </p>
  </div>

</div>
</body>
</html>"""


def _country_block(c: dict) -> str:
    """
    Wraps a country section in a styled card.
    Claude's HTML content is post-processed to add inline styles on bare tags.
    """
    styled_content = _inject_inline_styles(c["content"])
    return f"""
  <div class="no-break" id="country-{c['code']}" style="{_CARD_STYLE}">
    <div style="{_CARD_HEADER_STYLE}">
      <span style="{_FLAG_CELL_STYLE}">{c['flag']}</span>
      <span style="{_NAME_CELL_STYLE}">{c['name']}</span>
    </div>
    {styled_content}
  </div>"""


def build_plain_text(month: str, year: int, sections: list) -> str:
    """Plain-text fallback for email clients that don't render HTML."""
    lines = [
        f"APAC Cybersecurity Monthly Retrospective \u2014 {month} {year}",
        "=" * 62,
        "",
    ]
    for c in sections:
        lines.append(f"{c['flag']}  {c['name'].upper()}")
        lines.append("-" * 40)
        text = re.sub(r"<[^>]+>", " ", c["content"])
        text = re.sub(r"\s{2,}", " ", text).strip()
        lines.append(text)
        lines.append("")
        lines.append("")
    lines.append("\u2500" * 62)
    lines.append("APAC Cybersecurity Newsletter \u00b7 For informational purposes only.")
    return "\n".join(lines)
