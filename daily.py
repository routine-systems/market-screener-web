#!/usr/bin/env python3
"""
Daily potentials — cross-tab of daily screeners.

Scrapes (daily backtests):
  cp-ich-trend-bounce-dly       primary  (the daily potentials universe + history)
  cp-ich-trend-bounce-dly-fil   filter   (stricter subset → gold highlight dot)
  cp-pb                         signal   (price breakout)
  cp-mq                         signal   (Minervini Quotient)

Builds data/history_daily.json and renders daily.html: tickers on the selected day
ranked by cross-tab score = in dly (always) + also in PB + also in MQ (1–3), so a
ticker in all three ranks highest; plus a consistency dot-grid over the last N days.
Run 2–3× a day.

    python3 daily.py                 # scrape all four (pause between), render
    python3 daily.py --no-scrape     # re-render from the stored history
"""

import argparse
import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from selenium.webdriver.support.ui import WebDriverWait

from scrape import build_driver, download_backtest_csv, extract_scanlink
import build_dashboard as bd

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
STORE = DATA_DIR / "history_daily.json"
TEMPLATE = HERE / "daily_template.html"
OUT = HERE / "daily.html"
TMP = DATA_DIR / ".dly_tmp"
BASE = "https://chartink.com/screener/"

PRIMARY = "cp-ich-trend-bounce-dly"
FILTER = "cp-ich-trend-bounce-dly-fil"
SIGNALS = [("pb", "PB", "Price breakout", "cp-pb"),
           ("mq", "MQ", "Minervini Quotient", "cp-mq")]


def fetch_csv(driver, slug, timeout):
    """Load a screener, return (csv_path_in_TMP, scanlink, timeframe)."""
    driver.get(BASE + slug)
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete")
    time.sleep(6)
    scanlink, timeframe = extract_scanlink(driver.page_source)
    for p in TMP.glob("*.csv"):
        p.unlink()
    got = download_backtest_csv(driver, TMP, timeout, set())
    return got, scanlink, timeframe


def scrape_all(pause, headless, timeout):
    TMP.mkdir(parents=True, exist_ok=True)
    driver = build_driver(TMP, headless)
    try:
        print(f"[1] primary {PRIMARY}")
        csv, scanlink, timeframe = fetch_csv(driver, PRIMARY, timeout)
        h = bd.build_history(csv, BASE + PRIMARY, scanlink, timeframe or "daily")
        h["timeframe"] = timeframe or "daily"
        h["mode"] = "daily"
        csv.unlink()
        print(f"    {len(h['weeks'])} days ({h['weeks'][0]['week']}..{h['weeks'][-1]['week']}); scanlink {scanlink}")

        time.sleep(pause)
        print(f"[2] filter {FILTER}")
        csv, _, _ = fetch_csv(driver, FILTER, timeout)
        bd.attach_filter(h, csv, BASE + FILTER)
        csv.unlink()

        h["signals"] = []
        for i, (key, label, name, slug) in enumerate(SIGNALS, 3):
            time.sleep(pause)
            print(f"[{i}] signal {slug} ({label})")
            csv, _, _ = fetch_csv(driver, slug, timeout)
            mem = bd.parse_membership(csv)
            csv.unlink()
            h["signals"].append({"key": key, "label": label, "name": name,
                                 "url": BASE + slug, "weeks": mem})
            last = max(mem) if mem else "—"
            print(f"    {len(mem)} days; latest {last} → {len(mem.get(last, [])) if mem else 0} symbols")
        return h
    finally:
        driver.quit()
        try:
            for p in TMP.glob("*"):
                p.unlink()
            TMP.rmdir()
        except OSError:
            pass


def render(h):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Template missing: {TEMPLATE}")
    payload = dict(h)
    payload["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    OUT.write_text(TEMPLATE.read_text().replace("__HISTORY_B64__", b64))
    print(f"🖼  Rendered {OUT.name}")
    return OUT


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily potentials cross-tab dashboard")
    ap.add_argument("--pause", type=float, default=4.0, help="Seconds between screener downloads")
    ap.add_argument("--no-scrape", action="store_true", help="Re-render from stored history")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if args.no_scrape:
        if not STORE.exists():
            print("❌ No stored history — run without --no-scrape first.", file=sys.stderr)
            return 1
        h = json.loads(STORE.read_text())
    else:
        h = scrape_all(args.pause, not args.show, args.timeout)
        STORE.write_text(json.dumps(h))
    render(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
