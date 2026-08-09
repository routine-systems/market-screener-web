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

## Hosting & automation

Live (login-gated) at **screener.chiragpatnaik.com** — a Cloudflare **Pages** project (`screener`)
behind **Cloudflare Access** (allow-listed emails only). Deploy manually with **`./publish`**
(rebuilds all four pages from current data, no scrape, then `wrangler pages deploy`).

**Auto-refresh — no laptop needed.** `.github/workflows/refresh.yml` runs on a GitHub runner
**Mon–Fri 11:00 UTC (4:30pm IST)** and on-demand: full scrape (weekly + daily + market/sector)
→ `publish` → deploy. A **↻ Refresh** button in the nav (hosted site only) POSTs `/api/refresh`
(a Pages Function, `functions/api/refresh.js`) which dispatches that same workflow. Each screener
pull is spaced by a **random up-to-30s gap** (`scrape.polite_pause`; tune with `--pause`).

Two secrets make it live (create-your-own; not committed):
- **`CLOUDFLARE_API_TOKEN`** (Account · Cloudflare Pages · Edit) as a GitHub Actions secret —
  `gh secret set CLOUDFLARE_API_TOKEN -R NakliTechie/chartink-dashboard` — lets the workflow deploy.
- **`GH_DISPATCH_TOKEN`** (a GitHub fine-grained PAT with Actions: read+write on this repo) as a
  Pages secret — `wrangler pages secret put GH_DISPATCH_TOKEN --project-name screener` — lets the
  ↻ Refresh button trigger the workflow.

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
- Future shortlists must apply the scheduled-event proximity gate in
  [`notes/recommendation_policy.md`](notes/recommendation_policy.md) before presenting entries.

## Bhavcopy research store

`bhavcopy_store.py` maintains the NSE full-bhavcopy research dataset as one validated
Parquet file per trading day under `data/bhavcopy/`. The raw CSV response is parsed in
memory and discarded. Every NSE row and field is retained, including all series, previous
close, OHLC, last price, average price, traded quantity, turnover, trade count,
deliverable quantity, and delivery percentage.

The stock-level research window starts at 2016-01-01. For dates absent from the newer
full-bhavcopy endpoint, the downloader joins NSE's official historical equity bhavcopy
ZIP with the security-wise MTO delivery report. The canonical store still retains one
row per source symbol and series. The atomic manifest makes interrupted calendar runs
resumable.

Retrieve missing or legacy-schema dates from the NSE archive:

```bash
python3 bhavcopy_store.py backfill --start 2016-01-01
python3 bhavcopy_store.py status
```

Install the store dependencies with `pip install pandas pyarrow requests`. Query the
dataset directly with pandas or a Parquet-aware engine:

```python
import pandas as pd

day = pd.read_parquet("data/bhavcopy/IN_cash_20260807.parquet")
cash_equities = day[day["series"].isin(["EQ", "BE"])]
delivery = day.loc[:, ["symbol", "volume", "deliv_qty", "deliv_per"]]
```

The downloader rejects stale holiday responses whose embedded `DATE1` differs from the
requested date. It checks calendar days to retain special weekend trading sessions. Writes
use a temporary Parquet file followed by an atomic replacement.

## Signal backtest research

`backtest_research.py` runs the four research courses against the two-year bhavcopy store:

1. event-study baselines for the six Chartink histories;
2. point-in-time technical and delivery overlays with chronological holdouts;
3. capacity-constrained portfolio simulations with explicit costs;
4. purged walk-forward Ridge and histogram-gradient-boosting rankings.

Run the pipeline and its deterministic tests with:

```bash
python3 backtest_research.py
python3 -m unittest -v test_backtest_research.py test_bhavcopy_store.py
```

The narrative report is written to `reports/backtest_research.md`. Machine-readable tables,
plots, event outcomes, features, fills, equity curves, and model predictions are written under
`reports/` and `data/`. The pipeline reads the local store and does not upload artifacts.

### Maintained strategy suite

`strategy_suite.py` holds the reusable strategy registry. Each `StrategySpec` selects a
Chartink signal, a session exit, and an optional rolling occurrence trigger. The suite applies
the same chronological splits, ₹5-crore turnover floor, four sector-rotation variants,
cost model, ₹10-lakh reference book, and ₹2-lakh whole-share book to every registered spec.

Add another strategy by appending a `StrategySpec` to `STRATEGIES`; the scenario matrix,
portfolio ledgers, report, and registry uniqueness test expand from that entry.

```bash
python3 strategy_suite.py
python3 -m unittest -v test_strategy_suite.py test_confluence_research.py \
  test_backtest_research.py test_bhavcopy_store.py
```

The suite writes `reports/strategy_suite.csv`, `reports/research_decision_table.csv`,
`reports/matched_weekly_horizons.csv`, `reports/capital_sensitivity.csv`,
`reports/strategy_period_robustness.csv`, `reports/strategy_suite.md`, and whole-ledger
Parquet artifacts under `data/backtests/`.
The matched-weekly output holds the entry cohort constant when comparing 20, 50, and 100
sessions, which prevents end-of-dataset maturity from changing the stocks under comparison.

`risk_exit_research.py` tests the weekly persistence lead with fixed initial stops and
absolute next-open gap caps. It uses a ₹1-lakh, five-position, whole-share pilot book,
including a cost-aware 1%-risk sizing mode. It writes its matrix and ledgers to
`reports/weekly_risk_exit_research.csv` and `data/backtests/weekly_risk_exit_*.parquet`.
The maintained pilot selection uses a 50-session time exit, 8% initial stop, ±2% opening
gap cap, Industry-rising filter, and cost-aware 1%-risk sizing.

```bash
python3 risk_exit_research.py
python3 -m unittest -v test_risk_exit_research.py
```

`weekly_pilot.py` applies the selected persistence, Industry rotation, liquidity,
entry-gap, stop, and cost-aware sizing rules to the latest stored weekly observation.
It refreshes bounded official NSE board-meeting and corporate-action records for every
mechanical survivor. A failed event lookup withholds the entry. The five-session pre-event
and two-session post-event blackout covers financial results, board meetings, and ex-dates.
It writes `reports/weekly_pilot_plan.md`, upserts
`data/pilot/recommendation_log.csv`, and creates a trade-log schema without placing orders.

```bash
python3 weekly_pilot.py
python3 weekly_pilot.py --opening-prices /path/to/opening-prices.csv
python3 -m unittest -v test_weekly_pilot.py
```

The optional CSV requires `symbol,opening_price`. Rows remain non-actionable before an
official opening print passes the absolute ±2% gap gate. Official event records persist in
`data/india_events/candidate_events.parquet` with a source and fetch timestamp.

### India accumulation-entry and KuBra research

`india_derived_strategy_research.py` maintains price-and-delivery-derived strategies that
do not depend on Chartink history files. The accumulation family separates multi-week
delivery-volume setup events from EMA20-reclaim and rolling-high breakout entries. The
KuBra family preserves the source latch and tests direction-reset and volume sensitivities.

The event stage is isolated from portfolio evaluation to limit peak memory use:

```bash
python3 india_derived_strategy_research.py --stage events
python3 india_derived_strategy_research.py --stage evaluate
python3 -m unittest -v test_india_derived_strategy_research.py
```

The strategy matrix writes `reports/india_derived_strategy_research.csv`,
`reports/india_derived_strategy_candidates.csv`, and selected whole-share ledgers under
`data/backtests/`. `india_derived_risk_exit_research.py` tests fixed stops for surviving
accumulation rules:

```bash
python3 india_derived_risk_exit_research.py
python3 -m unittest -v test_india_derived_risk_exit_research.py \
  test_risk_exit_research.py
python3 india_derived_artifact_audit.py
```

### US market-data and benchmark stores

`us_market_data.py` builds a local current-listed US stock-and-ETF universe from the
official Nasdaq Trader symbol directories. It downloads Yahoo daily OHLCV into 128
resumable Parquet buckets and audits duplicates, prices, volumes, and OHLC relationships.
Individual securities are capped at 2016-01-01. Historical extensions merge atomically
with populated buckets. Alpha Vantage listing metadata supplies a durable delisted-universe
layer, but backtests must use the dated listing snapshot rather than today's directory.

```bash
python3 us_market_data.py universe
python3 us_market_data.py extend-history --start 2016-01-01 --end-exclusive 2024-08-09
python3 us_market_data.py classify-history-gaps --range 2016-01-01_2024-08-09
python3 us_market_data.py retry-history-gaps --range 2016-01-01_2024-08-09
python3 us_market_data.py repair-ohlc
python3 us_market_data.py retry-missing
python3 us_market_data.py audit
python3 -m unittest -v test_us_market_data.py
```

`market_indices.py` stores benchmark indices separately so their histories can extend to
the maximum range returned by the provider. The initial catalog contains six US and five
Indian benchmarks. Every row records its provider symbol and source URL.

```bash
python3 market_indices.py backfill --markets all
python3 market_indices.py audit
python3 -m unittest -v test_market_indices.py
```

`alpha_vantage_metadata.py` maintains earnings events, dated active and delisted listings,
quarterly shares outstanding, a resumable task queue, and a 25-request UTC-day ledger in
`data/us/alpha_vantage/metadata.sqlite3`. It loads `ALPHA_VANTAGE_API_KEY` from the ignored
`.env` file and never writes the key to the database.

```bash
python3 alpha_vantage_metadata.py seed
python3 alpha_vantage_metadata.py run
python3 alpha_vantage_metadata.py status
python3 -m unittest -v test_alpha_vantage_metadata.py
```

`sec_fundamentals_store.py` reads compact members from official SEC quarterly archives by
HTTP range request. It retains filing dates, filing-time SIC classifications, XBRL common-share
facts, and conservative security-to-CIK links. Raw SEC ZIP archives are not retained. A share
fact enters research only after its filing date and only when that date is not earlier than the
fact date.

`us_delisted_market_data.py` builds a separate Yahoo history store for Alpha Vantage delisted
stocks and ETFs. It excludes symbols reused by an active security and clips every row to the
recorded listing interval. Provider gaps remain explicit in the durable manifest.

`us_point_in_time_research.py` runs the translated daily and weekly formulas across current and
recovered-delisted histories. It compares price, dollar-liquidity, market-cap, ETF, and SEC-sector
cohorts with next-open execution, 0.10% costs per side, SPY-relative returns, chronological
subperiods, and signal-date-clustered confidence intervals.

```bash
python3 sec_fundamentals_store.py refresh
python3 sec_fundamentals_store.py audit
python3 us_delisted_market_data.py backfill
python3 us_delisted_market_data.py audit
python3 us_point_in_time_research.py run
python3 us_point_in_time_research.py audit
pytest -q test_sec_fundamentals_store.py test_us_delisted_market_data.py \
  test_us_point_in_time_research.py
```

The current US research does not promote an actionable signal. Daily cohorts underperform SPY.
Weekly `WKLY_FIL` earns positive absolute returns but negative SPY-relative returns at 50 and
100 sessions. The $300 million stock-cap cohort reduces the 50-session deficit without reversing
it. See `reports/us_point_in_time_research.md`.

See `notes/market_data_stores.md` for schemas, provenance, coverage audits, and restart
procedures. No ingestion command uploads data to R2.

### Scheduled local updates

`market_sync.py` updates India at 21:00 IST with a 23:00 fallback. It updates the
US at 08:00 IST with a 10:00 fallback. Both LaunchAgents run at login, detect
missed sessions, merge bounded updates atomically, and record runs in
`data/ops/sync_state.sqlite3`.

The US run also writes daily and completed-week signal artifacts under
`data/signals/us/`. It applies the translated EMA/cloud-bounce formula, the MACD
filter, liquidity gates, three-of-five persistence, and a seven-day known
earnings blackout. It checks the official SEC derivative store at most once per seven days.

```bash
./ops/install_local_sync.sh
python3 market_sync.py status
```

See `notes/local_market_sync.md` for schedule, recovery, signal, and operations
details. The local update path contains no Cloudflare write.
