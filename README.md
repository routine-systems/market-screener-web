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
3. **Rank by appearance over a window** — `dashboard.html` ranks every ticker by how
   many of the selected weeks it appeared in (5/5, 4/5, …) with a per-week presence
   grid, plus "new this week" / "dropped", weekly counts, and latest price/volume.
   A **week-range selector** (From/To + Last 5 / Last 8 / All presets, default the
   latest 5) re-ranks live over any range.
4. **In-scan ticker links** — each ticker links into its Chartink `stocks-new` chart
   *in the scan's context* (the chart highlights the weeks it matched). This needs the
   per-screener `scanlink` hash, which Chartink **rotates**, so every run re-extracts
   it from the screener page and bakes it into the dashboard. (`nav_token` is not
   required — Chartink's own row links omit it.)

## Two modes (`run.py`)

| Mode | What it does |
|---|---|
| `--mode weekly` | scrape → refresh scanlink → **add/replace this week** → rebuild. The Friday job. |
| `--mode adhoc`  | scrape → refresh scanlink → rebuild from existing history, **no new week**. Run anytime. |

```bash
python3 run.py --mode weekly          # Friday capture
python3 run.py --mode adhoc           # refresh links / rebuild now
python3 run.py --mode weekly --show   # watch the browser
```

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
