# Education News Roundup

Automated weekly news digest covering the education landscape across Scale Portfolio and Pilot Site countries. Runs every Monday; can also be triggered manually.

**Live site:** not yet published — see "Publishing the report" below to enable GitHub Pages once you're ready.

---

## What it does

Each Monday at 01:00 UTC the pipeline runs automatically:

1. Searches Google News RSS for 6 countries — 3 Scale Portfolio, 3 Pilot Sites
2. For each country, runs searches across **5 general themes**, plus 2 additional tracking themes:
   - Policy, Budget & Funding (government policy/spending and external donor/funder activity together)
   - Learning Outcomes & Assessment (includes foundational literacy/numeracy specifically)
   - Technology & Innovation in Education (includes AI in education specifically)
   - Teachers, Schools & Continuity (staffing/infrastructure and disruption — closures, conflict, climate events)
   - Education & the Workforce
   - IW Mentions (all 6 countries)
   - Government & Program Context — BEFIT / Pikin Tab / MsingiTek and named ministries, for Malawi, Sierra Leone, Tanzania, and Burkina Faso only
3. Attempts to extract verbatim article text directly from publisher pages
4. Highlights articles mentioning **youth, women, people with disabilities, refugees, or IW by name**
5. Publishes a production report split into Scale Portfolio and Pilot Sites sections
6. Saves a full CSV export of all articles collected

---

## Output files

Each weekly run produces three new files committed to this repo:

| File | Description |
|------|-------------|
| `education-digest-YYYY-MM-DD.html` | Production report — filtered, designed, ready to publish to GitHub Pages |
| `education-digest-YYYY-MM-DD.csv` | Full data export — all 6 countries, all themes, all articles |
| `index.html` | Archive page — lists all past issues with links (updated each run) |

Files are named by the calendar week (the Monday that week started), not by the exact moment the job ran, so a retry later in the week updates the same week's files rather than creating duplicates. See "How the search window works" below.

---

## Countries covered

### Scale Portfolio (national government-scale programs)
Malawi (BEFIT) · Sierra Leone (Pikin Tab) · Tanzania (MsingiTek)

### Pilot Sites
Burkina Faso · Ghana · Liberia

Burkina Faso is Francophone, so its searches also run a French-language equivalent of each general theme (e.g. "budget de l'éducation" alongside "education budget") — otherwise French-language press coverage of Burkina Faso would be almost entirely invisible to the digest.

---

## Repository structure

```
your-repo/
├── education_search.py            Main search script — fetches RSS, extracts text, saves results.pkl
├── education_export.py            Export script — reads results.pkl, writes HTML and CSV outputs
├── .github/
│   └── workflows/
│       └── education-digest.yml   GitHub Actions workflow — runs the pipeline every Monday
├── .checkpoints/                  Per-week progress files (auto-created, see below)
├── index.html                     Archive page (auto-generated, updated each run)
├── education-digest-YYYY-MM-DD.html  Weekly production reports (one per week, never overwritten)
└── education-digest-YYYY-MM-DD.csv   Full data exports (one per week, never overwritten)
```

None of the auto-generated files or folders need to exist before the first run — the workflow creates all of them.

---

## How the search works

### Google News RSS
The pipeline queries Google News RSS with the format:
```
"Country Name" (keyword1 OR keyword2) after:YYYY-MM-DD
```
RSS is fetched directly — no API key, no cost, no third-party dependency.

### How the search window works
The search window is anchored to the current calendar week's Monday, not to the exact moment the script runs — so a manual re-run midweek searches the same window as Monday's scheduled run did, rather than shifting forward and re-covering some days twice. Progress is also checkpointed per entity in `.checkpoints/`, so an interrupted run resumes rather than starting over, and a week that already completed won't be silently redone by a later trigger.

### URL resolution (three methods in sequence)
Because Google News links are redirects that hit a consent wall in some regions, the pipeline tries three methods to get the real article URL:

1. **Follow Google redirect** — works for publishers that redirect cleanly without a consent gate
2. **Publisher site search** — searches the publisher's own site using common search endpoint patterns
3. **URL slug construction** — constructs likely article URLs from the title and tests them

If none succeed, the Google News link is kept as a clickable fallback.

### Text extraction
Once a real article URL is found, the page is fetched and parsed. Noise (ads, navbars, footers, paywalls, subscription prompts) is removed. Article body selectors are tried from most specific (`[itemprop='articleBody']`, `article`) to least specific (`main`, `#content`). Text is reproduced verbatim — no summarisation, no paraphrasing.

### Demographic and org tagging
Articles are tagged automatically if their title contains: `youth`, `women`, `disabilit` (catches disability/disabilities), or `refugee`. A separate check flags articles whose title or extracted text mentions IW by name. Tags are shown as coloured badges in the HTML output and recorded in the CSV.

### Themes with no results
If a theme turns up nothing for a country in a given week, it's simply omitted from that country's section — there's no "no results" placeholder shown per theme. A country is only skipped entirely if every theme came back empty for it. A whole section (Scale Portfolio or Pilot Sites) only shows a fallback message if every country in it had nothing at all.

### Manual review — editing the generated HTML by hand
The raw output is expected to need a quick human pass most weeks (mismatched or irrelevant articles happen — see "Coverage may be thin" below). To make that easy, every article in `education-digest-<date>.html` is wrapped in comment markers:
```html
<!-- ══════ ARTICLE: <headline> — delete this whole block down to "END ARTICLE" to remove it ══════ -->
<article class="card">
  ...
</article>
<!-- ══════ END ARTICLE ══════ -->
```
To remove an article, delete everything from the `ARTICLE:` line down through the matching `END ARTICLE` line. Where no excerpt could be extracted, there's a second marker right at that spot showing exactly where to paste one in:
```html
<!-- NO EXCERPT — to add one, replace the <p class="read-link"> line below with:
     <div class="excerpt"><p>First paragraph…</p><p>Second paragraph… (optional)</p></div> -->
<p class="read-link"><a href="...">Read article</a></p>
```
**Important**: editing the generated HTML file directly only affects that one week's file — the *next* scheduled run regenerates and overwrites it from scratch. Manual edits don't persist automatically; if a change should apply every week going forward (wording, title, styling), that belongs in `education_export.py` instead.

---

## CSV columns

| Column | Description |
|--------|-------------|
| `entity` | Country name |
| `pillar` | Theme the article was found under |
| `title` | Article headline |
| `url` | Direct article URL or Google News link |
| `source` | Publisher name |
| `date` | Publication date |
| `demographics` | Comma-separated demographic labels found in title |
| `iw_mention` | `yes` if IW is mentioned in the title or extracted text |
| `text_paragraph_1` | First verbatim paragraph extracted from article |
| `text_paragraph_2` | Second verbatim paragraph |
| `text_paragraph_3` | Third verbatim paragraph |
| `has_text` | `yes` if text was extracted, `no` if only link available |
| `is_google_link` | `yes` if URL is still a Google News redirect |
| `rss_position` | Article's position in the Google News RSS feed (0 = top) |
| `reach_score` | Computed popularity score used to pick which articles appear in the report |

---

## Setup — uploading to GitHub

Create a new (or use an existing empty) GitHub repo, then add the files at
the paths shown in "Repository structure" above. The workflow file's
location matters — it must be inside `.github/workflows/`, not at the repo
root. On GitHub's web UI: create the repo, click **Add file → Create new
file**, type `.github/workflows/education-digest.yml` as the filename
(GitHub creates the folders for you), and paste the contents in.
`education_search.py` and `education_export.py` go directly in the repo
root.

### Repository permissions
The workflow's last step pushes commits back to the repo using GitHub's
built-in `GITHUB_TOKEN`. If the push step fails with a permissions error,
go to **Settings → Actions → General → Workflow permissions** and set it to
"Read and write permissions."

---

## Running manually

### Trigger via GitHub Actions (no local setup needed)
1. Go to the repo on GitHub
2. Click the **Actions** tab
3. Click **Weekly Education Digest** in the left sidebar
4. Click **Run workflow** → **Run workflow**
5. For 6 countries, the run should take well under an hour
6. When complete, new files appear in the repo

### Run locally
```bash
# Clone the repo
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# Install dependencies (one time)
pip install requests beautifulsoup4 lxml

# Run the search
python education_search.py

# Generate HTML and CSV outputs
python education_export.py
```

For a quick test on 2 countries only, open `education_search.py` and change:
```python
TEST_MODE = False
```
to:
```python
TEST_MODE = True
```
then run — this covers Malawi and Ghana only, one Scale country and one Pilot country.

---

## Publishing the report (optional)

To make `education-digest-<date>.html` viewable as a real webpage instead
of just a file in the repo, enable GitHub Pages: **Settings → Pages →
Deploy from a branch → main → / (root)**. `index.html` will then serve as
the landing/archive page, and you can update the "Live site" link at the
top of this README.

---

## Notes

- Article text is reproduced verbatim from source pages. Where text is not accessible (paywalled or blocked), only the title and link are shown.
- The production report shows a maximum of 3 articles per country, pooled across all themes and prioritised by estimated popularity (publisher reach, RSS position, and whether text was extracted).
- This digest is produced automatically. It has not been editorially reviewed. Kindly click each article title to read the full piece on the original publisher's site.
- Google News RSS is free and requires no authentication. The pipeline has no paid dependencies.
- Coverage may be thin some weeks — Malawi, Sierra Leone, Tanzania, Ghana, Liberia, and Burkina Faso get less English-language international press than larger media markets, so an empty theme or country in a given week reflects available coverage, not a pipeline error.
