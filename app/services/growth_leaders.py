"""Growth Leaders screen — long-horizon companion to the trade feed.

Surfaces stocks showing the multi-quarter signature that often precedes
multi-bagger runs: sustained price strength, trend alignment with the major
moving averages, proximity to the 52-week high, outperformance vs the broad
market, and recent volume pickup.

NOT a predictor — most flagged names won't deliver a 3x. The idea is to
surface the *signature*, not picks. v1 uses only price-history features;
future iterations should fold in earnings acceleration + analyst estimate
revisions when those data sources are wired up.
"""
from __future__ import annotations

from typing import Any, Iterable
import statistics

from app.services.market_data import fetch_yfinance_ohlc_batch


_DEFAULT_WEIGHTS = {
    "return_6mo": 0.35,
    "rs_vs_spy": 0.20,
    "trend_alignment": 0.20,
    "proximity_to_high": 0.15,
    "volume_confirm": 0.10,
}


def _safe_pct(numer: float, denom: float) -> float | None:
    if denom is None or denom == 0:
        return None
    try:
        return (numer - denom) / denom
    except (TypeError, ZeroDivisionError):
        return None


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _compute_metrics(bars: list[dict]) -> dict[str, Any] | None:
    """Per-ticker metrics from daily bars (oldest→newest). Returns None if
    insufficient history (need at least ~6 months to compute return_6mo)."""
    if not bars or len(bars) < 130:
        return None
    closes = [float(b["close"]) for b in bars]
    volumes = [float(b.get("volume") or 0.0) for b in bars]
    last = closes[-1]

    n_6mo = min(126, len(closes) - 1)
    n_12mo = min(252, len(closes) - 1)
    ret_6mo = _safe_pct(last, closes[-n_6mo - 1])
    ret_12mo = _safe_pct(last, closes[-n_12mo - 1]) if len(closes) > n_12mo else None

    window = closes[-min(252, len(closes)):]
    high_252 = max(window)
    low_252 = min(window)

    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)

    dist_high = (high_252 - last) / high_252 if high_252 else None
    dist_low = (last - low_252) / low_252 if low_252 else None

    vol_20 = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else None
    vol_60 = statistics.mean(volumes[-60:]) if len(volumes) >= 60 else None
    vol_ratio = (vol_20 / vol_60) if (vol_20 and vol_60) else None

    return {
        "lastClose": last,
        "return_6mo": ret_6mo,
        "return_12mo": ret_12mo,
        "high_252": high_252,
        "low_252": low_252,
        "sma50": sma50,
        "sma200": sma200,
        "dist_from_high": dist_high,
        "dist_from_low": dist_low,
        "vol_ratio_20_60": vol_ratio,
    }


def _trend_alignment(metrics: dict[str, Any]) -> float:
    """0..1: price > 200d MA worth 0.5; 50d > 200d MA worth 0.5."""
    last = metrics.get("lastClose")
    sma50 = metrics.get("sma50")
    sma200 = metrics.get("sma200")
    score = 0.0
    if last is not None and sma200 is not None and sma200 > 0 and last > sma200:
        score += 0.5
    if sma50 is not None and sma200 is not None and sma50 > sma200:
        score += 0.5
    return score


def _normalize_return(r: float | None, target: float = 0.50) -> float:
    """0..1; target return (default 50%) reaches 1.0; negative or missing → 0."""
    if r is None or r <= 0:
        return 0.0
    return min(1.0, r / target)


def _normalize_proximity(d: float | None) -> float:
    """0..1; at 52w high → 1.0, 25%+ below high → 0."""
    if d is None:
        return 0.0
    if d < 0:
        d = 0.0
    return max(0.0, 1.0 - (d / 0.25))


def _normalize_rs(stock_r: float | None, spy_r: float | None) -> float:
    """0..1; matching SPY → 0.5, +30% above → 1.0, -30% below → 0."""
    if stock_r is None or spy_r is None:
        return 0.5
    diff = stock_r - spy_r
    return max(0.0, min(1.0, 0.5 + (diff / 0.6)))


def _normalize_volume(v: float | None) -> float:
    """0..1; 20d/60d ratio: <0.7 → 0, 1.0 → 0.5 ramp, 1.5+ → 1.0."""
    if v is None:
        return 0.5
    if v <= 0.7:
        return 0.0
    if v >= 1.5:
        return 1.0
    return (v - 0.7) / 0.8


def _compute_growth_score(
    metrics: dict[str, Any],
    spy_return_6mo: float | None,
    weights: dict[str, float] | None = None,
) -> tuple[float, dict[str, float]]:
    w = weights or _DEFAULT_WEIGHTS
    components = {
        "return_6mo": _normalize_return(metrics.get("return_6mo")),
        "rs_vs_spy": _normalize_rs(metrics.get("return_6mo"), spy_return_6mo),
        "trend_alignment": _trend_alignment(metrics),
        "proximity_to_high": _normalize_proximity(metrics.get("dist_from_high")),
        "volume_confirm": _normalize_volume(metrics.get("vol_ratio_20_60")),
    }
    score = sum(components[k] * w.get(k, 0.0) for k in components)
    return score, components


def _row_field(s: Any, key: str) -> Any:
    if isinstance(s, dict):
        return s.get(key)
    return getattr(s, key, None)


def build_growth_leaders(
    stocks: Iterable[Any],
    *,
    limit: int = 20,
    bars_loader=None,
) -> dict[str, Any]:
    """Rank a stock universe by growth-leader signature.

    Args:
        stocks: iterable of dataclass-likes or dicts with at least .ticker
        limit: top-N to return (default 20)
        bars_loader: injectable for testing; signature (tickers) -> {ticker: bars}
    """
    universe: list[dict[str, Any]] = []
    tickers: list[str] = []
    for s in stocks:
        ticker = _row_field(s, "ticker")
        if not ticker:
            continue
        ticker = str(ticker).upper()
        if ticker in [u["ticker"] for u in universe]:
            continue
        tickers.append(ticker)
        universe.append({
            "ticker": ticker,
            "company": _row_field(s, "company"),
            "sector": _row_field(s, "sector"),
            "modelScore": _row_field(s, "score"),
        })

    if not tickers:
        return {"items": [], "totalScanned": 0, "weights": _DEFAULT_WEIGHTS}

    loader = bars_loader or (
        lambda ts: fetch_yfinance_ohlc_batch(ts, period="1y", min_rows=130)
    )
    fetch_list = list(dict.fromkeys(tickers + ["SPY"]))
    bars_by_ticker = loader(fetch_list) or {}
    spy_bars = bars_by_ticker.get("SPY")
    spy_metrics = _compute_metrics(spy_bars) if spy_bars else None
    spy_r6 = spy_metrics.get("return_6mo") if spy_metrics else None

    rows: list[dict[str, Any]] = []
    for u in universe:
        bars = bars_by_ticker.get(u["ticker"])
        if not bars:
            continue
        m = _compute_metrics(bars)
        if not m:
            continue
        score, components = _compute_growth_score(m, spy_r6)
        rows.append({
            **u,
            "growthScore": round(score, 4),
            "components": {k: round(v, 3) for k, v in components.items()},
            "metrics": {
                "return6mo": round(m["return_6mo"], 4) if m.get("return_6mo") is not None else None,
                "return12mo": round(m["return_12mo"], 4) if m.get("return_12mo") is not None else None,
                "distFromHigh": round(m["dist_from_high"], 4) if m.get("dist_from_high") is not None else None,
                "distFromLow": round(m["dist_from_low"], 4) if m.get("dist_from_low") is not None else None,
                "sma50": round(m["sma50"], 2) if m.get("sma50") is not None else None,
                "sma200": round(m["sma200"], 2) if m.get("sma200") is not None else None,
                "lastClose": round(m["lastClose"], 2),
                "vol20over60": round(m["vol_ratio_20_60"], 2) if m.get("vol_ratio_20_60") is not None else None,
                "high52w": round(m["high_252"], 2),
                "low52w": round(m["low_252"], 2),
            },
        })

    rows.sort(key=lambda r: r["growthScore"], reverse=True)
    if limit and limit > 0:
        rows = rows[:limit]

    return {
        "items": rows,
        "totalScanned": len(universe),
        "spyReturn6mo": round(spy_r6, 4) if spy_r6 is not None else None,
        "weights": _DEFAULT_WEIGHTS,
    }
