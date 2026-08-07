#!/usr/bin/env python3
"""
Single entry point for the Chartink weekly tracker.

Modes:
  --mode weekly   Scrape → refresh the rotating scanlink → add/replace THIS week's
                  snapshot in history → rebuild dashboard.  (Friday / launchd job.)
  --mode adhoc    Scrape → refresh the scanlink → rebuild dashboard from existing
                  history WITHOUT adding a week.  (Run anytime to refresh links/HTML.)

Both modes re-extract the scanlink every run (Chartink rotates it).

    python3 run.py --mode weekly
    python3 run.py --mode adhoc --url https://chartink.com/screener/<slug>
"""

import argparse
import sys

import scrape as scr
import build_dashboard as bd


def main() -> int:
    ap = argparse.ArgumentParser(description="Chartink weekly tracker — weekly / adhoc")
    ap.add_argument("--mode", choices=["weekly", "adhoc"], default="weekly",
                    help="weekly = add this week's snapshot; adhoc = refresh only")
    ap.add_argument("--url", default=scr.DEFAULT_URL, help="Chartink screener URL")
    ap.add_argument("--window", type=int, default=5, help="Default rolling window (weeks)")
    ap.add_argument("--show", action="store_true", help="Show the browser window")
    args = ap.parse_args()

    try:
        res = scr.scrape(args.url, headless=not args.show)
    except Exception as e:  # noqa: BLE001
        print(f"❌ scrape failed: {e}", file=sys.stderr)
        return 1

    h = bd.load_history(args.url)
    bd.set_meta(h, res.get("scanlink"), res.get("timeframe"))
    if args.mode == "weekly":
        bd.ingest(h, res["csv"], args.url)
    else:
        print("↻ adhoc: refreshed scanlink, no new week added")
    bd.save_history(h)
    bd.render(h, args.window)
    print(f"✔ {args.mode} run complete → dashboard.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
