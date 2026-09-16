# education_export.py
# Reads this week's results.pkl written by education_search.py.
# Produces three output files:
#   education-digest-YYYY-MM-DD.csv   full data export of all articles
#   education-digest-YYYY-MM-DD.html  production report for GitHub Pages
#   index.html                        archive landing page listing all past issues

# ── Imports ───────────────────────────────────────────────────────────────────
import pickle                  # loads the binary results file saved by education_search.py
import csv                     # writes the flat CSV data export
import os                      # file path construction and existence checks
import re                      # regular expressions used in the archive-index parser
import sys                     # sys.exit() — used to stop cleanly if the search hasn't finished yet
from datetime import datetime, timedelta   # formats dates for display and recomputes the week anchor

# ── Week anchor (must match education_search.py exactly) ───────────────────────
# This script may run right after the search in the same job, or be re-run
# manually later — either way, "today" isn't reliable for figuring out which
# week's file to load, so recompute the same Monday anchor the search script
# used.
_now        = datetime.utcnow()
_week_start = (_now - timedelta(days=_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
WEEK_SLUG   = _week_start.strftime("%Y-%m-%d")   # e.g. 2026-09-15 — must match education_search.py's WEEK_SLUG

CHECKPOINT_DIR = ".checkpoints"
RESULTS_PATH   = f"{CHECKPOINT_DIR}/results-{WEEK_SLUG}.pkl"

if not os.path.exists(RESULTS_PATH):
    # The search step hasn't finished (or hasn't run) for this week yet —
    # exit cleanly rather than error, so a re-trigger of the workflow before
    # search is done doesn't fail loudly.
    print(f"{RESULTS_PATH} not found — search hasn't completed for week {WEEK_SLUG} yet. Nothing to do.")
    sys.exit(0)

_expected_output = f"education-digest-{WEEK_SLUG}.html"
if os.path.exists(_expected_output):
    # This week's report was already generated and committed by an earlier
    # run (e.g. a manual re-trigger after Monday's scheduled run already
    # succeeded) — nothing changed since then, so skip re-rendering and
    # creating a no-op commit.
    print(f"{_expected_output} already exists — week {WEEK_SLUG} already published. Nothing to do.")
    sys.exit(0)

with open(RESULTS_PATH, "rb") as f:
    data = pickle.load(f)

results    = data["results"]      # list of per-entity dicts, each with a "categories" sub-dict
generated  = data["generated"]    # timestamp string e.g. "Mon, 14 Sep 2026 06:12 UTC" — actual run time
week_start = data["week_start"]   # datetime object anchored to this week's Monday — used for the masthead date, not run time
date_slug  = data["week_slug"]    # YYYY-MM-DD string used in output filenames
total_a    = data["total_a"]      # total articles collected across all entities and themes
total_t    = data["total_t"]      # subset of total_a where text was successfully extracted

print(f"Loaded {len(results)} entities | {total_a} articles | {total_t} with text")

# ── Tag labels and colours ────────────────────────────────────────────────────
# Tags are applied to articles where these terms appear in the title or text.
# "imagine" flags articles that mention the org by name — displayed as "IW"
# rather than spelled out, since the org's name appearing as visible branding
# on an automated page needs review, but flagging a mention in the underlying
# data is fine.
DEMO_LABELS = {
    "youth":     "Youth",             # youth employment / young people
    "women":     "Women",             # gender gaps in education outcomes
    "disabilit": "Disabilities",      # disability inclusion in education
    "refugee":   "Refugees",          # refugee/displaced learners — e.g. Dzaleka camp programs
    "imagine":   "IW",                # article mentions the org by name — abbreviated in all display output
}

DEMO_COLOURS = {
    "youth":     "#1a3a5c",
    "women":     "#4a2060",
    "disabilit": "#1a5c3a",
    "refugee":   "#7a3a10",
    "imagine":   "#5c1a1a",
}

# ── Production configuration ──────────────────────────────────────────────────
MAX_PER_COUNTRY = 3   # articles shown per country in the production report,
                      # pooled across all themes and ranked by estimated reach score

# Canonical display order — Scale Portfolio first, then Pilot Sites.
ALL_ENTITIES = ["Malawi", "Sierra Leone", "Tanzania", "Burkina Faso", "Ghana", "Liberia"]

# The lead country gets its own dedicated block at the top of the report (a
# featured/lead-story treatment) instead of joining the shared column flow
# below. Change this single value to make a different country the lead.
LEAD_COUNTRY = "Malawi"

# Static, hand-designed illustrations (inline SVG, not extracted from
# articles) — reused identically every week. Only the country's FIRST card
# (by reach score) gets one; every other card stays plain text. Applies only
# to the countries listed here; everyone else never gets an image. See
# render_image_svg() below for the actual artwork, and the "IMAGE" / "END
# IMAGE" comment markers it wraps around each for easy manual swap-in.
IMAGE_COUNTRIES = {
    "Malawi": "book",
    "Ghana":  "tab",
}

# ── Publisher reach scores ────────────────────────────────────────────────────
# Used to rank articles by estimated audience size.
# Scale: 10 = global wire services, 9 = major international, 8 = leading African
# nationals, 7 = strong regional, 6 = smaller local, 3 = unknown (default).
PUBLISHER_REACH = {
    "bbc":             10, "reuters":         10, "apnews":          10,
    "afp":             10, "bloomberg":       10,
    "aljazeera":        9, "theguardian":      9, "economist":        9,
    "ft.com":           9, "washingtonpost":   9, "nytimes":          9,
    "dw.com":           8, "france24":         8, "rfi":              8,
    "voaafrica":        8,
    "theafricareport":  8, "cnbcafrica":       8, "theeastafrican":   8,
    "africafeeds":      7, "africanews":       7, "quartz":           7,
}


def reach_score(article, rss_position):
    """
    Estimate how widely-read an article is likely to be.
    Combines publisher audience size, RSS ranking position, and a bonus for
    successfully extracted text. Higher = more popular.
    """
    url_lo    = article.get("url",    "").lower()
    source_lo = article.get("source", "").lower()
    publisher_score = max(
        (v for k, v in PUBLISHER_REACH.items() if k in url_lo or k in source_lo),
        default=3
    )
    position_score = max(0, 5 - rss_position)
    text_score     = 2 if article.get("paragraphs") else 0
    return publisher_score + position_score + text_score


def has_org_mention(article):
    """Return True if the org's name appears in the article title or any extracted paragraph."""
    haystack = article.get("title", "").lower()
    for p in article.get("paragraphs", []):
        haystack += " " + p.lower()
    return "imagine worldwide" in haystack


def get_all_tags(article):
    """Return the complete list of tags for one article: demographic tags + 'imagine' if the org is mentioned."""
    tags = list(article.get("demo_tags", []))
    if has_org_mention(article):
        tags.append("imagine")
    return tags


# ── HTML helpers ──────────────────────────────────────────────────────────────

def esc(s):
    """Escape special HTML characters to prevent broken markup."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _comment_safe(text):
    """HTML comments can't contain '--', so strip it before dropping text into a comment marker."""
    return text.replace("--", "—")


# ── PART 1: CSV EXPORT ────────────────────────────────────────────────────────

def build_csv(results, path):
    """Write one row per article to a CSV file with all metadata and extracted text."""
    fields = [
        "entity", "pillar", "title", "url", "source", "date",
        "demographics", "iw_mention",
        "text_paragraph_1", "text_paragraph_2", "text_paragraph_3",
        "has_text", "is_google_link", "rss_position", "reach_score",
    ]
    rows = []
    for r in results:
        entity = r["entity"]
        for pillar, articles in r["categories"].items():
            for a in articles:
                paras = a.get("paragraphs", [])
                rows.append({
                    "entity":            entity,
                    "pillar":            pillar,
                    "title":             a["title"],
                    "url":               a["url"],
                    "source":            a.get("source", ""),
                    "date":              a.get("date", ""),
                    "demographics":      ", ".join(
                                            DEMO_LABELS.get(t, t)
                                            for t in a.get("demo_tags", [])
                                         ),
                    "iw_mention":        "yes" if has_org_mention(a) else "no",
                    "text_paragraph_1":  paras[0] if len(paras) > 0 else "",
                    "text_paragraph_2":  paras[1] if len(paras) > 1 else "",
                    "text_paragraph_3":  paras[2] if len(paras) > 2 else "",
                    "has_text":          "yes" if paras else "no",
                    "is_google_link":    "yes" if "google.com" in a["url"] else "no",
                    "rss_position":      a.get("rss_position", ""),
                    "reach_score":       reach_score(a, a.get("rss_position", 99)),
                })
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved CSV: {path}  ({len(rows)} rows)")

csv_path = os.path.join(os.getcwd(), f"education-digest-{date_slug}.csv")
build_csv(results, csv_path)


# ── PART 2: PRODUCTION HTML REPORT ───────────────────────────────────────────

entity_map = {r["entity"]: r for r in results}
prod_date  = week_start.strftime("%A %-d %B %Y")   # e.g. "Monday 15 September 2026" — from the week anchor, not run time


def get_top_articles(entity_data, n=MAX_PER_COUNTRY):
    """
    Pool all articles from all themes for one entity, deduplicate by URL,
    sort by reach score descending, and return the top N.
    Returns list of (pillar_name, article) tuples so the theme label is preserved.
    """
    seen_urls    = set()
    all_articles = []
    for pillar, articles in entity_data["categories"].items():
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                all_articles.append((pillar, a))
    all_articles.sort(
        key=lambda pa: reach_score(pa[1], pa[1].get("rss_position", 99)),
        reverse=True
    )
    return all_articles[:n]


# ── Static per-country images ─────────────────────────────────────────────────
# Hand-designed, not extracted from articles — same artwork every week. Each
# is wrapped in IMAGE / END IMAGE comment markers so swapping in real artwork
# later is a matter of deleting between the markers and pasting an <img> tag
# in their place (the surrounding .np-photo-slot div supplies the frame,
# border, and halftone texture, and doesn't need to change).
_BOOK_SVG = '''<svg viewBox="0 0 320 200" fill="none" stroke="#0d0d0a" stroke-linecap="round" stroke-linejoin="round">
            <g stroke-width="2.2">
              <path d="M160 76 C138 62 78 60 34 68 V178 C78 170 138 172 160 186 C182 172 242 170 286 178 V68 C242 60 182 62 160 76 Z" />
              <path d="M160 76 V186" />
            </g>
            <g stroke-width="1.6" opacity="0.75">
              <path d="M52 90 H140" /><path d="M52 104 H140" /><path d="M52 118 H130" /><path d="M52 132 H140" /><path d="M52 146 H124" /><path d="M52 160 H136" />
              <path d="M180 90 H268" /><path d="M180 104 H268" /><path d="M180 118 H258" /><path d="M180 132 H268" /><path d="M180 146 H252" /><path d="M180 160 H264" />
            </g>
          </svg>'''

_TAB_SVG = '''<svg viewBox="0 0 320 200" fill="none" stroke="#0d0d0a" stroke-linecap="round" stroke-linejoin="round">
            <g stroke-width="1" opacity="0.45">
              <path d="M160 20 L160 2" />
              <path d="M160 20 L130 6" />
              <path d="M160 20 L190 6" />
              <path d="M160 20 L104 16" />
              <path d="M160 20 L216 16" />
            </g>
            <rect x="126" y="18" width="68" height="28" stroke-width="2.2" />
            <rect x="52" y="44" width="216" height="128" stroke-width="2.4" />
            <path d="M76 128 H244" stroke-width="1.3" opacity="0.6" />
            <text x="160" y="112" font-family="Georgia, 'Times New Roman', serif" font-size="46" font-weight="700" fill="#0d0d0a" stroke="none" text-anchor="middle" letter-spacing="2">abcdef</text>
          </svg>'''

_IMAGE_SVGS = {"book": _BOOK_SVG, "tab": _TAB_SVG}


def render_photo_slot(image_kind):
    """Return the .np-photo-slot div (frame + texture) wrapping the named static image, with swap-in comment markers."""
    svg = _IMAGE_SVGS.get(image_kind)
    if not svg:
        return ""
    return (
        '<div class="np-photo-slot">\n'
        '          <!-- ═══ IMAGE: replace the <svg>...</svg> below with your own artwork — e.g. '
        '<img src="your-file.png" alt="" style="width:82%;height:82%;object-fit:contain;"> '
        '— keep this outer .np-photo-slot div as-is, it provides the frame/border/texture ═══ -->\n'
        f'          {svg}\n'
        '          <!-- ═══ END IMAGE ═══ -->\n'
        '        </div>\n'
    )


def render_tags(a):
    tags = get_all_tags(a)
    if not tags:
        return ""
    return '<div class="np-tags">' + "".join(
        f'<span class="np-tag" style="border-color:{DEMO_COLOURS.get(t, "#555")};'
        f'color:{DEMO_COLOURS.get(t, "#555")}">{DEMO_LABELS.get(t, t)}</span>'
        for t in tags
    ) + "</div>\n"


def render_flow_card(pillar, a, image_kind=None):
    """
    Render one card for the continuous-flow section (Sierra Leone through
    Liberia): kicker, optional static image above the headline, headline,
    byline, excerpt. Stacked layout only — this has to fit inside one narrow
    newsprint column, so an image-left/text-right layout would overflow the
    column width and visibly break (this happened once — see the .np-card
    width note in the CSS).
    Wrapped in ARTICLE / END ARTICLE comment markers for easy manual removal.
    """
    title_marker = _comment_safe(a["title"])[:80]
    meta  = " — ".join(p for p in [a.get("source", ""), a.get("date", "")] if p)
    paras = a.get("paragraphs", [])

    if paras:
        excerpt_html = "".join(f"<p>{esc(p)}</p>" for p in paras)
    elif a.get("url"):
        # No excerpt was extracted — mark exactly where one could be added by hand.
        excerpt_html = (
            '<!-- NO EXCERPT — to add one, replace the <p class="np-read-link"> line below with:\n'
            '     <p>First paragraph…</p><p>Second paragraph… (optional)</p> -->\n'
            f'<p class="np-read-link"><a href="{esc(a["url"])}" target="_blank" rel="noopener">Read article</a></p>'
        )
    else:
        excerpt_html = ""

    photo_html = render_photo_slot(image_kind)

    return (
        f'<!-- ══════ ARTICLE: {title_marker} — delete this whole block down to "END ARTICLE" to remove it ══════ -->\n'
        f'<div class="np-card">\n'
        f'      <div class="np-kicker">{esc(pillar)}</div>\n'
        f'      {photo_html}'
        f'{render_tags(a)}'
        f'      <div class="np-hed"><a href="{esc(a["url"])}" target="_blank" rel="noopener">{esc(a["title"])}</a></div>\n'
        + (f'      <div class="np-byline">{esc(meta)}</div>\n' if meta else "")
        + f'      <div class="np-excerpt">{excerpt_html}</div>\n'
        f'    </div>\n'
        f'<!-- ══════ END ARTICLE ══════ -->\n'
    )


def render_lead_card(pillar, a, image_kind):
    """
    Render the lead country's featured (top-ranked) card: the image floats
    left and text wraps around it, then continues at full width once the
    text passes the image's height — a float, not a grid, specifically so
    long excerpts don't leave an ugly gap next to a short image.
    """
    title_marker = _comment_safe(a["title"])[:80]
    meta  = " — ".join(p for p in [a.get("source", ""), a.get("date", "")] if p)
    paras = a.get("paragraphs", [])

    if paras:
        excerpt_html = "".join(f"<p>{esc(p)}</p>" for p in paras)
    elif a.get("url"):
        # No excerpt was extracted — mark exactly where one could be added by hand.
        excerpt_html = (
            '<!-- NO EXCERPT — to add one, replace the <p class="np-read-link"> line below with:\n'
            '     <p>First paragraph…</p><p>Second paragraph… (optional)</p> -->\n'
            f'<p class="np-read-link"><a href="{esc(a["url"])}" target="_blank" rel="noopener">Read article</a></p>'
        )
    else:
        excerpt_html = ""

    photo_html = render_photo_slot(image_kind)

    return (
        f'<!-- ══════ ARTICLE: {title_marker} — delete this whole block down to "END ARTICLE" to remove it ══════ -->\n'
        f'<div class="np-card--media">\n'
        f'      <div class="np-card-media">\n'
        f'        {photo_html}'
        f'      </div>\n'
        f'      <div class="np-kicker">{esc(pillar)}</div>\n'
        f'{render_tags(a)}'
        f'      <div class="np-hed"><a href="{esc(a["url"])}" target="_blank" rel="noopener">{esc(a["title"])}</a></div>\n'
        + (f'      <div class="np-byline">{esc(meta)}</div>\n' if meta else "")
        + f'      <div class="np-excerpt">{excerpt_html}</div>\n'
        f'    </div>\n'
        f'<!-- ══════ END ARTICLE ══════ -->\n'
    )


def render_lead_section(entity, entity_data):
    """
    The lead country's dedicated block: its top card gets the float/media
    treatment (with its static image, if it has one); any additional cards
    for the same country are plain stacked cards below — never paired
    side-by-side, so there's nothing to misalign.
    Returns '' if the lead country has no articles this week.
    """
    top_pairs = get_top_articles(entity_data)
    if not top_pairs:
        return ""

    image_kind = IMAGE_COUNTRIES.get(entity)
    html = f'<div class="np-country">{esc(entity)}</div>\n'

    first_pillar, first_article = top_pairs[0]
    html += render_lead_card(first_pillar, first_article, image_kind)

    for pillar, a in top_pairs[1:]:
        html += render_flow_card(pillar, a, image_kind=None)

    return html


def render_country_flow(entity, entity_data):
    """
    One country's heading plus its cards for the continuous-flow section.
    Only its first (top-ranked) card can carry a static image, and only if
    this entity is in IMAGE_COUNTRIES. Returns '' if no articles.
    """
    top_pairs = get_top_articles(entity_data)
    if not top_pairs:
        return ""

    image_kind = IMAGE_COUNTRIES.get(entity)
    html = f'<div class="np-country">{esc(entity)}</div>\n'
    for i, (pillar, a) in enumerate(top_pairs):
        html += render_flow_card(pillar, a, image_kind=(image_kind if i == 0 else None))
    return html


# ── Assemble the two sections ───────────────────────────────────────────────
lead_entity_data = entity_map.get(LEAD_COUNTRY)
lead_html = render_lead_section(LEAD_COUNTRY, lead_entity_data) if lead_entity_data else ""

_flow_parts = []
for _entity in ALL_ENTITIES:
    if _entity == LEAD_COUNTRY:
        continue
    _data = entity_map.get(_entity)
    if not _data:
        continue
    _part = render_country_flow(_entity, _data)
    if _part:
        _flow_parts.append(_part)

flow_html = "\n".join(_flow_parts)
if not flow_html:
    flow_html = '<p class="np-empty">No results available this week.</p>\n'

divider_html = '<div class="np-divider"></div>\n' if lead_html and _flow_parts else ""
if not lead_html and not _flow_parts:
    # Nothing at all this week, from any country — still produce a valid page.
    lead_html = '<p class="np-empty">No results available this week.</p>\n'
    flow_html = ""


# ── Assemble production HTML ──────────────────────────────────────────────────
# The HTML string uses double-braces {{ }} to escape literal braces inside
# the f-string (Python f-strings use single braces for expressions).
prod_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Education News Roundup — {prod_date}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Oswald:wght@500;600;700&family=PT+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; border-radius: 0 !important; box-shadow: none !important; }}
:root {{ --page-bg: #d9d4c2; --ink: #0d0d0a; --ink-3: #4a463c; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ --page-bg: #15140f; --ink: #ece8de; --ink-3: #b0ab99; }}
}}
:root[data-theme="dark"] {{ --page-bg: #15140f; --ink: #ece8de; --ink-3: #b0ab99; }}

body {{ background: var(--page-bg); font-family: 'PT Serif', Georgia, serif; padding: 24px 12px 80px; }}

.np {{
  max-width: 980px; margin: 0 auto; color: var(--ink);
  background: #f0ecdf;
  background-image: radial-gradient(rgba(0,0,0,0.05) 0.6px, transparent 0.6px);
  background-size: 2.4px 2.4px;
  border: 1px solid var(--ink);
}}
.np-masthead {{ padding: 16px 20px 0; text-align: center; }}
.np-emblem {{ display: block; margin: 0 auto 4px; }}
.np-h1 {{
  font-family: 'Playfair Display', serif; font-weight: 900; font-size: 64px; line-height: 0.92;
  letter-spacing: -0.02em; text-transform: uppercase; margin: 6px 0 2px;
}}
.np-rule-heavy {{ height: 7px; background: var(--ink); margin: 4px 0 0; }}
.np-rule-thin  {{ height: 1px; background: var(--ink); margin: 2px 0 0; }}
.np-dateline {{
  font-family: 'Oswald', sans-serif; font-size: 11px; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--ink-3); padding: 6px 20px 8px; border-bottom: 3px solid var(--ink); text-align: center;
}}
.np-body {{ padding: 0 20px 24px; }}

.np-country {{
  font-family: 'Playfair Display', serif; font-weight: 900; font-size: 34px; text-transform: uppercase;
  letter-spacing: -0.01em; line-height: 1; border-bottom: 3px solid var(--ink); padding: 10px 0 6px; margin-bottom: 12px;
  break-after: avoid; break-inside: avoid;
}}
.np-divider {{ height: 1px; background: var(--ink-3); opacity: 0.4; margin: 36px 0 4px; }}
.np-empty {{ font-family: 'Oswald', sans-serif; font-size: 13px; color: var(--ink-3); font-style: italic; padding: 12px 0; }}

/* Continuous flow section: real 2-column newsprint text */
.np-columns {{ columns: 2; column-gap: 20px; column-rule: 1px solid var(--ink); }}
.np-card {{ break-inside: avoid; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid #a89f88; }}

/* Lead country's featured card — float, NOT grid, so long excerpts wrap
   around the image then continue full-width instead of leaving a gap */
.np-card--media {{ margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #a89f88; break-inside: avoid; }}
.np-card--media::after {{ content: ''; display: table; clear: both; }}
.np-card-media {{ float: left; width: 260px; margin-right: 22px; margin-bottom: 10px; }}
.np-card-media .np-photo-slot {{ margin-bottom: 0; }}

.np-kicker {{ font-family: 'Oswald', sans-serif; font-size: 9.5px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 2px; }}
.np-hed {{ font-family: 'PT Serif', Georgia, serif; font-size: 17.5px; font-weight: 700; line-height: 1.15; letter-spacing: -0.01em; margin-bottom: 3px; }}
.np-hed a {{ color: var(--ink); text-decoration: none; }}
.np-byline {{ font-family: 'Oswald', sans-serif; font-size: 9.5px; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 5px; }}
.np-excerpt {{ font-family: 'PT Serif', Georgia, serif; font-size: 12.5px; line-height: 1.42; text-align: justify; hyphens: auto; color: #1c1a14; }}
.np-excerpt p {{ margin-bottom: 4px; }}
.np-read-link {{ font-family: 'Oswald', sans-serif; font-size: 11px; }}
.np-read-link a {{ color: var(--ink); text-decoration: underline; }}

.np-photo-slot {{
  width: 100%; aspect-ratio: 16/10; margin-bottom: 8px; position: relative; overflow: hidden;
  background: #e4dfcd; border: 1.5px solid var(--ink); display: flex; align-items: center; justify-content: center;
}}
.np-photo-slot svg {{ width: 82%; height: 82%; }}
.np-photo-slot::after {{
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background-image: radial-gradient(circle, var(--ink) 0.6px, transparent 0.6px);
  background-size: 3.2px 3.2px; opacity: 0.28; mix-blend-mode: multiply;
}}

.np-tags {{ margin-bottom: 6px; }}
.np-tag {{
  display: inline-block; font-family: 'Oswald', sans-serif; font-size: 9px; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; padding: 2px 6px; border: 1px solid currentColor;
  margin-right: 5px;
}}

.np-footer {{
  font-family: 'Oswald', sans-serif; font-size: 10.5px; color: var(--ink-3); text-align: center;
  padding: 22px 20px; border-top: 3px double var(--ink); line-height: 1.9;
}}
.np-footer strong {{ color: var(--ink); font-family: 'Playfair Display', serif; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }}
.np-footer .np-tag-legend {{ font-family: 'Oswald', sans-serif; font-size: 10.5px; text-transform: none; letter-spacing: 0.04em; }}

@media (max-width: 620px) {{
  .np-columns {{ columns: 1; }}
  .np-card-media {{ float: none; width: 100%; margin-right: 0; }}
  .np-h1 {{ font-size: 38px; }}
}}
</style>
</head>
<body>

<div class="np">
  <div class="np-masthead">
    <svg class="np-emblem" width="40" height="30" viewBox="0 0 48 36" fill="none" stroke="#0d0d0a" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M24 6 C18 3 10 3 4 5 V29 C10 27 18 27 24 30 C30 27 38 27 44 29 V5 C38 3 30 3 24 6 Z" />
      <path d="M24 6 V30" />
      <path d="M8 10 H18 M8 14 H18 M8 18 H16" />
      <path d="M30 10 H40 M30 14 H40 M32 18 H40" />
    </svg>
    <div class="np-h1">Education News Roundup</div>
  </div>
  <div class="np-rule-heavy"></div>
  <div class="np-rule-thin"></div>
  <div class="np-dateline">{prod_date}</div>

  <div class="np-body">
    {lead_html}
    {divider_html}
    <div class="np-columns">
      {flow_html}
    </div>
  </div>

  <div class="np-footer">
    <strong>Education News Roundup</strong><br>
    {prod_date} &nbsp;·&nbsp; {generated}<br>
    Articles sourced from Google News RSS · Top {MAX_PER_COUNTRY} per country ranked by estimated reach<br>
    Excerpts reproduced verbatim from publisher pages where accessible<br><br>
    This roundup is produced automatically through a news scraper. Kindly click each article
    title to read the full piece on the original publisher's site. Content has not always been
    editorially reviewed.<br><br>
    Tags applied where terms appear in article titles or extracted text:
    <strong class="np-tag-legend">Youth · Women · Disabilities · Refugees · IW</strong>
  </div>
</div>

</body>
</html>"""

# ── Save the production report ────────────────────────────────────────────────
prod_filename = f"education-digest-{date_slug}.html"
prod_path     = os.path.join(os.getcwd(), prod_filename)
with open(prod_path, "w", encoding="utf-8") as f:
    f.write(prod_html)
print(f"Saved production report: {prod_path}")


# ── Update the archive index.html ─────────────────────────────────────────────
index_path      = os.path.join(os.getcwd(), "index.html")
archive_entries = []

if os.path.exists(index_path):
    with open(index_path, "r", encoding="utf-8") as f:
        existing = f.read()
    for m in re.finditer(
        r'href="(education-digest-[\d-]+\.html)"[^>]*>([^<]+)<', existing
    ):
        entry = (m.group(1), m.group(2))
        if entry not in archive_entries:
            archive_entries.append(entry)

this_entry = (prod_filename, prod_date)
if this_entry not in archive_entries:
    archive_entries.insert(0, this_entry)

archive_rows = "\n".join(
    f'    <li><a href="{fn}">{label}</a></li>'
    for fn, label in archive_entries
)

index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Education News Roundup</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@900&family=Oswald:wght@500;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; border-radius: 0 !important; }}
:root {{ --page-bg: #d9d4c2; --ink: #0d0d0a; --ink-3: #4a463c; }}
body {{ font-family: 'PT Serif', Georgia, serif; background: var(--page-bg); color: var(--ink); }}
.masthead {{ border-bottom: 3px double var(--ink); padding: 48px 24px 24px; text-align: center; max-width: 700px; margin: 0 auto; }}
.eyebrow {{ font-family: 'Oswald', sans-serif; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 12px; }}
h1 {{ font-family: 'Playfair Display', serif; font-weight: 900; text-transform: uppercase; font-size: clamp(24px, 5vw, 40px); line-height: 1.1; margin-bottom: 10px; }}
.dateline {{ font-family: 'Oswald', sans-serif; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); border-top: 1px solid var(--ink-3); padding-top: 10px; margin-top: 14px; }}
.container {{ max-width: 600px; margin: 52px auto 80px; padding: 0 20px; }}
h2 {{ font-family: 'Oswald', sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); border-bottom: 1px solid var(--ink-3); padding-bottom: 8px; margin-bottom: 20px; }}
ul {{ list-style: none; }}
li {{ border-bottom: 1px solid var(--ink-3); }}
li a {{ display: block; padding: 14px 0; font-size: 16px; color: var(--ink); text-decoration: none; }}
li a:hover {{ text-decoration: underline; }}
.footer {{ text-align: center; font-family: 'Oswald', sans-serif; font-size: 11px; color: var(--ink-3); padding: 32px 24px; border-top: 1px solid var(--ink-3); max-width: 700px; margin: 0 auto; line-height: 1.7; }}
</style>
</head>
<body>
<div class="masthead">
  <p class="eyebrow">Archive</p>
  <h1>Education News Roundup</h1>
  <p class="dateline">All issues</p>
</div>
<div class="container">
  <h2>Issues</h2>
  <ul>
{archive_rows}
  </ul>
</div>
<div class="footer">
  Produced automatically each week from Google News RSS.<br>
  Content has not always been editorially reviewed.
</div>
</body>
</html>"""

with open(index_path, "w", encoding="utf-8") as f:
    f.write(index_html)
print(f"Saved archive index: {index_path}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\nFiles ready to commit:")
print(f"  {prod_filename}                  ← this week's digest")
print(f"  index.html                       ← updated archive listing")
print(f"  education-digest-{date_slug}.csv  ← full data export")
