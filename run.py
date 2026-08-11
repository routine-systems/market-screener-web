#!/usr/bin/env python3
"""
Single entry point for the Chartink weekly tracker.

Both modes scrape the screener's BACKTEST CSV (full 3-year weekly history) and
rebuild the dashboard. Because that one download already carries every week, the
modes differ only in intent/scheduling — there is no forward accumulation:

  --mode weekly   The Friday / launchd job (picks up the newest weekly date).
  --mode adhoc    A manual refresh you run anytime.

    python3 run.py --mode weekly
    python3 run.py --mode adhoc --url https://chartink.com/screener/<slug>
"""

import argparse
import sys

import scrape as scr
import build_dashboard as bd


def main() -> int:
    ap = argparse.ArgumentParser(description="Chartink weekly tracker — weekly / adhoc")
    ap.add_argument("--mode", choices=["weekly", "adhoc"], default="weekly")
    ap.add_argument("--url", default=scr.DEFAULT_URL, help="Chartink screener URL")
    ap.add_argument(
        "--window",
        type=int,
        default=bd.DEFAULT_WINDOW,
        help="Default rolling window (weeks)",
    )
    ap.add_argument("--filter-url", help="Filtered-subset screener URL (default: <url>-fil)")
    ap.add_argument("--no-filter", action="store_true", help="Skip the filtered-subset overlay")
    ap.add_argument("--refresh", action="store_true", help="Only re-extract the scanlink and rebuild (no download)")
    ap.add_argument("--show", action="store_true", help="Show the browser window")
    args = ap.parse_args()

    # cheap fix for an expired scanlink: re-extract it and rebuild from the local CSV
    if args.refresh:
        try:
            scr.scanlink_only(args.url, headless=not args.show)   # updates the sidecar meta
        except Exception as e:  # noqa: BLE001
            print(f"❌ scanlink refresh failed: {e}", file=sys.stderr)
            return 1
        rc = bd.rebuild(args.url, args.window)
        if rc == 0:
            print("✔ refresh complete → dashboard.html (scanlink updated, no re-download)")
        return rc

    try:
        res = scr.scrape(args.url, headless=not args.show)
    except Exception as e:  # noqa: BLE001
        print(f"❌ scrape failed: {e}", file=sys.stderr)
        return 1

    h = bd.build_history(res["csv"], args.url, res.get("scanlink"), res.get("timeframe"))

    # filtered-subset screener (default <url>-fil): per-week membership → highlight dots
    if not args.no_filter:
        furl = args.filter_url or (args.url + "-fil")
        try:
            scr.polite_pause()                       # random gap before the next pull
            fres = scr.scrape(furl, headless=not args.show)
            bd.attach_filter(h, fres["csv"], furl)
        except Exception as e:  # noqa: BLE001
            print(f"⚠ filter screener skipped ({furl}): {e}")

    bd.save_history(h)
    bd.render(h, args.window)
    print(f"✔ {args.mode} run complete → dashboard.html "
          f"({len(h['weeks'])} weeks, window {args.window})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
