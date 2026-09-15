# education_search.py
# Weekly education-landscape digest — search script.
# Covers the org's Scale Portfolio and Pilot Site countries,
# scans Google News RSS for education-related coverage, extracts article
# text where possible, and saves results.pkl for education_export.py to
# turn into the HTML report and CSV.

import subprocess, sys                        # subprocess runs pip; sys gives the current Python executable
subprocess.run(                                   # install required libraries silently if not already present
    [sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "lxml", "-q"],
    check=False                                   # do not raise an error if pip prints warnings
)

import requests
import xml.etree.ElementTree as ET
import urllib.parse
import re
import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ── Countries covered ─────────────────────────────────────────────────────────
# Split into the two groups used internally, so the export script can
# show them as two separate sections in the report.

SCALE_PORTFOLIO = ["Malawi", "Sierra Leone", "Tanzania"]      # countries with national government-scale programs (BEFIT, Pikin Tab, MsingiTek)
PILOT_SITES     = ["Burkina Faso", "Ghana", "Liberia"]        # newer pilot-stage countries

ALL_ENTITIES = SCALE_PORTFOLIO + PILOT_SITES   # 6 entities total — small enough to run as a single job, no sharding needed

# ── Search themes ─────────────────────────────────────────────────────────────
# Each theme has one or more keyword strings that get OR-joined in the RSS
# query. Multiple keyword strings per theme = multiple RSS calls, results
# merged together under that theme.

CATEGORIES = {
    "Government Policy & Budget": [
        '"education policy" OR "curriculum reform" OR "education budget" OR "ministry of education" OR "education funding"',
        '"national education plan" OR "free primary education" OR "school fees" OR "public education spending"',
    ],
    "Learning Outcomes & Assessment": [
        '"literacy assessment" OR "numeracy assessment" OR "learning outcomes" OR "learning poverty" OR "EGRA" OR "EGMA"',
        '"national exam results" OR "student achievement" OR "foundational learning"',
    ],
    "EdTech & Digital Learning": [
        '"education technology" OR "edtech" OR "digital learning" OR "tablet program" OR "e-learning"',
        '"school digitization" OR "ICT in education" OR "online learning platform"',
    ],
    "Teachers & School Infrastructure": [
        '"teacher training" OR "teacher shortage" OR "untrained teachers" OR "teacher deployment"',
        '"school infrastructure" OR "school electricity" OR "school connectivity" OR "solar power schools" OR "device repair"',
    ],
    "Donor & Funding Landscape": [
        '"donor funding" OR "NGO partnership" OR "international aid" education',
        '"Global Partnership for Education" OR "USAID education" OR "World Bank education" OR "UNICEF education" OR "Audacious Project" OR "cost per child"',
    ],
    "Education & the Workforce": [
        '"school to work transition" OR "youth employment" education OR "skills gap" OR "graduate employability" OR "TVET"',
        '"education outcomes" employment OR "human capital" OR "labor market skills" OR "education economic growth"',
    ],
    "IW Mentions": [
        '"Imagine Worldwide"',   # the actual search phrase has to stay the real org name for the RSS query to work — only the display label above is abbreviated; specific enough to be low-noise, but not a registered proper noun, so some false positives are expected and fine to skim past
    ],
}

# ── Program-specific context ──────────────────────────────────────────────────
# Only the three Scale Portfolio countries have named government programs.
# Where defined, this runs as an extra "Program-Specific Context" theme for
# that entity only — Pilot Site countries simply don't get this theme added,
# same pattern as the old job's QRM country-interest layer, just without the
# WAEMU-style name substitution since each program name is unique here.
PROGRAM_INTERESTS = {
    "Malawi": [
        '"BEFIT" OR "Building Education Foundations through Innovation and Technology" OR "Ministry of Education Science and Technology Malawi"',
    ],
    "Sierra Leone": [
        '"Pikin Tab" OR "Digital Foundational Learning Program" OR "MBSSE" Sierra Leone',
    ],
    "Tanzania": [
        '"MsingiTek" OR "PO-RALG" Tanzania',
    ],
}


def get_program_context(entity):
    """Return the Program-Specific Context keyword list for an entity, or empty list if none defined."""
    return PROGRAM_INTERESTS.get(entity, [])   # Ghana/Liberia/Burkina Faso return [] — theme is skipped entirely for them


# ── Demographic tags ───────────────────────────────────────────────────────────
# Applied to articles where these terms appear in the title — shown as badges
# on each article card in the report. Still relevant here: gender gaps in
# learning outcomes, disability inclusion, and refugee learners (e.g. Dzaleka
# camp in Malawi) all come up in the org's own reporting.
DEMOGRAPHICS = ["youth", "women", "disabilit", "refugee"]
DEMO_LABELS  = {"youth": "youth", "women": "women", "disabilit": "disabilities", "refugee": "refugees"}
DEMO_COLOURS = {"youth": "#1a6fbf", "women": "#9b2e8a", "disabilit": "#2e8a4a", "refugee": "#bf6a1a"}

TEST_MODE     = False   # set True to run only TEST_ENTITIES — useful for quick local testing
TEST_ENTITIES = ["Malawi", "Ghana"]   # one Scale country + one Pilot country when TEST_MODE is True

MAX_ARTICLES_PER_CAT = 5   # maximum articles collected per keyword string per theme
MAX_PARAGRAPHS       = 3      # maximum paragraphs extracted from each article page
DELAY                = 0.8    # seconds between article fetches — keeps requests at human speed
TIMEOUT              = 12     # seconds before giving up on a single HTTP request

# ── Week anchor (NOT the same as "now") ───────────────────────────────────────
# Anchor the search window to this week's Monday rather than the exact moment
# the job executes, so a retry later in the week never shifts or overlaps the
# date range being searched — same fix applied to the africa-monitor repo.
TODAY      = datetime.utcnow()                                   # exact run time — used only for display ("generated"), never for the search window or filenames
WEEK_START = TODAY - timedelta(days=TODAY.weekday())              # TODAY.weekday(): Monday=0 ... Sunday=6, so this steps back to this week's Monday
WEEK_START = WEEK_START.replace(hour=0, minute=0, second=0, microsecond=0)   # zero out the time-of-day so it's a stable midnight anchor
DATE_FROM  = (WEEK_START - timedelta(days=7)).strftime("%Y-%m-%d")   # RSS filter: the Monday before this week's Monday — one full week, fixed per week
WEEK_SLUG  = WEEK_START.strftime("%Y-%m-%d")                      # e.g. 2026-09-15 — identical across every run/retry covering this week

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

BOILERPLATE = [
    "subscribe", "sign in", "sign up", "log in", "cookie policy", "privacy policy",
    "terms of use", "all rights reserved", "advertisement", "follow us", "share this",
    "enable javascript", "© 20", "you have reached", "become a member",
    "already a subscriber", "get unlimited", "to continue reading",
    "for full access", "free articles left", "digital subscription", "paywall",
]

BODY_SELECTORS = [
    "[itemprop='articleBody']", "article",
    "[class*='article-body']", "[class*='story-body']", "[class*='post-body']",
    "[class*='entry-content']", "[class*='post-content']", "[class*='article-content']",
    "[class*='article-text']", "[class*='story-text']", "[class*='content-body']",
    "[class*='body-text']", "[class*='body-copy']", "[class*='field-body']",
    "main", "#content", "#main", ".content",
]

NOISE_TAGS = [
    "script", "style", "nav", "header", "footer", "aside", "figure",
    "figcaption", "form", "button", "noscript", "iframe",
]

STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is",
    "are", "was", "were", "by", "as", "with", "its", "from", "this", "that",
    "have", "has", "will", "can", "but", "not", "been", "would", "about",
}

SKIP_PATTERNS = [
    "/search", "/tag/", "/tags/", "/category/", "/categories/", "/author/",
    "/page/", "/topic/", "/section/", "?s=", "?q=", "?query=", "?search=",
    "#", "javascript:", "mailto:", ".pdf", ".jpg", ".png", ".gif",
]


# ── RSS fetch & parse ─────────────────────────────────────────────────────────
# Same mechanics as the africa-monitor repo — Google News RSS, no API key needed.

def fetch_rss(entity, keyword_string):
    q = f'"{entity}" ({keyword_string}) after:{DATE_FROM}'
    p = urllib.parse.urlencode({
        "q": q, "hl": "en-US", "gl": "US", "ceid": "US:en", "tbs": "qdr:w",
    })
    try:
        r = requests.get(
            f"https://news.google.com/rss/search?{p}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        return ET.fromstring(r.content).findall(".//item")
    except Exception:
        return []


def parse_item(item):
    def txt(tag):
        el = item.find(tag)
        return (el.text or "").strip() if el is not None else ""

    title  = txt("title")
    source = txt("source")
    date   = txt("pubDate")
    link   = txt("link")
    guid   = txt("guid")

    source_el  = item.find("source")
    source_url = source_el.get("url", "").rstrip("/") if source_el is not None else ""

    # Clean Google link — strip line-break artifacts
    raw_link = re.sub(r"\s+", "", link) if link else ""
    if not raw_link.startswith("http"):
        raw_link = re.sub(r"\s+", "", guid) if guid else ""
    if raw_link and not raw_link.startswith("http"):
        raw_link = f"https://news.google.com/rss/articles/{raw_link}"

    if source and title.endswith(" - " + source):
        title = title[:-(len(source) + 3)].strip()
    else:
        title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title).strip()

    try:
        date_fmt = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %Z").strftime("%-d %b %Y")
    except Exception:
        date_fmt = date[:16]

    title_lo  = title.lower()
    demo_tags = [k for k in DEMOGRAPHICS if k in title_lo]

    return {
        "title":       title,
        "source":      source,
        "source_url":  source_url,
        "google_link": raw_link,
        "date":        date_fmt,
        "demo_tags":   demo_tags,
    }


# ── Text extraction ────────────────────────────────────────────────────────────

def is_boilerplate(text):
    if not text or len(text.strip()) < 55:
        return True
    return any(p in text.lower() for p in BOILERPLATE)


def extract_text_from_soup(soup):
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(
        r"ad|banner|cookie|paywall|subscribe|newsletter|popup|modal|"
        r"sidebar|promo|signup|related|share|widget|comment|social|tag|author-bio",
        re.I,
    )):
        tag.decompose()
    for sel in BODY_SELECTORS:
        try:
            container = soup.select_one(sel)
        except Exception:
            continue
        if not container:
            continue
        paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
        clean = [p for p in paras if not is_boilerplate(p)]
        if len(clean) >= 2:
            return clean[:MAX_PARAGRAPHS]
    best_div, best_len = None, 0
    for div in soup.find_all(["div", "section"]):
        paras = [p.get_text(" ", strip=True) for p in div.find_all("p", recursive=False)]
        clean = [p for p in paras if not is_boilerplate(p)]
        total = sum(len(p) for p in clean)
        if total > best_len and len(clean) >= 2:
            best_len, best_div = total, clean
    if best_div:
        return best_div[:MAX_PARAGRAPHS]
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    clean = [p for p in paras if not is_boilerplate(p)]
    return clean[:MAX_PARAGRAPHS] if len(clean) >= 2 else []


def try_google_link(google_url):
    """Follow the Google link. If it escapes google.com, extract text. Otherwise keep the Google link as a clickable fallback."""
    if not google_url:
        return google_url, []
    try:
        r = requests.get(
            google_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
        final = r.url
        if "google.com" not in final and "consent" not in final:
            soup = BeautifulSoup(r.content, "lxml")
            return final, extract_text_from_soup(soup)
    except Exception:
        pass
    return google_url, []


def find_article_url(source_url, title):
    """Publisher site search — tries common search endpoint patterns on the publisher's own domain."""
    if not source_url:
        return ""
    domain      = source_url.rstrip("/")
    domain_bare = re.sub(r"https?://(www\.)?", "", domain).split("/")[0]
    title_clean = re.sub(r"[^\w\s]", " ", title).strip()
    q_encoded   = urllib.parse.quote_plus(title_clean[:120])
    title_words = [
        w.lower() for w in title_clean.split()
        if len(w) > 3 and w.lower() not in STOPWORDS
    ][:8]
    if not title_words:
        return ""
    for search_url in [
        f"{domain}/search?q={q_encoded}",
        f"{domain}/search?query={q_encoded}",
        f"{domain}/search/{q_encoded}",
        f"{domain}/?s={q_encoded}",
        f"{domain}/search?text={q_encoded}",
        f"{domain}/search?term={q_encoded}",
        f"{domain}/search?keywords={q_encoded}",
        f"{domain}/search?p={q_encoded}",
    ]:
        try:
            r = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code != 200:
                continue
            final = r.url
            parsed_path = urllib.parse.urlparse(final).path.strip("/")
            if (domain_bare in final
                    and not any(p in final for p in SKIP_PATTERNS)
                    and parsed_path
                    and len(parsed_path) >= 10):
                if sum(1 for w in title_words if w in final.lower()) >= 2:
                    return final
            soup = BeautifulSoup(r.content, "lxml")
            best_url, best_score = "", 0
            for a in soup.find_all("a", href=True):
                href = a.get("href", "").strip()
                if not href:
                    continue
                if not href.startswith("http"):
                    href = urllib.parse.urljoin(domain + "/", href)
                href = href.split("#")[0]
                if domain_bare not in href:
                    continue
                if any(p in href for p in SKIP_PATTERNS):
                    continue
                pp = urllib.parse.urlparse(href).path.strip("/")
                if not pp or len(pp) < 10:
                    continue
                combined = (a.get_text(strip=True) + " " + href).lower()
                s = sum(1 for w in title_words if w in combined)
                if s > best_score:
                    best_score, best_url = s, href
            if best_score >= 3:
                return best_url
        except Exception:
            continue
    return ""


def try_slug_on_domain(source_url, title):
    if not source_url or not title:
        return ""
    domain = source_url.rstrip("/")
    slug   = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug   = re.sub(r"\s+", "-", slug)
    slug   = re.sub(r"-+", "-", slug)[:120]
    for url in [
        f"{domain}/{slug}/",
        f"{domain}/{slug}",
        f"{domain}/news/{slug}/",
        f"{domain}/news/{slug}",
        f"{domain}/article/{slug}/",
        f"{domain}/articles/{slug}/",
        f"{domain}/stories/{slug}/",
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code == 200 and "404" not in r.url and len(r.content) > 2000:
                if any(w.lower() in r.text.lower() for w in title.split()[:4]):
                    return r.url
        except Exception:
            continue
    return ""


def fetch_article_text(url):
    if not url:
        return [], url
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if any(p in r.url for p in ["/login", "/subscribe", "/signin", "/register"]):
            return [], r.url
        r.raise_for_status()
        return extract_text_from_soup(BeautifulSoup(r.content, "lxml")), r.url
    except Exception:
        return [], url


def resolve_article(parsed):
    """
    Resolution chain, tried in order until one succeeds:
      1. Follow the Google News redirect directly
      2. Search the publisher's own site for the article
      3. Construct a likely URL slug from the title and test it
      4. Retry a plain fetch if we ended up with a real URL but no text yet
    Always returns (url, paragraphs) — url is never empty; worst case it's
    the Google link, which is still clickable in a browser.
    """
    real_url, paragraphs = try_google_link(parsed["google_link"])

    if not paragraphs and "google.com" in real_url:
        found = find_article_url(parsed["source_url"], parsed["title"])
        if found:
            paragraphs, final = fetch_article_text(found)
            real_url = final or found

    if not paragraphs and "google.com" in real_url:
        found = try_slug_on_domain(parsed["source_url"], parsed["title"])
        if found:
            paragraphs, final = fetch_article_text(found)
            real_url = final or found

    if not paragraphs and real_url and "google.com" not in real_url:
        paragraphs, _ = fetch_article_text(real_url)

    return real_url, paragraphs


# ── Process one entity ────────────────────────────────────────────────────────

def process_entity(entity):
    print(f"\n{'─'*50}")
    print(f"  {entity}")
    print(f"{'─'*50}")

    entity_result = {"entity": entity, "categories": {}}
    seen_titles   = set()

    all_categories = dict(CATEGORIES)                        # start with the 7 standard themes

    program_kws = get_program_context(entity)                # empty list for Ghana/Liberia/Burkina Faso
    if program_kws:
        all_categories["Program-Specific Context"] = program_kws   # adds an 8th theme for Malawi/Sierra Leone/Tanzania only

    for cat_name, keyword_list in all_categories.items():
        cat_articles = []

        for kw in keyword_list:
            if len(cat_articles) >= MAX_ARTICLES_PER_CAT:
                break
            items = fetch_rss(entity, kw)
            for rss_position, item in enumerate(items):
                if len(cat_articles) >= MAX_ARTICLES_PER_CAT:
                    break
                parsed = parse_item(item)
                if not parsed["title"] or parsed["title"] in seen_titles:
                    continue
                seen_titles.add(parsed["title"])

                print(f'    [{cat_name}] {parsed["title"]}')
                real_url, paragraphs = resolve_article(parsed)
                is_google = "google.com" in real_url
                status    = f"{len(paragraphs)}p" if paragraphs else ("google-link" if is_google else "no text")
                print(f'         → {real_url}  [{status}]')

                cat_articles.append({
                    "title":      parsed["title"],
                    "url":        real_url,
                    "source":     parsed["source"],
                    "date":       parsed["date"],
                    "paragraphs": paragraphs,
                    "demo_tags":  parsed["demo_tags"],
                    "is_google":    is_google,
                    "rss_position": rss_position,
                })
                time.sleep(DELAY)

        # If a theme genuinely has no matches this week, cat_articles is just
        # an empty list here — it still gets stored under its key so the CSV
        # export can see it was searched, but the HTML report skips it
        # entirely (see render_entity_block in education_export.py). No
        # placeholder text is shown per-theme — it simply doesn't appear.
        entity_result["categories"][cat_name] = cat_articles

    total     = sum(len(v) for v in entity_result["categories"].values())
    with_text = sum(1 for v in entity_result["categories"].values() for a in v if a["paragraphs"])
    print(f'  → {total} articles, {with_text} with text')
    return entity_result


# ── CHECKPOINT & SAVE ─────────────────────────────────────────────────────────
# After each entity completes, its result is appended to the checkpoint file.
# If the run is interrupted, re-running the script resumes from where it left
# off rather than starting over. With only 6 entities this is unlikely to
# matter much, but it's cheap insurance and matches the pattern already
# proven out on the africa-monitor repo.

import pickle

CHECKPOINT_DIR  = ".checkpoints"
CHECKPOINT_PATH = f"{CHECKPOINT_DIR}/checkpoint-{WEEK_SLUG}.pkl"   # in-progress state for this week
RESULTS_PATH    = f"{CHECKPOINT_DIR}/results-{WEEK_SLUG}.pkl"      # this week's finished output, read by education_export.py
os.makedirs(CHECKPOINT_DIR, exist_ok=True)

# If this week's run already completed successfully (RESULTS_PATH already
# exists), there's nothing left to do — a manual re-trigger shouldn't
# silently redo all the work.
if os.path.exists(RESULTS_PATH):
    print(f"{RESULTS_PATH} already exists — this week's search already completed. Nothing to do.")
    exit(0)


def load_checkpoint():
    """Load partially completed results from a previous interrupted run."""
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "rb") as f:
            cp = pickle.load(f)
        print(f"Resuming from checkpoint: {len(cp['results'])} entities already done")
        return cp["results"], set(cp["done_entities"])
    return [], set()


def save_checkpoint(results, done_entities):
    """Write current progress to disk after each entity so a restart can resume from here."""
    with open(CHECKPOINT_PATH, "wb") as f:
        pickle.dump({
            "results":       results,
            "done_entities": list(done_entities),
        }, f)


# ── RUN WITH CHECKPOINT ───────────────────────────────────────────────────────

entities  = TEST_ENTITIES if TEST_MODE else ALL_ENTITIES
generated = TODAY.strftime("%a, %d %b %Y %H:%M UTC")      # human-readable timestamp for display — actual run time

print(f"Generated: {generated}  |  week:{WEEK_SLUG}  |  after:{DATE_FROM}")
print(f"Mode: {'TEST' if TEST_MODE else 'FULL'} — {len(entities)} entities × {len(CATEGORIES)} themes")
print("=" * 60)

results, done_entities = load_checkpoint()

for entity in entities:
    if entity in done_entities:
        print(f"  [checkpoint] skipping {entity} — already done")
        continue
    result = process_entity(entity)
    results.append(result)
    done_entities.add(entity)
    save_checkpoint(results, done_entities)
    print(f"  [checkpoint saved — {len(done_entities)}/{len(entities)} done]")

total_a = sum(len(a) for r in results for a in r["categories"].values())
total_t = sum(1 for r in results for v in r["categories"].values() for a in v if a["paragraphs"])
print(f"\nDone: {len(results)} entities | {total_a} articles | {total_t} with text")

# ── Save final results.pkl for education_export.py ─────────────────────────────
with open(RESULTS_PATH, "wb") as f:
    pickle.dump({
        "results":    results,      # complete list of entity result dicts
        "generated":  generated,    # timestamp string for display — actual run time
        "week_start": WEEK_START,   # datetime object anchored to this week's Monday — used for the masthead date
        "week_slug":  WEEK_SLUG,    # YYYY-MM-DD of this week's Monday
        "total_a":    total_a,      # total article count across all entities
        "total_t":    total_t,      # articles where text was successfully extracted
    }, f)
print(f"Saved {RESULTS_PATH}")

if os.path.exists(CHECKPOINT_PATH):
    os.remove(CHECKPOINT_PATH)   # clean up — checkpoint no longer needed once results.pkl is saved
    print(f"Deleted {CHECKPOINT_PATH} (run complete)")
