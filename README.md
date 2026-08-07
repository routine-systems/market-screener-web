# chartink-dashboard

Weekly tracker for a Chartink screener. It downloads the screener's **backtest
history** (≈3 years of weekly scan membership in one CSV) and builds a single-file
HTML dashboard that **ranks tickers by how many weeks — of a selectable window —
they appeared in**. Because the backtest CSV already contains every week, the whole
history is available from a single download; no waiting to accumulate.

Built for `cp-ich-trend-bounce-wkly` but works with any screener URL.

## What it does (the requirements)

1. **Download every Friday** — `run_weekly.sh` scrapes the screener; a launchd job
   fires it weekly (re-download picks up the newest weekly date).
2. **Full weekly history from one file** — the scraper takes the **BACKTEST HISTORY →
   Download → CSV** export (`Date, Symbol, Marketcapname, Sector`), grouped into weeks.
3. **Rank by appearance over a window** — `dashboard.html` ranks every ticker by how
   many of the selected weeks it appeared in (5/5, 4/5, …), with a per-week presence
   grid, plus "new this week" / "dropped", per-week counts, and appearance-frequency.
   A **week-range selector** (From/To + Last 5 / 8 / 13 / 26 / 52 / All presets,
   default the latest 5) re-ranks live over any range.
4. **In-scan ticker links** — each ticker links into its Chartink `stocks-new` chart
   *in the scan's context* (the chart highlights the weeks it matched). This uses the
   per-screener `scanlink` hash, which Chartink **rotates**, so every run re-extracts
   it. (`nav_token` is not required.)

## Everyday use — one command

```bash
./dash.sh          # opens the dashboard; downloads fresh only if a new week has closed
./dash.sh force    # force a fresh pull now (mid-week check), then open
```

`dash.sh` re-downloads only when your data predates the most recent **Friday 16:00**
cutoff; otherwise it just opens `dashboard.html`.

## Two modes (`run.py`)

Both scrape the backtest CSV and rebuild; they differ only in intent/scheduling
(the single download already carries all weeks — there is no forward accumulation):

| Mode | Use |
|---|---|
| `--mode weekly` | The Friday / launchd job. |
| `--mode adhoc`  | A manual refresh you run anytime. |

```bash
python3 run.py --mode weekly           # Friday capture
python3 run.py --mode adhoc            # refresh now
python3 run.py --mode weekly --show    # watch the browser
```

## Files

| File | Role |
|---|---|
| `scrape.py` | Headless-Chrome: extract `scanlink`, download the **backtest** CSV → `data/<slug>_backtest_latest.csv` + `<slug>_latest.meta.json` |
| `build_dashboard.py` | Parse the backtest CSV into weeks, render `dashboard.html` |
| `template.html` | The dashboard UI; history baked in at build time (double-click to open) |
| `run.py` | Single entry: `--mode weekly` / `--mode adhoc` |
| `run_weekly.sh` | Drives `run.py`, logs to `logs/` |
| `com.chirag.chartink-weekly.plist` | launchd schedule (Fridays 18:30) |
| `data/history.json` | Derived cache of the parsed backtest history |

## Requirements

- Python 3.12, Chrome, and `pip install selenium webdriver-manager` (already present here).

## Manual run (step by step)

```bash
python3 scrape.py --url https://chartink.com/screener/cp-ich-trend-bounce-wkly
python3 build_dashboard.py --backtest data/cp-ich-trend-bounce-wkly_backtest_latest.csv \
    --url https://chartink.com/screener/cp-ich-trend-bounce-wkly --window 5
open dashboard.html
```

Drop any Chartink **Backtest** CSV onto the open dashboard to load it (in-memory).

## Schedule it (every Friday)

```bash
cp com.chirag.chartink-weekly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.chirag.chartink-weekly.plist
launchctl list | grep chartink-weekly
```

Stop with `launchctl unload …`. The job runs in your logged-in session (headless
Chrome needs no visible window); if the Mac is asleep at 18:30 Friday, launchd runs
it once shortly after the next wake.

## Notes

- The backtest CSV has membership + sector + market cap, but **no price** (close/%chg/
  volume). The ranking table shows Symbol · appearances · Sector · Cap · all-time count.
- Data is unofficial, scraped from Chartink's public screener page for personal use.
