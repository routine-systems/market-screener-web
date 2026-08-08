# chartink-dashboard

Three self-contained HTML dashboards built from Chartink screener **backtest history** —
one download carries the full history (no waiting to accumulate).

## Usage

```bash
./dash.sh      # Weekly potentials — run Fridays (auto-refreshes Fri ≥ 2pm)
./daily.sh     # Daily potentials  — run 2–3× a day
./market.sh    # Market breadth    — run daily after 2pm
```

Each command opens its page, **downloading fresh only when its data is stale**. Add
`force` to re-pull immediately, any time:

```bash
./daily.sh force
```

The three pages cross-link via a top menu (**Weekly · Daily · Market**). `dash.sh` and
`daily.sh` also cheaply re-render each other so the weekly↔daily cross-tags stay fresh.

---

## What each page shows

**Weekly potentials** (`dashboard.html`) — ranks tickers by how many of a selectable
**week window** they appeared in (5/5, 4/5 …), with a per-week presence grid (hover for
the breakdown), "new / dropped", and per-week + frequency charts. Controls: From/To +
◀▶ offset + presets (Last 5 / 8 / 13 / 26 / 52 / All, default 5). A gold dot marks names
also in the stricter `-fil` subset (**◆ In filter** toggle); a **D** badge marks names
also in the daily sheet (**◲ In daily**). Ticker links open the in-scan Chartink chart.

**Daily potentials** (`daily.html`) — ranks the day's `cp-ich-trend-bounce-dly` tickers
by a **cross-tab score**: in `dly` + also in `cp-pb` + also in `cp-mq`, counted **anywhere
in the selected window** (default 5 days) → 1–3; **all three ranks highest**. DLY/PB/MQ in
the legend are the three source links. Gold dot = `-fil`; **W** badge = also in the weekly
sheet (**◲ In weekly**). Consistency dot-grid (hover for per-day breakdown). Controls:
From/To + ◀▶ offset + presets (1D / 5D / 10D / 21D / All); toggles All-three / PB / MQ /
Filter / New.

**Market breadth** (`market.html`) — the **daily count** of stocks in 8 market-trend
screeners (Total, Nifty, Nifty 500, Futures, Indices, Mid/Small, BankNifty, Stage-2), as
mini count-charts **coloured by recent trend** (green rising / red falling, with a badge
and day-delta) so a page-scan shows the market turning. Rolling **9-month** store; window
presets 1M / 3M / 6M / 9M + ◀▶ offset.

## Freshness (when a plain run re-downloads)

- **`dash.sh`** — when a new week has closed (data older than the most recent **Friday
  16:00**) or during **Friday closing hours (≥ 2pm)**.
- **`daily.sh`** — when the store is older than **90 min**.
- **`market.sh`** — when not pulled since the most recent **2pm**.
- **`force`** on any of them always re-downloads.

## How it works

Each screener's **BACKTEST HISTORY → Download → CSV** is scraped headlessly; the Python
parses it (grouped by date) and bakes the data into the HTML at build time. The per-screener
`scanlink` (which Chartink rotates) is re-extracted each run for the in-scan links. Daily /
market pages keep only what they need (counts / membership) and discard the raw CSVs, so
`data/` stays small.

## Files

| File | Role |
|---|---|
| `dash.sh` · `daily.sh` · `market.sh` | The three everyday commands (refresh-if-stale, then open) |
| `scrape.py` | Headless-Chrome: extract `scanlink`, download a backtest CSV |
| `run.py` | Weekly entry (`--mode weekly` / `adhoc`) used by `dash.sh` |
| `build_dashboard.py` / `template.html` | Build + UI for the weekly page |
| `daily.py` / `daily_template.html` | Build + UI for the daily cross-tab page |
| `market.py` / `market_template.html` | Build + UI for the market-breadth page |
| `data/*.json` | Derived caches (weekly/daily history, market counts) — git-ignored |

## Requirements

Python 3.12, Chrome, and `pip install selenium webdriver-manager` (already present here).

## Notes

- Backtest CSVs carry membership + sector + market cap, but **no price** (close/%chg/volume).
- Data is unofficial, scraped from Chartink's public screener pages for personal use.
