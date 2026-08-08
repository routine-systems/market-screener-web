#!/usr/bin/env python3
"""
Build the dashboard from a Chartink screener BACKTEST CSV.

The backtest CSV (Date, Symbol, Marketcapname, Sector) already contains the full
weekly membership history, so there is no forward accumulation — each build parses
the CSV, groups rows by weekly Date, and renders a self-contained dashboard that
ranks tickers by how many weeks (of a selected window) they appeared in.

    python3 build_dashboard.py --backtest data/<slug>_backtest_latest.csv \
        --url https://chartink.com/screener/<slug>

State (data/history.json) is a derived cache: {screener, source_url, scanlink,
timeframe, weeks:[{week, tickers:[{symbol, sector, marketcap}]}]}.
"""

import argparse
import base64
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import sectors_lib

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
HISTORY = DATA_DIR / "history.json"
TEMPLATE = HERE / "template.html"
OUT = HERE / "dashboard.html"
DEFAULT_URL = "https://chartink.com/screener/cp-ich-trend-bounce-wkly"


def _iso(d: str) -> str:
    """DD-MM-YYYY (Chartink) -> YYYY-MM-DD; pass through if already ISO."""
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return d.strip()


def parse_backtest(csv_path: Path):
    """Group backtest rows into weeks: [{week, tickers:[{symbol,sector,marketcap}]}]."""
    text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines())
    fields = {(f or "").lower().strip(): f for f in (reader.fieldnames or [])}

    def col(*names):
        for n in names:
            if n in fields:
                return fields[n]
        return None

    c_date = col("date")
    c_sym = col("symbol")
    c_mc = col("marketcapname", "marketcap", "market cap")
    c_sec = col("sector")
    if not c_date or not c_sym:
        raise RuntimeError(f"Backtest CSV missing Date/Symbol columns: {reader.fieldnames}")

    byweek = defaultdict(list)
    for r in reader:
        sym = (r.get(c_sym) or "").strip()
        if not sym:
            continue
        byweek[_iso(r.get(c_date) or "")].append({
            "symbol": sym,
            "sector": (r.get(c_sec) or "").strip() if c_sec else "",
            "marketcap": (r.get(c_mc) or "").strip() if c_mc else "",
        })
    weeks = [{"week": wk, "tickers": byweek[wk]} for wk in sorted(byweek) if wk]
    return weeks


def build_history(csv_path: Path, url: str, scanlink=None, timeframe=None):
    weeks = parse_backtest(csv_path)
    if not weeks:
        raise RuntimeError(f"No weekly rows parsed from {csv_path}")
    slug = url.rstrip("/").split("/")[-1]
    return {
        "screener": slug,
        "source_url": url,
        "scanlink": scanlink,
        "timeframe": timeframe or "weekly",
        "weeks": weeks,
    }


def parse_membership(csv_path: Path):
    """Backtest CSV of a subset screener -> { week: [symbols] } per week."""
    weeks = parse_backtest(csv_path)
    return {w["week"]: sorted({t["symbol"] for t in w["tickers"]}) for w in weeks}


def attach_filter(h, filter_csv: Path, furl: str):
    """Attach a filtered-subset screener's weekly membership for highlight dots."""
    mem = parse_membership(filter_csv)
    fslug = furl.rstrip("/").split("/")[-1]
    h["filter"] = {"screener": fslug, "url": furl, "weeks": mem}
    if mem:
        last = max(mem)
        print(f"◆ filter '{fslug}': {len(mem)} weeks, latest {last} → {len(mem[last])} symbols")
    else:
        print(f"◆ filter '{fslug}': 0 weeks parsed")
    return h


def save_history(h):
    HISTORY.write_text(json.dumps(h))


def render(h, window: int):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Template missing: {TEMPLATE}")
    payload = dict(h)
    payload["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    payload["window"] = window
    b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    html = TEMPLATE.read_text().replace("__HISTORY_B64__", b64).replace("__WINDOW__", str(window))
    OUT.write_text(html)
    weeks = h["weeks"]
    print(f"🖼  Rendered {OUT.name} · {len(weeks)} weeks "
          f"({weeks[0]['week']} → {weeks[-1]['week']}) · default window {window}")
    return OUT


def resolve_meta(backtest: Path, scanlink, timeframe):
    """Fill scanlink/timeframe from the scrape sidecar when not passed explicitly."""
    if scanlink and timeframe:
        return scanlink, timeframe
    slug = backtest.name.split("_backtest")[0]
    sidecar = backtest.parent / f"{slug}_latest.meta.json"
    if sidecar.exists():
        m = json.loads(sidecar.read_text())
        scanlink = scanlink or m.get("scanlink")
        timeframe = timeframe or m.get("timeframe")
    return scanlink, timeframe


def rebuild(url, window, backtest=None, scanlink=None, timeframe=None,
            filter_csv=None, filter_url=None) -> int:
    """Build + render the weekly page from the LOCAL backtest CSV (no download).
    Also attaches the -fil overlay and the daily cross-membership when present."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    slug = url.rstrip("/").split("/")[-1]
    if not backtest:
        cand = DATA_DIR / f"{slug}_backtest_latest.csv"
        pool = [p for p in DATA_DIR.glob("*_backtest_latest.csv") if "-fil" not in p.name]
        backtest = cand if cand.exists() else (sorted(pool)[-1] if pool else None)
    if not backtest or not backtest.exists():
        print("❌ No primary backtest CSV in data/ — run a scrape first.", file=sys.stderr)
        return 1

    scanlink, timeframe = resolve_meta(backtest, scanlink, timeframe)
    h = build_history(backtest, url, scanlink, timeframe)

    fcsv = filter_csv
    if not fcsv:
        cand = DATA_DIR / f"{slug}-fil_backtest_latest.csv"
        fcsv = cand if cand.exists() else None
    if fcsv and fcsv.exists():
        attach_filter(h, fcsv, filter_url or (url + "-fil"))

    dly = DATA_DIR / "history_daily.json"
    if dly.exists():
        d = json.loads(dly.read_text())
        h["cross"] = {"label": "D", "name": "daily", "url": d.get("source_url"),
                      "weeks": {x["week"]: sorted({t["symbol"] for t in x["tickers"]})
                                for x in d.get("weeks", [])}}

    syms = {t["symbol"] for wk in h["weeks"] for t in wk["tickers"]}
    rot = sectors_lib.rotation_for(syms)
    if rot:
        h["rotation"] = rot
        print(f"◉ rotation: {len(rot['of'])}/{len(syms)} tickers mapped to sectors "
              f"(window {rot['window']} wk)")

    save_history(h)
    print(f"🔑 scanlink={h['scanlink']} timeframe={h['timeframe']}")
    render(h, window)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Render dashboard from a backtest CSV")
    ap.add_argument("--backtest", type=Path, help="Backtest CSV (default: newest in data/)")
    ap.add_argument("--url", default=DEFAULT_URL, help="Source screener URL")
    ap.add_argument("--window", type=int, default=5, help="Default rolling window (weeks)")
    ap.add_argument("--scanlink", help="In-scan link hash (else read from sidecar)")
    ap.add_argument("--timeframe", help="Screener timeframe (e.g. weekly)")
    ap.add_argument("--filter", dest="filter_csv", type=Path, help="Filtered-subset backtest CSV (highlight dots)")
    ap.add_argument("--filter-url", help="Filtered-subset screener URL (default: <url>-fil)")
    args = ap.parse_args()
    return rebuild(args.url, args.window, args.backtest, args.scanlink,
                   args.timeframe, args.filter_csv, args.filter_url)


if __name__ == "__main__":
    sys.exit(main())
