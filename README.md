# Weekly Education Landscape Digest — Imagine Worldwide

Scans Google News RSS weekly for education-landscape coverage across
Imagine Worldwide's Scale Portfolio countries (Malawi, Sierra Leone,
Tanzania) and Pilot Sites (Burkina Faso, Ghana, Liberia), and produces a
readable HTML report plus a full CSV data export.

## What to upload, and where

Create a new (or use an existing empty) GitHub repo, then add these files
at the paths shown — the folder structure matters, especially for the
workflow file:

```
your-repo/
├── education_search.py                    ← repo root
├── education_export.py                    ← repo root
└── .github/
    └── workflows/
        └── education-digest.yml           ← MUST be in this exact folder — GitHub only
                                              looks for workflows here
```

`education-digest.yml` is currently named without the `.github/workflows/`
path in front of it (that's just how it was handed to you) — when you
upload it, put it inside a `.github/workflows/` folder, not at the repo
root. On GitHub's web UI: create the repo, click "Add file → Create new
file," type `.github/workflows/education-digest.yml` as the filename (GitHub
will create the folders for you), and paste the contents in.

`education_search.py` and `education_export.py` go directly in the repo
root, same level as the `.github` folder.

You do **not** need to create `.checkpoints/`, the CSV, the HTML report, or
`index.html` yourself — the workflow creates all of those automatically on
its first run and commits them back to the repo.

## Running it for the first time

1. Push the three files above to GitHub in the structure shown.
2. Go to the repo's **Actions** tab. GitHub should show "Weekly Education
   Digest" as an available workflow (if it doesn't appear, double check the
   yml file is exactly at `.github/workflows/education-digest.yml`).
3. Click into the workflow, then **Run workflow** (this is the
   `workflow_dispatch` trigger in the yml — it lets you trigger a run
   manually instead of waiting for Monday).
4. Watch the run — for 6 countries this should take well under an hour.
   When it finishes, check the repo: you should see
   `education-digest-<date>.html`, `index.html`, a CSV, and a
   `.checkpoints/` folder all committed automatically.

## Repository permissions

The workflow's last step pushes commits back to the repo using GitHub's
built-in `GITHUB_TOKEN`. If the push step fails with a permissions error,
go to **Settings → Actions → General → Workflow permissions** in the repo
and set it to "Read and write permissions."

## A note on themes with no results

If a theme (e.g. "Donor & Funding Landscape") turns up nothing for a given
country in a given week, it's simply omitted from that country's section in
the report — there's no "no results" placeholder shown per theme. A whole
country is only skipped entirely if *every* theme comes back empty for it.
A whole section (Scale Portfolio or Pilot Sites) only shows a fallback
message if every country in that section had nothing at all.

## Publishing the report (optional)

If you want `education-digest-<date>.html` viewable as a real webpage
rather than just a file in the repo, enable GitHub Pages: **Settings →
Pages → Deploy from a branch → main → / (root)**. `index.html` will then
serve as the landing/archive page.
