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
import re                      # regular expressions for anchor-safe string cleaning
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
# "imagine" replaces the old job's "wdl" (World Data Lab) tag — here it flags
# articles that mention the org by name, which is more useful for
# this digest than for the prior one. Displayed as "IW" rather than spelled
# out, pending internal review before the org's name appears in public output.
DEMO_LABELS = {
    "youth":     "Youth",             # youth employment / young people
    "women":     "Women",             # gender gaps in education outcomes
    "disabilit": "Disabilities",      # disability inclusion in education
    "refugee":   "Refugees",          # refugee/displaced learners — e.g. Dzaleka camp programs
    "imagine":   "IW",                # article mentions the org by name — abbreviated in all display output
}

DEMO_COLOURS = {
    "youth":     "#1a3a5c",   # dark navy
    "women":     "#4a2060",   # deep plum
    "disabilit": "#1a5c3a",   # dark green
    "refugee":   "#7a3a10",   # dark amber
    "imagine":   "#5c1a1a",   # dark crimson — visually distinct from the demographics
}

# ── Production configuration ──────────────────────────────────────────────────
MAX_PER_COUNTRY = 3   # articles shown per country in the production report,
                      # pooled across all themes and ranked by estimated reach score

# The two country groupings shown as separate sections in the report
SCALE_PORTFOLIO = ["Malawi", "Sierra Leone", "Tanzania"]
PILOT_SITES     = ["Burkina Faso", "Ghana", "Liberia"]

# Order themes appear under each country in the production report
# Government & Program Context always last — only shown where PROGRAM_INTERESTS defined it
PILLAR_ORDER = [
    "Policy, Budget & Funding",
    "Learning Outcomes & Assessment",
    "Technology & Innovation in Education",
    "Teachers, Schools & Continuity",
    "Education & the Workforce",
    "IW Mentions",
    "Government & Program Context",   # only appears where PROGRAM_INTERESTS defined it — Malawi/Sierra Leone/Tanzania/Burkina Faso
]

# ── Publisher reach scores ────────────────────────────────────────────────────
# Used to rank articles by estimated audience size.
# Scale: 10 = global wire services, 9 = major international, 8 = leading African
# nationals, 7 = strong regional, 6 = smaller local, 3 = unknown (default).
# Kept generic — none of these confirmed as specific to Malawi/Sierra Leone/
# Tanzania/Ghana/Liberia/Burkina Faso, but the global and pan-African outlets
# still apply, and everything else defaults to 3 rather than being ignored.
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

def make_anchor(s):
    """Convert a country name to a valid HTML id attribute (alphanumeric + underscore)."""
    return re.sub(r"[^\w]", "_", s)


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
                    "iw_mention":   "yes" if has_org_mention(a) else "no",
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


def render_article_card(a):
    """Render one article as a clean editorial card. 'Read article' appears as a hyperlink when no excerpt text is available."""
    is_google = "google.com" in a["url"]
    tags      = get_all_tags(a)

    tags_html = ""
    if tags:
        tags_html = '<div class="tags">' + "".join(
            f'<span class="tag" style="border-color:{DEMO_COLOURS.get(t, "#555")};'
            f'color:{DEMO_COLOURS.get(t, "#555")}">'
            f'{DEMO_LABELS.get(t, t)}</span>'
            for t in tags
        ) + "</div>"

    meta = " · ".join(p for p in [a.get("source", ""), a.get("date", "")] if p)

    paras = a.get("paragraphs", [])
    if paras:
        ex_html = (
            '<div class="excerpt">'
            + "".join(f"<p>{esc(p)}</p>" for p in paras)
            + "</div>"
        )
    elif is_google or a.get("url"):
        ex_html = (
            f'<p class="read-link">'
            f'<a href="{esc(a["url"])}" target="_blank" rel="noopener">Read article</a>'
            f'</p>'
        )
    else:
        ex_html = ""

    return (
        '<article class="card">\n'
        + tags_html
        + f'<h4 class="card-hed">'
          f'<a href="{esc(a["url"])}" target="_blank" rel="noopener">'
          f'{esc(a["title"])}</a></h4>\n'
        + (f'<p class="card-meta">{esc(meta)}</p>\n' if meta else "")
        + ex_html
        + "\n</article>\n"
    )


def render_entity_block(entity, entity_data):
    """
    Render one country: a heading, then articles grouped by theme.
    Top N articles are selected by reach score across all themes, then
    grouped under their theme label for display, in PILLAR_ORDER.
    Returns empty string if no articles at all this week — caller skips it.
    A theme with zero matching articles simply doesn't appear; there is no
    per-theme "no results" placeholder, only a whole-section fallback (see
    render_section below).
    """
    top_pairs = get_top_articles(entity_data)
    if not top_pairs:
        return ""

    from collections import defaultdict
    by_pillar = defaultdict(list)
    for pillar, a in top_pairs:
        by_pillar[pillar].append(a)

    anchor = make_anchor(entity)
    html   = f'<div class="entity-block" id="{anchor}">\n'
    html  += f'<h3 class="entity-hed">{esc(entity)}</h3>\n'

    for pillar in PILLAR_ORDER:
        articles = by_pillar.get(pillar, [])
        if not articles:
            continue                          # this theme had no results for this entity this week — skip it, no placeholder
        html += f'<div class="pillar-block">\n'
        html += f'<div class="pillar-label">{esc(pillar)}</div>\n'
        for a in articles:
            html += render_article_card(a)
        html += "</div>\n"

    html += "</div>\n"
    return html


def render_section(section_label, section_id, entities):
    """Render one country-group section. Skips countries with no articles. Shows a fallback message only if the whole section is empty."""
    body = ""
    for entity in entities:
        data = entity_map.get(entity)
        if not data:
            continue
        block = render_entity_block(entity, data)
        if block:
            body += block
    if not body:
        body = '<p class="empty">No results available this week.</p>\n'
    return (
        f'<section class="geo-section" id="{section_id}">\n'
        f'<div class="section-rule">'
        f'<span class="section-label">{esc(section_label)}</span>'
        f'</div>\n'
        + body
        + "</section>\n"
    )


# Build the two country-group sections
scale_html = render_section("Scale Portfolio Countries", "scale", SCALE_PORTFOLIO)
pilot_html = render_section("Pilot Sites",                "pilot", PILOT_SITES)


def sidebar_nav():
    """Build the left sidebar: a vertical index of all countries with anchor links."""
    html  = '<nav class="sidebar">\n<div class="sidebar-inner">\n'
    html += '<p class="nav-section-label">Scale Portfolio</p>\n'
    for entity in SCALE_PORTFOLIO:
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    html += '<p class="nav-section-label">Pilot Sites</p>\n'
    for entity in PILOT_SITES:
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    html += '</div>\n</nav>\n'
    return html

nav_html = sidebar_nav()

# ── Assemble production HTML ──────────────────────────────────────────────────
# The HTML string uses double-braces {{ }} to escape literal braces inside
# the f-string (Python f-strings use single braces for expressions).
prod_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly Education Landscape Digest — {prod_date}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --paper:      #f5f2eb;
  --ink:        #1a1a18;
  --ink-2:      #3d3d38;
  --ink-3:      #7a7a72;
  --rule:       #ccc9be;
  --rule-heavy: #1a1a18;
  --accent:     #1c3d5c;
  --serif:      "Georgia", "Times New Roman", serif;
  --sans:       "Helvetica Neue", "Arial", sans-serif;
  --sidebar-w:  180px;
}}

html {{ scroll-behavior: smooth; font-size: 16px; }}
body {{ font-family: var(--serif); background: var(--paper); color: var(--ink); line-height: 1.7; }}

.masthead {{
  border-bottom: 3px double var(--rule-heavy);
  padding: 36px 24px 20px;
  text-align: center;
  max-width: 1100px;
  margin: 0 auto;
}}
.masthead-eyebrow {{
  font-family: var(--sans);
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: 10px;
}}
.masthead h1 {{
  font-family: var(--serif);
  font-size: clamp(26px, 4vw, 46px);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--ink);
  margin-bottom: 10px;
}}
.masthead-dateline {{
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-top: 1px solid var(--rule);
  border-bottom: 1px solid var(--rule);
  padding: 7px 0;
  margin-top: 14px;
}}

.page-wrap {{
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  align-items: flex-start;
  padding: 0 0 80px;
}}

.sidebar {{
  width: var(--sidebar-w);
  flex-shrink: 0;
  border-right: 1px solid var(--rule);
  position: sticky;
  top: 0;
  max-height: 100vh;
  overflow-y: auto;
  padding: 28px 0;
}}
.sidebar-inner {{ padding: 0 16px; }}
.nav-section-label {{
  font-family: var(--sans);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--rule);
  padding-bottom: 5px;
  margin: 20px 0 8px;
}}
.nav-section-label:first-child {{ margin-top: 0; }}
.nav-link {{
  display: block;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  padding: 3px 0;
  line-height: 1.4;
}}
.nav-link:hover {{ text-decoration: underline; }}

.content {{
  flex: 1;
  min-width: 0;
  padding: 28px 32px;
}}

.geo-section {{ margin-bottom: 60px; }}
.section-rule {{
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
  margin-top: 52px;
}}
.geo-section:first-child .section-rule {{ margin-top: 0; }}
.section-rule::before {{
  content: '';
  flex: 0 0 32px;
  height: 3px;
  background: var(--rule-heavy);
}}
.section-rule::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--rule);
}}
.section-label {{
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink);
  white-space: nowrap;
}}

.entity-block {{ margin-bottom: 44px; }}
.entity-hed {{
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  border-bottom: 1px solid var(--rule);
  padding-bottom: 8px;
  margin-bottom: 18px;
  letter-spacing: -0.01em;
}}

.card {{
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--rule);
}}
.card:last-child {{
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}}
.card-hed {{
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.35;
  margin-bottom: 5px;
}}
.card-hed a {{ color: var(--ink); text-decoration: none; }}
.card-hed a:hover {{ color: var(--accent); text-decoration: underline; }}
.card-meta {{
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.03em;
  margin-bottom: 10px;
}}
.excerpt {{
  font-family: var(--serif);
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-2);
}}
.excerpt p {{ margin-bottom: 8px; }}
.excerpt p:last-child {{ margin: 0; }}
.read-link {{
  font-family: var(--sans);
  font-size: 12px;
  margin-top: 6px;
}}
.read-link a {{ color: var(--accent); text-decoration: underline; }}

.tags {{ margin-bottom: 8px; }}
.tag {{
  display: inline-block;
  font-family: var(--sans);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 6px;
  border: 1px solid currentColor;
  border-radius: 2px;
  margin-right: 5px;
  line-height: 1.6;
}}

.footer {{
  border-top: 3px double var(--rule);
  padding: 32px 24px;
  text-align: center;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.8;
  max-width: 1100px;
  margin: 0 auto;
}}
.footer strong {{ color: var(--ink-2); }}

@media (max-width: 700px) {{
  .page-wrap {{ flex-direction: column; }}
  .sidebar {{
    width: 100%;
    position: static;
    max-height: none;
    border-right: none;
    border-bottom: 1px solid var(--rule);
    padding: 16px 0;
    overflow-y: visible;
  }}
  .sidebar-inner {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px 12px;
    padding: 0 16px;
  }}
  .nav-section-label {{ width: 100%; margin: 10px 0 4px; }}
  .content {{ padding: 20px 16px; }}
}}

.empty {{ font-family: var(--sans); font-size: 13px; color: var(--ink-3); font-style: italic; }}
</style>
</head>
<body>

<header class="masthead">
  <p class="masthead-eyebrow">Weekly Education Landscape Digest</p>
  <h1>Education Landscape<br>Scale &amp; Pilot Countries</h1>
  <p class="masthead-dateline">{prod_date}</p>
</header>

<div class="page-wrap">

  {nav_html}

  <main class="content">
    {scale_html}
    {pilot_html}
  </main>

</div>

<footer class="footer">
  <strong>Weekly Education Landscape Digest: Scale &amp; Pilot Countries</strong><br>
  {prod_date} &nbsp;·&nbsp; {generated}<br>
  Articles sourced from Google News RSS · Top {MAX_PER_COUNTRY} per country ranked by estimated reach<br>
  Excerpts reproduced verbatim from publisher pages where accessible<br><br>
  This roundup is produced automatically through a news scraper. Kindly click each article
  title to read the full piece on the original publisher's site. Content has not been
  editorially reviewed.<br><br>
  Tags applied where terms appear in article titles or extracted text:
  <strong>Youth · Women · Disabilities · Refugees · IW</strong>
</footer>

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
<title>Weekly Education Landscape Digest</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{ --paper: #f5f2eb; --ink: #1a1a18; --ink-3: #7a7a72; --accent: #1c3d5c; --rule: #ccc9be; }}
body {{ font-family: Georgia, serif; background: var(--paper); color: var(--ink); }}
.masthead {{
  border-bottom: 3px double var(--ink);
  padding: 48px 24px 24px;
  text-align: center;
  max-width: 700px;
  margin: 0 auto;
}}
.eyebrow {{ font-family: sans-serif; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 12px; }}
h1 {{ font-size: clamp(24px, 5vw, 40px); font-weight: 700; line-height: 1.15; margin-bottom: 10px; }}
.dateline {{ font-family: sans-serif; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); border-top: 1px solid var(--rule); padding-top: 10px; margin-top: 14px; }}
.container {{ max-width: 600px; margin: 52px auto 80px; padding: 0 20px; }}
h2 {{ font-family: sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); border-bottom: 1px solid var(--rule); padding-bottom: 8px; margin-bottom: 20px; }}
ul {{ list-style: none; }}
li {{ border-bottom: 1px solid var(--rule); }}
li a {{ display: block; padding: 14px 0; font-size: 16px; color: var(--accent); text-decoration: none; }}
li a:hover {{ color: var(--ink); }}
.footer {{ text-align: center; font-family: sans-serif; font-size: 11px; color: var(--ink-3); padding: 32px 24px; border-top: 1px solid var(--rule); max-width: 700px; margin: 0 auto; line-height: 1.7; }}
</style>
</head>
<body>
<div class="masthead">
  <p class="eyebrow">Archive</p>
  <h1>Weekly Education Landscape Digest:<br>Scale &amp; Pilot Countries</h1>
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
  Content has not been editorially reviewed.
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
