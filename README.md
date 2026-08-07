# chartink-dashboard

Weekly tracker for a Chartink screener. Every Friday it downloads the screener's
CSV, appends that week's tickers to a rolling history, and rebuilds a single-file
HTML dashboard that **ranks tickers by how many of the last 5 weeks they appeared in**.

Built for `cp-ich-trend-bounce-wkly` but works with any screener URL.

## What it does (the requirements)

1. **Download every Friday** — `run_weekly.sh` scrapes the screener; a launchd job
   fires it weekly.
2. **Add this week's data** — each run ingests the snapshot into `data/history.json`,
   keyed to the week's Friday (idempotent: re-running in the same week replaces it).
3. **Rank by appearance in a 5-week window** — `dashboard.html` shows every ticker
   ranked by appearance count (5/5, 4/5, …) with a per-week presence grid, plus
   "new this week" / "dropped", weekly counts, and latest price/volume.

## Files

| File | Role |
|---|---|
| `scrape.py` | Headless-Chrome scraper → `data/<slug>_latest.csv` (+ timestamped snapshot) |
| `build_dashboard.py` | Ingest a snapshot into `data/history.json`, render `dashboard.html` |
| `template.html` | The dashboard UI; data is baked in at build time (double-click to open) |
| `run_weekly.sh` | scrape → ingest → build, with logging to `logs/` |
| `com.chirag.chartink-weekly.plist` | launchd schedule (Fridays 18:30) |
| `data/history.json` | Accumulated weekly history (the source of truth) |

## Requirements

- Python 3.12, Chrome, and: `pip install selenium webdriver-manager`
- (already present on this machine)

## Manual run

```bash
./run_weekly.sh
# or step by step:
python3 scrape.py --url https://chartink.com/screener/cp-ich-trend-bounce-wkly
python3 build_dashboard.py --ingest data/cp-ich-trend-bounce-wkly_latest.csv \
    --url https://chartink.com/screener/cp-ich-trend-bounce-wkly --window 5
open dashboard.html
```

`scrape.py --show` runs a visible browser. Drop any Chartink CSV onto the open
dashboard to preview it as "this week" (in-memory only; not saved to history).

## Schedule it (every Friday)

```bash
cp com.chirag.chartink-weekly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.chirag.chartink-weekly.plist
# verify:
launchctl list | grep chartink-weekly
```

To stop: `launchctl unload ~/Library/LaunchAgents/com.chirag.chartink-weekly.plist`.
The job runs in your logged-in session (headless Chrome needs no visible window). If
the Mac is asleep at 18:30 Friday, launchd runs it once shortly after the next wake.

## Notes

- History grows one entry per week; the dashboard windows to the last 5 for ranking
  but keeps all weeks in `history.json`.
- With fewer than 5 weeks it ranks over what exists (e.g. 2/2) and says so.
- Data is unofficial, scraped from Chartink's public screener page for personal use.
