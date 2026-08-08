# chartink-dashboard

Four self-contained HTML dashboards built from Chartink screener **backtest history** —
one download carries the full history (no waiting to accumulate).

## Usage

```bash
./weekly       # Weekly potentials — run Fridays (auto-refreshes Fri ≥ 2pm)
./daily        # Daily potentials  — run 2–3× a day
./market       # Market breadth    — run daily after 2pm
```

Each command opens its page, **downloading fresh only when its data is stale**. Two extra
words work on `./weekly` and `./daily`:

```bash
./daily force      # re-download now, any time
./weekly refresh   # re-extract the expired scanlinks and rebuild — no re-download
```

Use **`refresh`** when you open a page hours later and the in-scan highlight links have gone
dead: Chartink expires the `scanlink`. `refresh` re-fetches it (quick page loads, no full
re-download) and — from either `./weekly` or `./daily` — readies **both** the weekly and
daily scanlinks, since you may open both.

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
A **rotation dot** after each ticker shows whether its sector is rotating **in** (green),
**out** (red) or flat (hollow ring) — from the weekly sector screener; toggle **◉ Rotation**
and choose the granularity (Sector / Industry / Basic). **⧉ Chart links** (off by default) shows
a hover card of quick chart links — **Chartink** (in-scan, with scan highlights) · **TradingView**
· **Yahoo** — so you can open a chart straight from the row (Chartink pages can't be embedded,
so this links out rather than previewing inline).

**Daily potentials** (`daily.html`) — ranks the day's `cp-ich-trend-bounce-dly` tickers
by a **cross-tab score**: in `dly` + also in `cp-pb` + also in `cp-mq`, counted **anywhere
in the selected window** (default 5 days) → 1–3; **all three ranks highest**. DLY/PB/MQ in
the legend are the three source links. Gold dot = `-fil`; **W** badge = also in the weekly
sheet (**◲ In weekly**). Consistency dot-grid (hover for per-day breakdown). Controls:
From/To + ◀▶ offset + presets (1D / 5D / 10D / 21D / All); toggles All-three / PB / MQ /
Filter / New. The same **rotation dot** (**◉ Rotation**) and **⧉ Chart links** hover card
(Chartink · TradingView · Yahoo, off by default) work here too.

**Market breadth** (`market.html`) — the **daily count** of stocks in 9 market-trend
screeners (Total, Nifty, Nifty 500, Futures, Indices, Mid/Small, BankNifty, Stage-2, CMO),
as mini count-charts **coloured by recent trend** (green rising / red falling, with a badge
and day-delta) so a page-scan shows the market turning. A **View** toggle switches all charts
between **Line** (count over the window) and **Bars** (a histogram shaded per day — darker
green if the count rose vs the prior day, darker red if it fell — with a 10-day moving-average
line drawn on top). Rolling **9-month** store; window presets 1M / 3M / 6M / 9M + ◀▶ offset.

**Sector rotation** (`sectors.html`) — reads the **weekly** `cp-cmo-wkly` screener and maps each
stock to a **finer sector classification** from the in-repo **`data.csv`** (NSE **Sector → Industry
→ Basic Industry**; a fresh `~/Downloads/data.csv` is auto-pulled into the folder and trimmed into
`sector_map.csv`). For each week it counts how many of a group's stocks are in the screener — a
**rising count = the sector is gaining interest**, and weekly data smooths out intermittent blips.
Two **Layouts**:

- **Grid** — cards **sorted by recent momentum** (rising first), each a Line/Bars+MA mini-chart,
  with **Weekly ↗ / Daily ↗** buttons that jump to that sheet **filtered to the sector**.
- **Quadrant** — a rotation graph of sector **movement**: **x** = current participation (avg stocks
  in the screener), **y** = momentum (stocks added per week), centred on the median participation
  and zero momentum → **Leading** (large + adding), **Improving** (small + adding), **Weakening**
  (large + shedding), **Lagging** (small + shedding); bubble size = latest count. A **Within**
  dropdown focuses the plot on one sector's **sub-groups** (at Industry / Basic level).

Shared controls: **Level** (Sector / Industry / Basic), **Weeks** window (5 / 8 / 13 / 26 / 52 /
All, default 13) + ◀▶ offset. Groups with a single stock in the window are hidden as noise. Built
by the **market** command (no separate script); open it from the top nav.

## Freshness (when a plain run re-downloads)

- **`weekly`** — when a new week has closed (data older than the most recent **Friday
  16:00**) or during **Friday closing hours (≥ 2pm)**.
- **`daily`** — when the store is older than **90 min**.
- **`market`** — when not pulled since the most recent **2pm**.
- **`force`** always re-downloads; **`refresh`** only re-fetches the scanlink (no download).

## How it works

Each screener's **BACKTEST HISTORY → Download → CSV** is scraped headlessly; the Python
parses it (grouped by date) and bakes the data into the HTML at build time. The per-screener
`scanlink` (which Chartink rotates) is re-extracted each run for the in-scan links. Daily /
market pages keep only what they need (counts / membership) and discard the raw CSVs, so
`data/` stays small.

## Files

| File | Role |
|---|---|
| `weekly` · `daily` · `market` | The three everyday commands (refresh-if-stale, then open) |
| `scrape.py` | Headless-Chrome: extract `scanlink`, download a backtest CSV |
| `run.py` | Weekly entry (`--mode weekly` / `adhoc`) used by `dash.sh` |
| `build_dashboard.py` / `template.html` | Build + UI for the weekly page |
| `daily.py` / `daily_template.html` | Build + UI for the daily cross-tab page |
| `market.py` / `market_template.html` | Build + UI for the market-breadth page (also builds sectors) |
| `sectors_template.html` | UI for the sector-rotation page (built by `market.py`) |
| `sectors_lib.py` | Shared sector map + rotation-status + quadrant helpers (used by all builds) |
| `data.csv` | Durable in-repo classification export (NSE Sector/Industry/Basic-Industry + snapshot cols) |
| `sector_map.csv` | Trimmed Symbol → Sector/Industry/Basic-Industry map (derived from `data.csv`) |
| `data/*.json` | Derived caches (weekly/daily history, market + sector counts) — git-ignored |

## Requirements

Python 3.12, Chrome, and `pip install selenium webdriver-manager` (already present here).

## Notes

- Backtest CSVs carry membership + sector + market cap, but **no price** (close/%chg/volume).
- Data is unofficial, scraped from Chartink's public screener pages for personal use.
