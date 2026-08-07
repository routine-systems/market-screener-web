#!/usr/bin/env python3
"""
Ingest a weekly Chartink screener snapshot into a rolling history, then render a
self-contained HTML dashboard that ranks tickers by how many of the last N weeks
they appeared in.

Typical weekly use (via run_weekly.sh):
    python3 build_dashboard.py --ingest data/<slug>_latest.csv \
        --url https://chartink.com/screener/<slug>

Re-render only (no new week):
    python3 build_dashboard.py

State lives in data/history.json:  {screener, source_url, weeks:[{week, scraped_at,
tickers:[{symbol,name,close,change,volume}]}]}. "week" is the Friday (ISO date) of
the scrape's calendar week; re-running in the same week replaces that week's entry.
"""

import argparse
import base64
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
HISTORY = DATA_DIR / "history.json"
TEMPLATE = HERE / "template.html"
OUT = HERE / "dashboard.html"
DEFAULT_URL = "https://chartink.com/screener/cp-ich-trend-bounce-wkly"


def clean_num(s):
    try:
        return float(str(s).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return 0.0


def clean_int(s):
    return int(round(clean_num(s)))


def read_records(csv_path: Path):
    """Parse a Chartink screener CSV into normalized ticker records."""
    text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        return []
    head = [h.lower().strip() for h in rows[0]]

    def col(*names):
        for n in names:
            if n in head:
                return head.index(n)
        return -1

    i_sr = col("sr.", "sr", "#")
    i_name = col("stock name", "name")
    i_sym = col("symbol")
    i_close = col("close", "price")
    i_chg = col("%_change", "% change", "%change", "change")
    i_vol = col("volume", "vol")

    out = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        sym = (r[i_sym] if i_sym >= 0 and i_sym < len(r) else "").strip()
        if not sym:
            continue
        get = lambda i: r[i] if 0 <= i < len(r) else ""
        out.append({
            "symbol": sym,
            "name": get(i_name).strip(),
            "close": clean_num(get(i_close)),
            "change": clean_num(get(i_chg)),
            "volume": clean_int(get(i_vol)),
        })
    return out


def friday_of_week(d: date) -> date:
    """Friday (weekday 4) of the calendar week containing d (Mon-anchored week)."""
    return d + timedelta(days=(4 - d.weekday()))


def load_history(url: str):
    if HISTORY.exists():
        h = json.loads(HISTORY.read_text())
    else:
        slug = url.rstrip("/").split("/")[-1]
        h = {"screener": slug, "source_url": url, "weeks": []}
    return h


def save_history(h):
    HISTORY.write_text(json.dumps(h, indent=2))


def ingest(h, csv_path: Path, url: str):
    recs = read_records(csv_path)
    if not recs:
        raise RuntimeError(f"No ticker rows parsed from {csv_path}")
    wk = friday_of_week(date.today()).isoformat()
    try:
        mtime = datetime.fromtimestamp(csv_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        mtime = ""
    entry = {"week": wk, "scraped_at": mtime, "tickers": recs}
    weeks = [w for w in h["weeks"] if w["week"] != wk]  # replace same-week re-run
    weeks.append(entry)
    weeks.sort(key=lambda w: w["week"])
    h["weeks"] = weeks
    if url:
        h["source_url"] = url
        h["screener"] = url.rstrip("/").split("/")[-1]
    print(f"📥 Ingested week {wk}: {len(recs)} tickers ({len(h['weeks'])} weeks tracked)")
    return h


def render(h, window: int):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Template missing: {TEMPLATE}")
    payload = dict(h)
    payload["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    payload["window"] = window
    html = TEMPLATE.read_text()
    b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    html = html.replace("__HISTORY_B64__", b64).replace("__WINDOW__", str(window))
    OUT.write_text(html)
    weeks = h["weeks"][-window:]
    print(f"🖼  Rendered {OUT.name} · window={window} · weeks in view: "
          f"{', '.join(w['week'] for w in weeks) or 'none'}")
    return OUT


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest weekly snapshot + render dashboard")
    ap.add_argument("--ingest", type=Path, help="CSV snapshot to add as this week")
    ap.add_argument("--url", default=DEFAULT_URL, help="Source screener URL (for metadata)")
    ap.add_argument("--window", type=int, default=5, help="Rolling window in weeks (default 5)")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    h = load_history(args.url)
    if args.ingest:
        if not args.ingest.exists():
            print(f"❌ Snapshot not found: {args.ingest}", file=sys.stderr)
            return 1
        h = ingest(h, args.ingest, args.url)
        save_history(h)
    if not h["weeks"]:
        print("⚠️  No weeks in history yet — run scrape.py then --ingest.", file=sys.stderr)
    render(h, args.window)
    return 0


if __name__ == "__main__":
    sys.exit(main())
