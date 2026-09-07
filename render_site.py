#!/usr/bin/env python3
"""Validate a versioned signal bundle and render the Cloudflare Pages site."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DEFAULT_BUNDLE = ROOT / "artifacts" / "signals-bundle.v1.json"
DEFAULT_OUTPUT = ROOT / "dist"
TEMPLATES = ROOT / "templates"
FUNCTIONS = ROOT / "functions"
ASSETS = ROOT / "assets"
REQUIRED_FIELDS = {
    "schema_version",
    "producer_commit",
    "generated_at_utc",
    "data_cutoff",
    "markets",
    "timeframes",
    "pages",
    "source_freshness",
    "event_gate_status",
    "artifacts",
}
PAGE_SPECS = {
    "weekly": ("weekly.html", "dashboard.html", "__HISTORY_B64__"),
    "daily": ("daily.html", "daily.html", "__HISTORY_B64__"),
    "market": ("market.html", "market.html", "__MARKET_B64__"),
    "sectors": ("sectors.html", "sectors.html", "__SECTOR_B64__"),
    "recommendations": (
        "recommendations.html",
        "recommendations.html",
        "__RECOMMENDATIONS_B64__",
    ),
}
NAV_ITEMS = (
    ("shortlist", "shortlist.html", "Shortlist"),
    ("weekly", "dashboard.html", "Weekly"),
    ("daily", "daily.html", "Daily"),
    ("us-weekly", "us-weekly.html", "US Weekly"),
    ("us-daily", "us-daily.html", "US Daily"),
    ("ht", "tsha_hbcs.html", "HT"),
    ("vt", "volume_trend.html", "VT"),
    ("transactions", "transactions.html", "Trades"),
    ("market", "market.html", "Market"),
    ("sectors", "sectors.html", "Sectors"),
    ("recommendations", "recommendations.html", "Forward Test"),
)
TREND_BOUNCE_TEMPLATE = "us_trend_bounce.html"
TREND_BOUNCE_PAGES = {
    "weekly": "us-weekly.html",
    "daily": "us-daily.html",
}
PLACEHOLDER = re.compile(r"__[A-Z0-9_]+__")
IST = ZoneInfo("Asia/Kolkata")


class BundleError(ValueError):
    """Raised when an input bundle violates the web contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleError(f"{field} must be a non-empty ISO-8601 string")
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise BundleError(f"{field} is not ISO-8601: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BundleError(f"{field} must include a timezone offset")
    return value


def _parse_cutoff(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise BundleError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise BundleError(f"{field} must be an ISO date") from exc
    return parsed


def _validate_chartink_freshness(bundle: dict) -> None:
    source = bundle["source_freshness"]
    cutoffs = {}
    for name in ("weekly", "daily", "market", "sectors"):
        item = source.get(name)
        if not isinstance(item, dict):
            raise BundleError(f"source_freshness.{name} must be an object")
        cutoffs[name] = _parse_cutoff(
            item.get("as_of"), f"source_freshness.{name}.as_of"
        )

    expected_week = cutoffs["daily"] - timedelta(days=cutoffs["daily"].weekday())
    if cutoffs["market"] != cutoffs["daily"]:
        raise BundleError(
            "Chartink market cutoff must equal the daily cutoff: "
            f"{cutoffs['market']} != {cutoffs['daily']}"
        )
    for name in ("weekly", "sectors"):
        if cutoffs[name] != expected_week:
            raise BundleError(
                f"Chartink {name} cutoff must equal the daily session's Monday: "
                f"{cutoffs[name]} != {expected_week}"
            )


def _format_ist(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(IST).strftime("%d %b %Y, %H:%M IST")


def _page_data_as_of(bundle: dict, page_name: str) -> str:
    freshness = bundle["source_freshness"].get(page_name, {})
    if isinstance(freshness, dict) and isinstance(freshness.get("as_of"), str):
        return freshness["as_of"]
    if page_name == "recommendations":
        cutoffs = [
            value
            for value in bundle["data_cutoff"].values()
            if isinstance(value, str) and value
        ]
        return min(cutoffs, default="")
    return ""


def _validate_artifact(item: object, index: int) -> None:
    if not isinstance(item, dict):
        raise BundleError(f"artifacts[{index}] must be an object")
    required = {"path", "row_count", "sha256"}
    missing = sorted(required - set(item))
    if missing:
        raise BundleError(f"artifacts[{index}] misses {', '.join(missing)}")
    path = item["path"]
    if not isinstance(path, str) or not path:
        raise BundleError(f"artifacts[{index}].path must be a non-empty string")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise BundleError(f"artifacts[{index}].path must remain bundle-relative")
    if not isinstance(item["row_count"], int) or item["row_count"] < 0:
        raise BundleError(f"artifacts[{index}].row_count must be a non-negative integer")
    checksum = item["sha256"]
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise BundleError(f"artifacts[{index}].sha256 must be lowercase SHA-256")


def _validate_linked_payload(page_name: str, payload: dict) -> None:
    cross = payload.get("cross")
    if not isinstance(cross, dict) or not isinstance(cross.get("weeks"), dict):
        raise BundleError(
            f"pages.{page_name}.payload.cross requires a weeks object"
        )
    rotation = payload.get("rotation")
    if not isinstance(rotation, dict):
        raise BundleError(f"pages.{page_name}.payload.rotation must be an object")
    for field in ("levels", "status", "of"):
        if field not in rotation:
            raise BundleError(
                f"pages.{page_name}.payload.rotation misses {field}"
            )
    if not isinstance(rotation["levels"], list):
        raise BundleError(f"pages.{page_name}.payload.rotation.levels must be an array")
    if not isinstance(rotation["status"], dict):
        raise BundleError(f"pages.{page_name}.payload.rotation.status must be an object")
    if not isinstance(rotation["of"], dict):
        raise BundleError(f"pages.{page_name}.payload.rotation.of must be an object")


def validate_bundle(bundle: object) -> dict:
    if not isinstance(bundle, dict):
        raise BundleError("bundle root must be an object")
    missing = sorted(REQUIRED_FIELDS - set(bundle))
    if missing:
        raise BundleError(f"bundle misses {', '.join(missing)}")

    version = bundle["schema_version"]
    if not isinstance(version, str) or version.split(".", 1)[0] != "1":
        raise BundleError(f"unsupported schema_version: {version!r}")
    if not isinstance(bundle["producer_commit"], str) or not bundle["producer_commit"]:
        raise BundleError("producer_commit must be a non-empty string")
    _parse_timestamp(bundle["generated_at_utc"], "generated_at_utc")
    if not isinstance(bundle["data_cutoff"], dict):
        raise BundleError("data_cutoff must be an object")
    if not isinstance(bundle["markets"], list) or not bundle["markets"]:
        raise BundleError("markets must be a non-empty array")
    if not isinstance(bundle["timeframes"], list) or not bundle["timeframes"]:
        raise BundleError("timeframes must be a non-empty array")
    if not isinstance(bundle["source_freshness"], dict):
        raise BundleError("source_freshness must be an object")
    _validate_chartink_freshness(bundle)
    if not isinstance(bundle["event_gate_status"], dict):
        raise BundleError("event_gate_status must be an object")

    pages = bundle["pages"]
    if not isinstance(pages, dict):
        raise BundleError("pages must be an object")
    missing_pages = sorted(set(PAGE_SPECS) - set(pages))
    if missing_pages:
        raise BundleError(f"bundle misses pages: {', '.join(missing_pages)}")
    for page_name in PAGE_SPECS:
        page = pages[page_name]
        if not isinstance(page, dict) or not isinstance(page.get("payload"), dict):
            raise BundleError(f"pages.{page_name}.payload must be an object")
    for page_name in ("weekly", "daily"):
        _validate_linked_payload(page_name, pages[page_name]["payload"])
    weekly_window = pages["weekly"].get("default_window", 8)
    if not isinstance(weekly_window, int) or weekly_window < 1:
        raise BundleError("pages.weekly.default_window must be a positive integer")

    artifacts = bundle["artifacts"]
    if not isinstance(artifacts, list):
        raise BundleError("artifacts must be an array")
    for index, artifact in enumerate(artifacts):
        _validate_artifact(artifact, index)
    return bundle


def load_bundle(path: Path) -> dict:
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BundleError(f"bundle not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BundleError(f"bundle is not valid JSON: {exc}") from exc
    return validate_bundle(bundle)


def _navigation(active: str) -> str:
    links = []
    for page, href, label in NAV_ITEMS:
        state = ' class="on" aria-current="page"' if page == active else ""
        links.append(f'<a href="{href}"{state}>{label}</a>')
    return (
        '<a class="skip-link" href="#main-content">Skip to results</a>'
        '<nav class="nav dashboard-nav" aria-label="Views">'
        + "".join(links)
        + '<span class="sp"></span>'
        + '<button class="themebtn" id="themeBtn" type="button" '
        + 'aria-label="Change color theme">◐ Theme</button></nav>'
    )


def _freshness_strip(active: str) -> str:
    active_source = {
        "weekly": "india_weekly",
        "daily": "india_daily",
        "market": "market",
        "sectors": "sectors",
        "us-weekly": "us_weekly",
        "us-daily": "us_daily",
        "ht": "ht",
        "shortlist": "ht",
        "recommendations": "outcomes",
    }.get(active)

    def item(source: str, label: str, value: str | None = None) -> str:
        state = ' data-active="true"' if source == active_source else ""
        slots = value or f'<time data-freshness="{source}">—</time>'
        return (
            f'<div class="freshness-item" data-freshness-group="{source}"{state}>'
            f'<span class="freshness-name">{label}</span>'
            f'<span class="freshness-value">{slots}</span></div>'
        )

    ht_value = (
        '<span class="freshness-market">IN</span> '
        '<time data-freshness="ht_india">—</time>'
        '<span class="freshness-divider">/</span>'
        '<span class="freshness-market">US</span> '
        '<time data-freshness="ht_us">—</time>'
    )
    return (
        '<section class="dashboard-freshness" aria-label="Source cutoff dates">'
        '<h2 class="freshness-heading">Cutoffs</h2>'
        '<div class="freshness-items">'
        + item("india_weekly", "India Weekly")
        + item("india_daily", "India Daily")
        + item("market", "Market")
        + item("sectors", "Sectors")
        + item("us_weekly", "US Weekly")
        + item("us_daily", "US Daily")
        + item("ht", "HT", ht_value)
        + item("outcomes", "Forward Test")
        + "</div></section>"
    )


def _apply_shell(source: str, active: str) -> str:
    if "__DASHBOARD_NAV__" not in source:
        raise BundleError(f"template for {active} misses __DASHBOARD_NAV__")
    if "__DASHBOARD_FRESHNESS__" not in source:
        raise BundleError(f"template for {active} misses __DASHBOARD_FRESHNESS__")
    source = source.replace("__DASHBOARD_NAV__", _navigation(active))
    source = source.replace("__DASHBOARD_FRESHNESS__", _freshness_strip(active))
    assets = (
        '<script src="dashboard-shell.js?v=2"></script>'
        '<script src="market-rotation.js?v=1"></script>'
        '<link rel="stylesheet" href="dashboard-shell.css?v=3">'
    )
    return source.replace("</head>", f"{assets}</head>", 1)


def _render_template(
    template_path: Path,
    token: str,
    payload: dict,
    window: int,
    active: str,
) -> str:
    source = template_path.read_text(encoding="utf-8")
    encoded = base64.b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    if token not in source:
        raise BundleError(f"template {template_path.name} misses {token}")
    rendered = source.replace(token, encoded).replace("__WINDOW__", str(window))
    rendered = _apply_shell(rendered, active)
    leftovers = sorted(set(PLACEHOLDER.findall(rendered)))
    if leftovers:
        raise BundleError(
            f"template {template_path.name} has unresolved placeholders: {', '.join(leftovers)}"
        )
    return rendered


def _source_freshness(bundle: dict) -> dict:
    source = bundle.get("source_freshness", {})

    def item(name: str, fallback: object = None) -> dict:
        value = source.get(name, {})
        if isinstance(value, str):
            value = {"as_of": value}
        elif not isinstance(value, dict):
            value = {}
        result = {
            key: value[key]
            for key in ("as_of", "status")
            if key in value and value[key] is not None
        }
        if not result.get("as_of") and fallback:
            result["as_of"] = fallback
        return result

    cutoffs = bundle.get("data_cutoff", {})
    return {
        "schema_version": "dashboard-freshness.v1",
        "generated_at_utc": bundle["generated_at_utc"],
        "sources": {
            "india_weekly": item("weekly", cutoffs.get("IN")),
            "india_daily": item("daily", cutoffs.get("IN")),
            "market": item("market"),
            "sectors": item("sectors"),
            "us_weekly": item("us_weekly"),
            "us_daily": item("us_daily"),
            "ht_india": item("ht_india"),
            "ht_us": item("ht_us"),
            "vt_india": item("vt_india"),
            "vt_us": item("vt_us"),
            "outcomes": item("recommendations"),
        },
    }


def _index_document() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0; url=shortlist.html"><title>Screener</title></head>
<body><a href="shortlist.html">Open the shortlist</a></body></html>
"""


def render_site(bundle_path: Path, output: Path = DEFAULT_OUTPUT) -> dict:
    bundle = load_bundle(bundle_path)
    ht_page = TEMPLATES / "tsha_hbcs.html"
    if not ht_page.is_file():
        raise BundleError(f"HT template not found: {ht_page}")
    vt_page = TEMPLATES / "volume_trend.html"
    if not vt_page.is_file():
        raise BundleError(f"VT template not found: {vt_page}")
    transactions_page = TEMPLATES / "transactions.html"
    if not transactions_page.is_file():
        raise BundleError(f"transactions template not found: {transactions_page}")
    trend_bounce_template = TEMPLATES / TREND_BOUNCE_TEMPLATE
    if not trend_bounce_template.is_file():
        raise BundleError(f"US Trend Bounce template not found: {trend_bounce_template}")
    clusters_page = TEMPLATES / "clusters.html"
    if not clusters_page.is_file():
        raise BundleError(f"HT/VT Shortlist template not found: {clusters_page}")
    temp = output.parent / f".{output.name}.tmp"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)

    generated = bundle["generated_at_utc"]
    window = bundle["pages"]["weekly"].get("default_window", 8)
    for page_name, (template_name, output_name, token) in PAGE_SPECS.items():
        payload = dict(bundle["pages"][page_name]["payload"])
        payload.setdefault("generated_at", generated)
        payload["last_updated_ist"] = _format_ist(generated)
        payload["data_as_of"] = _page_data_as_of(bundle, page_name)
        html = _render_template(
            TEMPLATES / template_name,
            token,
            payload,
            window,
            page_name,
        )
        (temp / output_name).write_text(html, encoding="utf-8")

    shortlist_source = _apply_shell(clusters_page.read_text(encoding="utf-8"), "shortlist")
    (temp / "shortlist.html").write_text(shortlist_source, encoding="utf-8")

    (temp / "index.html").write_text(_index_document(), encoding="utf-8")
    ht_source = _apply_shell(ht_page.read_text(encoding="utf-8"), "ht")
    (temp / "tsha_hbcs.html").write_text(ht_source, encoding="utf-8")
    vt_source = _apply_shell(vt_page.read_text(encoding="utf-8"), "vt")
    (temp / "volume_trend.html").write_text(vt_source, encoding="utf-8")
    transactions_source = _apply_shell(
        transactions_page.read_text(encoding="utf-8"), "transactions"
    )
    (temp / "transactions.html").write_text(
        transactions_source, encoding="utf-8"
    )
    trend_source = trend_bounce_template.read_text(encoding="utf-8")
    for timeframe, output_name in TREND_BOUNCE_PAGES.items():
        rendered = trend_source.replace("__TIMEFRAME__", timeframe)
        rendered = _apply_shell(rendered, f"us-{timeframe}")
        leftovers = sorted(set(PLACEHOLDER.findall(rendered)))
        if leftovers:
            raise BundleError(
                f"template {TREND_BOUNCE_TEMPLATE} has unresolved placeholders: "
                f"{', '.join(leftovers)}"
            )
        (temp / output_name).write_text(rendered, encoding="utf-8")
    if FUNCTIONS.exists():
        shutil.copytree(FUNCTIONS, temp / "functions")
    if ASSETS.exists():
        for asset in ASSETS.iterdir():
            if asset.is_file():
                shutil.copy2(asset, temp / asset.name)

    (temp / "india-rotation.json").write_text(
        json.dumps({"rotation": bundle["pages"]["weekly"]["payload"]["rotation"]}) + "\n",
        encoding="utf-8",
    )

    (temp / "dashboard-freshness.json").write_text(
        json.dumps(_source_freshness(bundle), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rendered_files = sorted(
        path.relative_to(temp).as_posix() for path in temp.rglob("*") if path.is_file()
    )
    manifest = {
        "schema_version": 1,
        "bundle_sha256": _sha256(bundle_path),
        "producer_commit": bundle["producer_commit"],
        "generated_at_utc": generated,
        "files": rendered_files,
    }
    (temp / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if output.exists():
        shutil.rmtree(output)
    temp.replace(output)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = render_site(args.bundle, args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
