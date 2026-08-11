#!/usr/bin/env python3
"""Append-only recommendation decisions and forward outcome snapshots."""

from __future__ import annotations

import argparse
import html
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import duckdb
import exchange_calendars as xcals
import numpy as np
import pandas as pd

import backtest_research as india_research
import recommendation_diagnostics as diagnostics
import us_market_data
import weekly_pilot


INDIA_CANDIDATE_PATH = Path("reports/combined_recommendation_candidates.csv")
US_CANDIDATE_PATH = Path("reports/us_combined_recommendation_candidates.csv")
STORE_ROOT = Path("data/forward_test")
DECISION_PATH = STORE_ROOT / "recommendation_decisions.parquet"
OUTCOME_PATH = STORE_ROOT / "recommendation_outcomes.parquet"
ANNOTATION_PATH = STORE_ROOT / "recommendation_annotations.parquet"
SUMMARY_PATH = Path("reports/recommendation_forward_test.csv")
HTML_PATH = Path("recommendations.html")
BENCHMARKS = {"IN": "NIFTYBEES", "US": "SPY"}
HORIZONS = (1, 5, 10, 20, 50)
OPPORTUNITY_MISS_RETURN = 0.10
ACTIVE_TIMEFRAME = "weekly"

DECISION_FIELDS = [
    "decision_id",
    "captured_at_utc",
    "market",
    "timeframe",
    "signal_date",
    "planned_entry_date",
    "symbol",
    "exchange",
    "presented",
    "shortlist_rank",
    "actionable_entry",
    "decision_stage",
    "exclusion_reason",
    "model_rank_score",
    "signal_close",
    "median_turnover_20",
    "volume_ratio_20",
    "rsi14",
    "rs20",
    "atr_pct14",
    "return_1d",
    "volume_ratio_5_prior",
    "volume_ratio_20_prior",
    "turnover_ratio_5_prior",
    "delivery_qty_ratio_20_prior",
    "delivery_pct_delta_20",
    "distance_to_20d_high_prior",
    "distance_to_55d_high_prior",
    "close_location_value",
    "true_range_ratio_20_prior",
    "realized_vol_5_vs_20_prior",
    "diagnostic_policy",
    "weekly_cmo_14",
    "weekly_cmo_ema_10",
    "weekly_cmo_ema_change",
    "weekly_cmo_ema_acceleration",
    "weekly_cmo_ema_rising",
    "weekly_cmo_ema_rising_trigger",
    "weekly_cmo_ema_accelerating",
    "weekly_cmo_ema_accelerating_trigger",
    "weekly_cmo_policy",
    "weekly_vbsm_nres1",
    "weekly_vbsm_nres2",
    "weekly_vbsm_pvi_nvi",
    "weekly_vbsm_sma_25",
    "weekly_vbsm_gap",
    "weekly_vbsm_gap_change",
    "weekly_vbsm_above",
    "weekly_vbsm_cross_above",
    "weekly_vbsm_policy",
    "twin_ha_status",
    "occurrence_count_5",
    "occurrence_3of5_trigger",
    "rotation_group",
    "rotation_state",
    "event_gate_status",
    "opening_gate_status",
    "research_gate_status",
    "snapshot_json",
]


def _as_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _value(row: pd.Series, name: str, default: object = pd.NA) -> object:
    return row[name] if name in row.index else default


def _decision_scope(candidates: pd.DataFrame) -> pd.Series:
    mechanical = candidates.get(
        "mechanical_exclusion_reason", pd.Series("", index=candidates.index)
    ).fillna("").eq("")
    presented = candidates.get(
        "presented", pd.Series(False, index=candidates.index)
    ).map(_as_bool)
    event_pool = candidates.get(
        "event_pool_selected", pd.Series(False, index=candidates.index)
    ).map(_as_bool)
    return mechanical | presented | event_pool


def active_weekly_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return rows that remain active under the weekly recommendation policy."""
    return active_timeframe_rows(frame, (ACTIVE_TIMEFRAME,))


def active_timeframe_rows(
    frame: pd.DataFrame,
    timeframes: tuple[str, ...] | None,
) -> pd.DataFrame:
    """Filter generated decisions without limiting the underlying daily data store."""
    if timeframes is None:
        return frame.copy()
    invalid = set(timeframes) - {"daily", "weekly"}
    if invalid:
        raise ValueError(f"unsupported timeframes: {sorted(invalid)}")
    return frame[frame["timeframe"].isin(timeframes)].copy()


def _decision_stage(row: pd.Series) -> str:
    if _as_bool(_value(row, "presented", False)):
        return "presented"
    mechanical_reason = str(_value(row, "mechanical_exclusion_reason", "") or "")
    if mechanical_reason == "nan":
        mechanical_reason = ""
    exclusion = str(_value(row, "exclusion_reason", "") or "")
    if exclusion == "outside_event_refresh_pool":
        return "near_miss_budget"
    if _as_bool(_value(row, "event_pool_selected", False)):
        return "event_pool_rejected" if exclusion and exclusion != "nan" else "event_pool"
    if not mechanical_reason:
        return "mechanical_survivor"
    return "mechanically_excluded"


def _next_session(market: str, signal_date: pd.Timestamp) -> pd.Timestamp:
    if market == "IN":
        return pd.Timestamp(weekly_pilot.capital_market_sessions_after(signal_date, 1)[0])
    calendar = xcals.get_calendar("XNYS")
    session = calendar.date_to_session(pd.Timestamp(signal_date), direction="previous")
    return pd.Timestamp(calendar.next_session(session)).tz_localize(None)


def _json_snapshot(row: pd.Series) -> str:
    values = {}
    for key, value in row.items():
        if pd.isna(value):
            values[str(key)] = None
        elif isinstance(value, (pd.Timestamp, datetime)):
            values[str(key)] = value.isoformat()
        elif isinstance(value, np.generic):
            values[str(key)] = value.item()
        else:
            values[str(key)] = value
    return json.dumps(values, sort_keys=True, default=str)


def normalize_decisions(
    market: str,
    candidates: pd.DataFrame,
    planned_entry_date: pd.Timestamp | None = None,
    captured_at: datetime | None = None,
) -> pd.DataFrame:
    """Normalize candidate-stage rows to immutable decision records."""
    frame = candidates[_decision_scope(candidates)].copy()
    if frame.empty:
        return pd.DataFrame(columns=DECISION_FIELDS)
    frame["signal_date"] = pd.to_datetime(frame["signal_date"])
    captured = (captured_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        signal_date = pd.Timestamp(row["signal_date"])
        entry_value = _value(row, "planned_entry_date")
        entry_date = (
            pd.Timestamp(planned_entry_date)
            if planned_entry_date is not None
            else pd.Timestamp(entry_value)
            if not pd.isna(entry_value)
            else _next_session(market, signal_date)
        )
        symbol = str(row["symbol"])
        timeframe = str(row["timeframe"])
        signal_close = _value(row, "latest_close")
        if pd.isna(signal_close):
            signal_close = _value(row, "daily_close")
        if pd.isna(signal_close):
            signal_close = _value(row, "weekly_close")
        rotation_group = _value(row, "rotation_group")
        if pd.isna(rotation_group):
            rotation_group = _value(row, "rotation_industry_group")
        rotation_state = _value(row, "strict_rotation_rising")
        if pd.isna(rotation_state):
            rotation_state = _value(row, "rotation_industry")
        occurrence_count = _value(row, "occurrence_count_5")
        occurrence_trigger = _value(row, "occurrence_3of5_trigger")
        if pd.isna(occurrence_count):
            occurrence_count = _value(row, "wkly_fil_count_5")
        if pd.isna(occurrence_trigger):
            occurrence_trigger = _value(row, "wkly_fil_3of5_trigger")
        normalized = {
            "decision_id": f"{market}_{timeframe.upper()}_{signal_date:%Y%m%d}_{symbol}",
            "captured_at_utc": captured,
            "market": market,
            "timeframe": timeframe,
            "signal_date": signal_date.normalize(),
            "planned_entry_date": entry_date.normalize(),
            "symbol": symbol,
            "exchange": _value(row, "exchange", "NSE" if market == "IN" else pd.NA),
            "presented": _as_bool(_value(row, "presented", False)),
            "shortlist_rank": _value(row, "shortlist_rank"),
            "actionable_entry": _as_bool(_value(row, "actionable_entry", False)),
            "decision_stage": _decision_stage(row),
            "exclusion_reason": _value(row, "exclusion_reason", ""),
            "model_rank_score": _value(row, "model_rank_score"),
            "signal_close": signal_close,
            "rotation_group": rotation_group,
            "rotation_state": rotation_state,
            "occurrence_count_5": occurrence_count,
            "occurrence_3of5_trigger": occurrence_trigger,
            "snapshot_json": _json_snapshot(row),
        }
        for field in DECISION_FIELDS:
            if field not in normalized:
                normalized[field] = _value(row, field)
        rows.append(normalized)
    result = pd.DataFrame(rows)[DECISION_FIELDS]
    result["signal_date"] = pd.to_datetime(result["signal_date"])
    result["planned_entry_date"] = pd.to_datetime(result["planned_entry_date"])
    return result.sort_values(
        ["signal_date", "market", "timeframe", "presented", "model_rank_score", "symbol"],
        ascending=[True, True, True, False, False, True],
    ).reset_index(drop=True)


def _load_us_bars(
    symbols: set[str],
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    pattern = str((us_market_data.BAR_ROOT / "bucket=*" / "part.parquet").resolve())
    placeholders = ",".join("?" for _ in symbols)
    conditions = [f"symbol IN ({placeholders})"]
    parameters: list[object] = [pattern, *sorted(symbols)]
    if start is not None:
        conditions.append("date >= ?")
        parameters.append(pd.Timestamp(start))
    if end is not None:
        conditions.append("date <= ?")
        parameters.append(pd.Timestamp(end))
    query = f"""
        SELECT symbol, date,
               open * COALESCE(adj_close / NULLIF(close, 0), 1) AS open,
               high * COALESCE(adj_close / NULLIF(close, 0), 1) AS high,
               low * COALESCE(adj_close / NULLIF(close, 0), 1) AS low,
               COALESCE(adj_close, close) AS close,
               volume
        FROM read_parquet(?, union_by_name=true)
        WHERE {' AND '.join(conditions)}
        ORDER BY symbol, date
    """
    return duckdb.connect().execute(query, parameters).fetchdf()


def _attach_missing_diagnostics(market: str, candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates[_decision_scope(candidates)].copy()
    if frame.empty:
        return frame
    cutoff = pd.Timestamp(frame["signal_date"].max())
    if market == "IN":
        prices = india_research.load_prices()
    else:
        prices = _load_us_bars(
            set(frame["symbol"].astype(str)),
            cutoff - pd.Timedelta(days=180),
            cutoff,
        )
    existing = [column for column in diagnostics.ALL_DIAGNOSTIC_COLUMNS if column in frame]
    frame = frame.drop(columns=existing)
    return diagnostics.attach_price_diagnostics(frame, prices, cutoff)


def append_decisions(decisions: pd.DataFrame, path: Path = DECISION_PATH) -> dict:
    """Append new decision IDs while preserving the first captured snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=DECISION_FIELDS)
    before = len(existing)
    if existing.empty:
        combined = decisions.copy()
    elif decisions.empty:
        combined = existing.copy()
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.*",
                category=FutureWarning,
            )
            combined = pd.concat([existing, decisions], ignore_index=True, sort=False)
    combined = combined.drop_duplicates("decision_id", keep="first")
    combined = combined.sort_values(["signal_date", "market", "timeframe", "symbol"])
    combined.to_parquet(path, index=False, compression="zstd")
    return {"before": before, "added": len(combined) - before, "rows": len(combined)}


def cmo_annotations(decisions: pd.DataFrame, calculated_at: datetime | None = None) -> pd.DataFrame:
    """Build versioned weekly-momentum annotations without rewriting decisions."""
    fields = [
        "weekly_cmo_14",
        "weekly_cmo_ema_10",
        "weekly_cmo_ema_change",
        "weekly_cmo_ema_acceleration",
        "weekly_cmo_ema_rising",
        "weekly_cmo_ema_rising_trigger",
        "weekly_cmo_ema_accelerating",
        "weekly_cmo_ema_accelerating_trigger",
        "weekly_cmo_policy",
        "weekly_vbsm_nres1",
        "weekly_vbsm_nres2",
        "weekly_vbsm_pvi_nvi",
        "weekly_vbsm_sma_25",
        "weekly_vbsm_gap",
        "weekly_vbsm_gap_change",
        "weekly_vbsm_above",
        "weekly_vbsm_cross_above",
        "weekly_vbsm_policy",
    ]
    selected = decisions[
        decisions["timeframe"].eq(ACTIVE_TIMEFRAME)
        & decisions["weekly_cmo_ema_10"].notna()
    ][["decision_id", "signal_date", *fields]].copy()
    if selected.empty:
        return pd.DataFrame(
            columns=[
                "annotation_id",
                "decision_id",
                "annotation_version",
                "calculated_at_utc",
                "signal_date",
                *fields,
            ]
        )
    selected.insert(
        0,
        "annotation_id",
        selected["decision_id"].astype(str) + "_weekly_momentum_v2",
    )
    selected.insert(2, "annotation_version", "weekly_momentum_v2")
    selected.insert(
        3,
        "calculated_at_utc",
        (calculated_at or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
    )
    return selected.reset_index(drop=True)


def append_annotations(
    annotations: pd.DataFrame,
    path: Path = ANNOTATION_PATH,
) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    before = len(existing)
    if existing.empty:
        combined = annotations.copy()
    elif annotations.empty:
        combined = existing.copy()
    else:
        combined = pd.concat([existing, annotations], ignore_index=True, sort=False)
    if not combined.empty:
        combined = combined.drop_duplicates("annotation_id", keep="first")
        combined = combined.sort_values(["signal_date", "decision_id"])
    combined.to_parquet(path, index=False, compression="zstd")
    return {"before": before, "added": len(combined) - before, "rows": len(combined)}


def capture_candidate_reports(
    timeframes: tuple[str, ...] = (ACTIVE_TIMEFRAME,),
) -> dict:
    results: dict[str, object] = {}
    for market, path in (("IN", INDIA_CANDIDATE_PATH), ("US", US_CANDIDATE_PATH)):
        if not path.exists():
            results[market] = {"status": "missing", "path": str(path)}
            continue
        candidates = pd.read_csv(path)
        candidates = active_timeframe_rows(candidates, timeframes)
        candidates = _attach_missing_diagnostics(market, candidates)
        decisions = normalize_decisions(market, candidates)
        results[market] = {
            "decisions": append_decisions(decisions),
            "annotations": append_annotations(cmo_annotations(decisions)),
        }
    return results


def calculate_outcomes(
    decisions: pd.DataFrame,
    bars: pd.DataFrame,
    benchmark_symbol: str,
    observed_at: datetime | None = None,
) -> pd.DataFrame:
    """Calculate one as-of snapshot per entered decision."""
    if decisions.empty or bars.empty:
        return pd.DataFrame()
    prices = bars.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values(["symbol", "date"])
    groups = {symbol: group.reset_index(drop=True) for symbol, group in prices.groupby("symbol")}
    benchmark = groups.get(benchmark_symbol, pd.DataFrame())
    observed = (observed_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    rows: list[dict[str, object]] = []
    for row in decisions.itertuples(index=False):
        security = groups.get(str(row.symbol), pd.DataFrame())
        if security.empty:
            continue
        window = security[security["date"].ge(pd.Timestamp(row.planned_entry_date))].copy()
        if window.empty:
            continue
        entry = window.iloc[0]
        latest = window.iloc[-1]
        entry_price = float(entry["open"])
        if not np.isfinite(entry_price) or entry_price <= 0:
            continue
        outcome = {
            "outcome_id": f"{row.decision_id}_{pd.Timestamp(latest['date']):%Y%m%d}",
            "decision_id": row.decision_id,
            "observed_at_utc": observed,
            "asof_date": pd.Timestamp(latest["date"]).normalize(),
            "actual_entry_date": pd.Timestamp(entry["date"]).normalize(),
            "entry_open": entry_price,
            "entry_gap": entry_price / float(row.signal_close) - 1
            if pd.notna(row.signal_close) and float(row.signal_close) > 0
            else np.nan,
            "opening_gate_pass": abs(entry_price / float(row.signal_close) - 1) <= 0.02
            if pd.notna(row.signal_close) and float(row.signal_close) > 0
            else pd.NA,
            "sessions_elapsed": len(window),
            "latest_close": float(latest["close"]),
            "return_since_entry": float(latest["close"]) / entry_price - 1,
            "max_favorable_excursion": float(window["high"].max()) / entry_price - 1,
            "max_adverse_excursion": float(window["low"].min()) / entry_price - 1,
        }
        if benchmark.empty:
            benchmark_window = benchmark.copy()
        else:
            benchmark_window = benchmark[
                benchmark["date"].between(entry["date"], latest["date"])
            ].copy()
        if not benchmark_window.empty:
            benchmark_entry = float(benchmark_window.iloc[0]["open"])
            benchmark_return = float(benchmark_window.iloc[-1]["close"]) / benchmark_entry - 1
        else:
            benchmark_entry = np.nan
            benchmark_return = np.nan
        outcome["benchmark_symbol"] = benchmark_symbol
        outcome["benchmark_return_since_entry"] = benchmark_return
        outcome["excess_return_since_entry"] = outcome["return_since_entry"] - benchmark_return
        for horizon in HORIZONS:
            if len(window) >= horizon:
                security_return = float(window.iloc[horizon - 1]["close"]) / entry_price - 1
                outcome[f"return_{horizon}s"] = security_return
                if len(benchmark_window) >= horizon and np.isfinite(benchmark_entry):
                    benchmark_horizon = (
                        float(benchmark_window.iloc[horizon - 1]["close"]) / benchmark_entry - 1
                    )
                    outcome[f"benchmark_return_{horizon}s"] = benchmark_horizon
                    outcome[f"excess_return_{horizon}s"] = security_return - benchmark_horizon
                else:
                    outcome[f"benchmark_return_{horizon}s"] = np.nan
                    outcome[f"excess_return_{horizon}s"] = np.nan
            else:
                outcome[f"return_{horizon}s"] = np.nan
                outcome[f"benchmark_return_{horizon}s"] = np.nan
                outcome[f"excess_return_{horizon}s"] = np.nan
        rows.append(outcome)
    return pd.DataFrame(rows)


def append_outcomes(outcomes: pd.DataFrame, path: Path = OUTCOME_PATH) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    before = len(existing)
    if existing.empty:
        combined = outcomes.copy()
    elif outcomes.empty:
        combined = existing.copy()
    else:
        combined = pd.concat([existing, outcomes], ignore_index=True, sort=False)
    if not combined.empty:
        combined = combined.drop_duplicates("outcome_id", keep="first")
        combined = combined.sort_values(["asof_date", "decision_id"])
    combined.to_parquet(path, index=False, compression="zstd")
    return {"before": before, "added": len(combined) - before, "rows": len(combined)}


def refresh_outcomes(timeframes: tuple[str, ...] | None = None) -> dict:
    if not DECISION_PATH.exists():
        return {"status": "no_decisions", "rows": 0}
    decisions = pd.read_parquet(DECISION_PATH)
    decisions = active_timeframe_rows(decisions, timeframes)
    results: dict[str, object] = {}
    snapshots = []
    india_prices: pd.DataFrame | None = None
    for market, group in decisions.groupby("market"):
        benchmark = BENCHMARKS[market]
        symbols = set(group["symbol"].astype(str)) | {benchmark}
        start = pd.Timestamp(group["planned_entry_date"].min())
        if market == "IN":
            if india_prices is None:
                india_prices = india_research.load_prices()
            bars = india_prices[
                india_prices["symbol"].isin(symbols)
                & pd.to_datetime(india_prices["date"]).ge(start)
            ].copy()
        else:
            bars = _load_us_bars(symbols, start)
        outcome = calculate_outcomes(group, bars, benchmark)
        snapshots.append(outcome)
        results[market] = {"decisions": len(group), "outcomes": len(outcome)}
    combined = pd.concat(snapshots, ignore_index=True, sort=False) if snapshots else pd.DataFrame()
    results["append"] = append_outcomes(combined)
    return results


def latest_results(
    decision_path: Path = DECISION_PATH,
    outcome_path: Path = OUTCOME_PATH,
    annotation_path: Path = ANNOTATION_PATH,
) -> pd.DataFrame:
    if not decision_path.exists():
        return pd.DataFrame(columns=DECISION_FIELDS)
    decisions = pd.read_parquet(decision_path)
    frame = decisions.copy()
    if outcome_path.exists():
        outcomes = pd.read_parquet(outcome_path)
        if not outcomes.empty:
            latest = outcomes.sort_values(["decision_id", "asof_date"]).groupby(
                "decision_id", as_index=False
            ).tail(1)
            frame = frame.merge(latest, on="decision_id", how="left", validate="one_to_one")
    if annotation_path.exists():
        annotations = pd.read_parquet(annotation_path)
        if not annotations.empty:
            latest_annotations = annotations.sort_values(
                ["decision_id", "calculated_at_utc"]
            ).groupby("decision_id", as_index=False).tail(1)
            cmo_fields = [
                "weekly_cmo_14",
                "weekly_cmo_ema_10",
                "weekly_cmo_ema_change",
                "weekly_cmo_ema_acceleration",
                "weekly_cmo_ema_rising",
                "weekly_cmo_ema_rising_trigger",
                "weekly_cmo_ema_accelerating",
                "weekly_cmo_ema_accelerating_trigger",
                "weekly_cmo_policy",
                "weekly_vbsm_nres1",
                "weekly_vbsm_nres2",
                "weekly_vbsm_pvi_nvi",
                "weekly_vbsm_sma_25",
                "weekly_vbsm_gap",
                "weekly_vbsm_gap_change",
                "weekly_vbsm_above",
                "weekly_vbsm_cross_above",
                "weekly_vbsm_policy",
            ]
            for field in cmo_fields:
                if field not in latest_annotations:
                    latest_annotations[field] = pd.NA
            frame = frame.merge(
                latest_annotations[["decision_id", *cmo_fields]],
                on="decision_id",
                how="left",
                suffixes=("", "_annotation"),
                validate="one_to_one",
            )
            for field in cmo_fields:
                annotation_field = f"{field}_annotation"
                if field in frame:
                    frame[field] = frame[annotation_field].combine_first(frame[field])
                else:
                    frame[field] = frame[annotation_field]
                frame = frame.drop(columns=annotation_field)
    for field in DECISION_FIELDS:
        if field not in frame:
            frame[field] = pd.NA
    return frame


def _format_number(value: object, digits: int = 2, suffix: str = "") -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}{suffix}"


def _format_percent(value: object, digits: int = 1) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def _format_multiple(value: object) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):.2f}×"


def render_html(frame: pd.DataFrame, path: Path = HTML_PATH) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = frame.copy()
    if not data.empty:
        data["opportunity_miss"] = (
            ~data["presented"].map(_as_bool)
            & data.get("return_since_entry", pd.Series(np.nan, index=data.index)).ge(
                OPPORTUNITY_MISS_RETURN
            )
        )
        data = data.sort_values(
            ["signal_date", "opportunity_miss", "presented", "model_rank_score"],
            ascending=[False, False, False, False],
        )
    else:
        data["opportunity_miss"] = pd.Series(dtype=bool)

    active = data[
        data.get("timeframe", pd.Series(index=data.index, dtype=str)).eq(ACTIVE_TIMEFRAME)
    ]
    presented_count = int(active.get("presented", pd.Series(dtype=bool)).map(_as_bool).sum())
    near_miss_count = int(active.get("decision_stage", pd.Series(dtype=str)).eq("near_miss_budget").sum())
    tracked_count = int(active.get("actual_entry_date", pd.Series(dtype="datetime64[ns]")).notna().sum())
    miss_count = int(active["opportunity_miss"].sum())
    rows = []
    for row in data.itertuples(index=False):
        symbol = html.escape(str(row.symbol))
        market = str(row.market)
        tradingview = (
            f"https://www.tradingview.com/chart/?symbol=NSE%3A{symbol}"
            if market == "IN"
            else f"https://www.tradingview.com/chart/?symbol={quote(str(row.exchange))}%3A{symbol}"
        )
        result_class = "miss" if bool(row.opportunity_miss) else "presented" if bool(row.presented) else ""
        rows.append(
            f"""<tr class="{result_class}" data-market="{market}" data-timeframe="{html.escape(str(row.timeframe))}" data-stage="{html.escape(str(row.decision_stage))}">
            <td>{pd.Timestamp(row.signal_date):%Y-%m-%d}</td>
            <td>{market}</td><td>{html.escape(str(row.timeframe))}</td>
            <td><a href="{tradingview}" target="_blank" rel="noopener">{symbol}</a></td>
            <td>{'Presented' if bool(row.presented) else html.escape(str(row.decision_stage).replace('_', ' '))}</td>
            <td>{_format_number(row.model_rank_score, 1)}</td>
            <td>{html.escape(str(row.twin_ha_status)) if pd.notna(row.twin_ha_status) else '—'}</td>
            <td>{_format_number(row.weekly_cmo_ema_10, 1)}</td>
            <td>{'Rising' if _as_bool(row.weekly_cmo_ema_rising) else 'Falling' if pd.notna(row.weekly_cmo_ema_rising) else '—'}</td>
            <td>{_format_number(row.weekly_cmo_ema_acceleration, 2)}</td>
            <td>{_format_number(row.weekly_vbsm_gap, 2)}</td>
            <td>{'Above' if _as_bool(row.weekly_vbsm_above) else 'Below' if pd.notna(row.weekly_vbsm_above) else '—'}</td>
            <td>{_format_multiple(row.volume_ratio_5_prior)}</td>
            <td>{_format_multiple(row.delivery_qty_ratio_20_prior)}</td>
            <td>{_format_percent(row.return_1d)}</td>
            <td>{_format_number(row.close_location_value, 2)}</td>
            <td>{_format_multiple(row.true_range_ratio_20_prior)}</td>
            <td>{_format_percent(getattr(row, 'entry_gap', np.nan))}</td>
            <td>{_format_percent(getattr(row, 'return_since_entry', np.nan))}</td>
            <td>{_format_percent(getattr(row, 'excess_return_since_entry', np.nan))}</td>
            <td>{_format_percent(getattr(row, 'max_favorable_excursion', np.nan))}</td>
            <td>{_format_percent(getattr(row, 'max_adverse_excursion', np.nan))}</td>
            </tr>"""
        )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recommendation forward test</title>
<style>
:root{{--bg:#f7f7f4;--card:#fff;--ink:#121212;--muted:#686861;--line:#deded7;--blue:#1c5cab;--green:#0a7d0a;--amber:#9a5b00}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0d0d0d;--card:#1a1a19;--ink:#f7f7f4;--muted:#9b9a92;--line:#33332f;--blue:#67a7f2;--green:#54c654;--amber:#f0b83e}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,sans-serif}}
.wrap{{max-width:1500px;margin:auto;padding:18px 20px 60px}}nav{{display:flex;gap:18px;border-bottom:1px solid var(--line);padding:0 0 10px;margin-bottom:22px;flex-wrap:wrap}}nav a{{color:var(--muted);text-decoration:none;font-weight:600}}nav a.on{{color:var(--ink);border-bottom:2px solid var(--blue)}}
h1{{font-size:23px;margin:0}}.sub{{color:var(--muted);margin:3px 0 20px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}}.card b{{font-size:24px;display:block}}.card span{{color:var(--muted);font-size:12px}}
.controls{{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}}button,input{{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 10px}}button.on{{background:var(--blue);color:white}}input{{min-width:220px}}.table{{overflow:auto;max-height:72vh;background:var(--card);border:1px solid var(--line);border-radius:12px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:8px 9px;white-space:nowrap;border-bottom:1px solid var(--line);text-align:right}}th{{position:sticky;top:0;background:var(--card);color:var(--muted);font-size:10px;text-transform:uppercase}}th:nth-child(-n+5),td:nth-child(-n+5){{text-align:left}}td a{{color:var(--blue);font-weight:700;text-decoration:none}}tr.presented{{box-shadow:inset 3px 0 var(--green)}}tr.miss{{background:color-mix(in srgb,var(--amber) 12%,transparent);box-shadow:inset 3px 0 var(--amber)}}.note{{color:var(--muted);font-size:12px;margin-top:14px;max-width:900px}}
@media(max-width:700px){{.cards{{grid-template-columns:repeat(2,1fr)}}.wrap{{padding:14px 10px 40px}}}}
</style></head><body><div class="wrap">
<nav><a href="dashboard.html">Weekly</a><a href="daily.html">Daily</a><a href="market.html">Market</a><a href="sectors.html">Sectors</a><a href="recommendations.html" class="on">Forward Test</a></nav>
<h1>Recommendation forward test</h1><div class="sub">Immutable decisions and point-in-time outcome snapshots · rendered {generated}</div>
<section class="cards"><div class="card"><b>{presented_count}</b><span>Presented decisions</span></div><div class="card"><b>{near_miss_count}</b><span>Budget near misses</span></div><div class="card"><b>{tracked_count}</b><span>Entered forward tests</span></div><div class="card"><b>{miss_count}</b><span>Non-presented returns ≥ 10%</span></div></section>
<div class="controls"><button class="on" data-filter="weekly">Weekly</button><button data-filter="IN">India</button><button data-filter="US">US</button><button data-filter="miss">Opportunity misses</button><button data-filter="daily">Daily archive</button><button data-filter="all">All history</button><input id="search" placeholder="Search symbol or stage"></div>
<div class="table"><table id="results"><thead><tr><th>Signal</th><th>Market</th><th>Frame</th><th>Symbol</th><th>Decision</th><th>Score</th><th>Twin HA</th><th>CMO EMA</th><th>CMO slope</th><th>CMO accel.</th><th>VBSM gap</th><th>VBSM state</th><th>Vol / 5d</th><th>Delivery / 20d</th><th>Signal day</th><th>Close loc.</th><th>TR / 20d</th><th>Entry gap</th><th>Return</th><th>Excess</th><th>MFE</th><th>MAE</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="note">Diagnostics use only bars available on the signal date. Their policy weight is zero until forward samples support a predeclared rule. Returns use the first session open on or after the planned entry date. “Opportunity miss” marks a non-presented row with a forward return of at least 10%; it is descriptive, not a recommendation.</p>
</div><script>
const buttons=[...document.querySelectorAll('button[data-filter]')], rows=[...document.querySelectorAll('tbody tr')], search=document.querySelector('#search');let filter='weekly';
function apply(){{const q=search.value.trim().toLowerCase();rows.forEach(r=>{{const match=filter==='all'||r.dataset.market===filter||r.dataset.timeframe===filter||(filter==='miss'&&r.classList.contains('miss')&&r.dataset.timeframe==='weekly');r.hidden=!match||!r.textContent.toLowerCase().includes(q)}})}}
buttons.forEach(b=>b.onclick=()=>{{buttons.forEach(x=>x.classList.remove('on'));b.classList.add('on');filter=b.dataset.filter;apply()}});search.oninput=apply;apply();
</script></body></html>"""
    path.write_text(document)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.drop(columns=["snapshot_json"], errors="ignore").to_csv(SUMMARY_PATH, index=False)
    return {
        "rows": len(data),
        "presented": presented_count,
        "near_misses": near_miss_count,
        "opportunity_misses": miss_count,
        "path": str(path.resolve()),
    }


def run(
    capture: bool = True,
    outcomes: bool = True,
    capture_timeframes: tuple[str, ...] = (ACTIVE_TIMEFRAME,),
    outcome_timeframes: tuple[str, ...] | None = None,
) -> dict:
    payload: dict[str, object] = {}
    if capture:
        payload["capture"] = capture_candidate_reports(capture_timeframes)
    if outcomes:
        payload["outcomes"] = refresh_outcomes(outcome_timeframes)
    payload["render"] = render_html(latest_results())
    print(json.dumps(payload, indent=2, default=str))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-only", action="store_true")
    arguments = parser.parse_args()
    run(capture=not arguments.render_only, outcomes=not arguments.render_only)
