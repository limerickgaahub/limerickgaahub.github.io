# Data updater

This folder contains:
- `scripts/scrape_fixtures.py` — a simple scraper stub for limerickgaa.ie
- `.github/workflows/update-fixtures.yml` — GitHub Action to run the scraper and commit updates

## How it works
1. The site loads `data/hurling_2025.json` at runtime.
2. The Action runs on a schedule and updates that JSON if new fixtures are detected.
3. The "Refresh" button on the site re-fetches the JSON with cache-busting and re-renders.

## Configure
- Open `scripts/scrape_fixtures.py` and add the exact fixture/result page URLs to `URLS`.
- Improve `extract_entries` with page-specific selectors (use BeautifulSoup) for higher accuracy.
- Commit to `main` and the workflow will keep the data current.

