"""
Lightweight historical validation for Explosive Move Radar (rules only, no ML).

Walks recent daily bars, evaluates the radar as-of each sample date (price path only
unless you pass time-filtered articles), then measures simple forward max gain / drawdown.

Usage (CLI): python scripts/validate_explosive_radar.py --tickers NVDA,AMD --output report.json
"""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.models import Article, StockScore
from app.services.explosive_radar import (
    _articles_for_ticker,
    compute_explosive_radar_row,
    load_explosive_radar_weights,
)
from app.services.explosive_radar_data import DailyBarSeries, fetch_daily_bars_for_radar, slice_bars_at_end


@dataclass
class SignalEvent:
    ticker: str
    signal_index: int
    signal_date: str | None
    jump_score: int
    catalyst_score: int
    risk_score: int
    confidence_score: int
    ranked_opportunity_score: int
    setup_type: str
    max_fwd_return_1d: float | None
    max_fwd_return_3d: float | None
    max_fwd_return_5d: float | None
    max_drawdown_fwd_5d: float | None


def forward_outcomes_from_index(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    signal_idx: int,
) -> dict[str, float | None]:
    """
    Forward outcomes from signal close (signal_idx inclusive as the signal bar).
    Max gain uses path high vs signal close; drawdown uses path low vs signal close.
    """
    if signal_idx < 0 or signal_idx >= len(closes) - 1:
        return {
            "max_fwd_return_1d": None,
            "max_fwd_return_3d": None,
            "max_fwd_return_5d": None,
            "max_drawdown_fwd_5d": None,
        }
    base = closes[signal_idx]
    if base <= 0:
        return {
            "max_fwd_return_1d": None,
            "max_fwd_return_3d": None,
            "max_fwd_return_5d": None,
            "max_drawdown_fwd_5d": None,
        }

    def max_gain(horizon: int) -> float | None:
        end = min(len(closes) - 1, signal_idx + horizon)
        if signal_idx >= end:
            return None
        peak = max(highs[signal_idx + 1 : end + 1], default=base)
        return (peak - base) / base

    def max_dd(horizon: int) -> float | None:
        end = min(len(closes) - 1, signal_idx + horizon)
        if signal_idx >= end:
            return None
        trough = min(lows[signal_idx + 1 : end + 1], default=base)
        return (trough - base) / base

    return {
        "max_fwd_return_1d": max_gain(1),
        "max_fwd_return_3d": max_gain(3),
        "max_fwd_return_5d": max_gain(5),
        "max_drawdown_fwd_5d": max_dd(5),
    }


def _liquidity_from_slice(volumes: list[float]) -> float:
    recent = [v for v in volumes[-10:] if v > 0]
    if not recent:
        return 0.35
    avg = sum(recent) / len(recent)
    return round(min(1.0, avg / 30_000_000), 3)


def run_historical_validation(
    tickers: list[str],
    *,
    finnhub_enabled: bool = False,
    finnhub_api_key: str = "",
    min_bars: int = 30,
    step: int = 5,
    min_jump_signal: int = 60,
    max_signals_per_ticker: int = 50,
    articles: list[Article] | None = None,
    as_of_filter_articles: bool = True,
) -> dict[str, Any]:
    """
    For each ticker, fetch full OHLCV, sample historical indices, compute radar row on sliced
    bars, record forward returns when jump >= min_jump_signal.

    If as_of_filter_articles and articles provided, only articles on/before the bar date count.
    """
    weights = load_explosive_radar_weights()
    events: list[SignalEvent] = []
    art = articles or []

    with httpx.Client(timeout=22.0, follow_redirects=True) as client:
        for raw in tickers:
            sym = raw.strip().upper()
            if not sym:
                continue
            full = fetch_daily_bars_for_radar(
                sym,
                finnhub_enabled=finnhub_enabled,
                finnhub_api_key=finnhub_api_key,
                client=client,
            )
            if not full or len(full.closes) < min_bars + 6:
                continue
            n = len(full.closes)
            count = 0
            for i in range(min_bars, n - 6, step):
                if count >= max_signals_per_ticker:
                    break
                sliced = slice_bars_at_end(full, i + 1)
                if len(sliced.closes) < min_bars:
                    continue
                sig_date = sliced.dates_iso[-1] if sliced.dates_iso else None
                as_of = None
                if sig_date:
                    try:
                        as_of = datetime.strptime(sig_date, "%Y-%m-%d").replace(
                            hour=23, minute=59, second=59, tzinfo=timezone.utc
                        )
                    except ValueError:
                        as_of = None

                if as_of_filter_articles and as_of is not None:
                    linked = _articles_for_ticker(art, sym, max_age_days=365, as_of=as_of)
                else:
                    linked = []

                last_c = sliced.closes[-1]
                prev_c = sliced.closes[-2] if len(sliced.closes) >= 2 else last_c
                day_ch = (last_c - prev_c) / prev_c if prev_c > 0 else 0.0
                mom_5 = 0.0
                if len(sliced.closes) >= 6:
                    p5 = sliced.closes[-6]
                    mom_5 = (last_c - p5) / p5 if p5 > 0 else 0.0
                liq = _liquidity_from_slice(sliced.volumes)
                stock = StockScore(
                    ticker=sym,
                    price=last_c,
                    day_change=round(day_ch, 4),
                    score=0.0,
                    confidence=0.5,
                    momentum=round(mom_5, 4),
                    liquidity=liq,
                    valuation_sanity=0.6,
                    sentiment=0.0,
                    relevance=0.0,
                    explanation="validation-synthetic",
                    updated_at=datetime.now(timezone.utc),
                )
                row = compute_explosive_radar_row(sym, stock, sliced, linked, weights)
                if row["jumpScore"] < min_jump_signal:
                    continue
                # Forward path must use the full series so post-signal bars exist.
                fo = forward_outcomes_from_index(full.highs, full.lows, full.closes, i)
                events.append(
                    SignalEvent(
                        ticker=sym,
                        signal_index=i,
                        signal_date=sig_date,
                        jump_score=row["jumpScore"],
                        catalyst_score=row["catalystScore"],
                        risk_score=row["riskScore"],
                        confidence_score=row["confidenceScore"],
                        ranked_opportunity_score=row["rankedOpportunityScore"],
                        setup_type=row["setupType"],
                        max_fwd_return_1d=fo["max_fwd_return_1d"],
                        max_fwd_return_3d=fo["max_fwd_return_3d"],
                        max_fwd_return_5d=fo["max_fwd_return_5d"],
                        max_drawdown_fwd_5d=fo["max_drawdown_fwd_5d"],
                    )
                )
                count += 1

    return aggregate_validation(events)


def aggregate_validation(events: list[SignalEvent]) -> dict[str, Any]:
    """Aggregate diagnostics + per-event list for export."""
    if not events:
        return {
            "eventCount": 0,
            "summary": {},
            "bySetupType": {},
            "events": [],
        }

    def mean(xs: list[float]) -> float | None:
        return round(statistics.mean(xs), 6) if xs else None

    jumps = sorted(e.jump_score for e in events)
    cut = max(0, int(len(jumps) * 0.9) - 1)
    top_decile_threshold = jumps[cut] if jumps else 0
    top_decile = [e for e in events if e.jump_score >= top_decile_threshold]
    high_jump = [e for e in events if e.jump_score >= 75]

    def hit_rate(es: list[SignalEvent], thresh: float = 0.03) -> float | None:
        gains = [e.max_fwd_return_5d for e in es if e.max_fwd_return_5d is not None]
        if not gains:
            return None
        return round(sum(1 for g in gains if g >= thresh) / len(gains), 4)

    top5 = [e.max_fwd_return_5d for e in top_decile if e.max_fwd_return_5d is not None]
    hi5 = [e.max_fwd_return_5d for e in high_jump if e.max_fwd_return_5d is not None]

    winners = [e for e in events if e.max_fwd_return_5d is not None and e.max_fwd_return_5d >= 0.03]
    losers = [e for e in events if e.max_fwd_return_5d is not None and e.max_fwd_return_5d < 0.03]

    by_setup: dict[str, dict[str, Any]] = {}
    for e in events:
        by_setup.setdefault(e.setup_type, {"n": 0, "hits": 0, "sum5d": 0.0, "n5": 0})
        by_setup[e.setup_type]["n"] += 1
        if e.max_fwd_return_5d is not None:
            by_setup[e.setup_type]["n5"] += 1
            by_setup[e.setup_type]["sum5d"] += e.max_fwd_return_5d
            if e.max_fwd_return_5d >= 0.03:
                by_setup[e.setup_type]["hits"] += 1

    for st, d in by_setup.items():
        n5 = d["n5"]
        d["hitRate5d_3pct"] = round(d["hits"] / n5, 4) if n5 else None
        d["avgMaxGain5d"] = round(d["sum5d"] / n5, 6) if n5 else None
        d["signals"] = d["n"]
        del d["hits"]
        del d["sum5d"]
        del d["n5"]
        del d["n"]

    out_events = [
        {
            "ticker": e.ticker,
            "signalDate": e.signal_date,
            "jumpScore": e.jump_score,
            "catalystScore": e.catalyst_score,
            "riskScore": e.risk_score,
            "confidenceScore": e.confidence_score,
            "rankedOpportunityScore": e.ranked_opportunity_score,
            "setupType": e.setup_type,
            "maxFwdReturn1d": e.max_fwd_return_1d,
            "maxFwdReturn3d": e.max_fwd_return_3d,
            "maxFwdReturn5d": e.max_fwd_return_5d,
            "maxDrawdownFwd5d": e.max_drawdown_fwd_5d,
        }
        for e in events
    ]

    return {
        "eventCount": len(events),
        "summary": {
            "topDecileJumpThreshold": top_decile_threshold,
            "avgMaxFwdReturn5d_topDecileJump": mean(top5),
            "hitRate5d_3pct_jumpGte75": hit_rate(high_jump),
            "avgRiskScore_winnersVsLosers": {
                "winners": mean([float(e.risk_score) for e in winners]) if winners else None,
                "losers": mean([float(e.risk_score) for e in losers]) if losers else None,
            },
            "avgConfidenceScore_winnersVsLosers": {
                "winners": mean([float(e.confidence_score) for e in winners]) if winners else None,
                "losers": mean([float(e.confidence_score) for e in losers]) if losers else None,
            },
        },
        "bySetupType": by_setup,
        "events": out_events,
    }


def export_validation_csv(report: dict[str, Any], path: Path) -> None:
    evs = report.get("events") or []
    if not evs:
        path.write_text("", encoding="utf-8")
        return
    keys = list(evs[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for row in evs:
            w.writerow(row)


def export_validation_json(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
