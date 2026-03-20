"""
Historical price-based forward outlook using Finnhub daily candles.

Uses empirical distribution of past H-day forward returns (not a guarantee).
"""

from __future__ import annotations

import statistics
import time
from typing import Any

import httpx

FINNHUB_CANDLE_URL = "https://finnhub.io/api/v1/stock/candle"

# Need enough bars for 30-day forward windows + statistics
MIN_CLOSES = 45
DEFAULT_LOOKBACK_DAYS = 550  # calendar days → ~390 trading days


def fetch_finnhub_daily_series(
    symbol: str,
    api_key: str,
    *,
    client: httpx.Client | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_closes: int = MIN_CLOSES,
) -> tuple[list[float], list[float]] | None:
    """
    Return (closes, volumes) oldest → newest, aligned.
    None if Finnhub error or insufficient data.
    """
    sym = symbol.strip().upper()
    if not sym or not api_key:
        return None

    to_ts = int(time.time())
    from_ts = to_ts - lookback_days * 86400

    def _do_fetch(c: httpx.Client) -> tuple[list[float], list[float]] | None:
        resp = c.get(
            FINNHUB_CANDLE_URL,
            params={
                "symbol": sym,
                "resolution": "D",
                "from": from_ts,
                "to": to_ts,
                "token": api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("s") != "ok":
            return None
        ts_list = data.get("t") or []
        closes_raw = data.get("c") or []
        vols_raw = data.get("v") or []
        if not ts_list or not closes_raw or len(ts_list) != len(closes_raw):
            return None
        if len(vols_raw) != len(closes_raw):
            vols_raw = [0.0] * len(closes_raw)
        pairs = sorted(zip(ts_list, closes_raw, vols_raw), key=lambda x: x[0])
        out_c: list[float] = []
        out_v: list[float] = []
        for _, cval, vval in pairs:
            try:
                close = float(cval)
            except (TypeError, ValueError):
                continue
            if close <= 0:
                continue
            try:
                vol = float(vval) if vval is not None else 0.0
            except (TypeError, ValueError):
                vol = 0.0
            out_c.append(close)
            out_v.append(max(0.0, vol))
        return (out_c, out_v) if len(out_c) >= min_closes else None

    if client is not None:
        return _do_fetch(client)
    with httpx.Client(timeout=15.0, follow_redirects=True) as c:
        return _do_fetch(c)


def fetch_finnhub_daily_closes(
    symbol: str,
    api_key: str,
    *,
    client: httpx.Client | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[float] | None:
    series = fetch_finnhub_daily_series(
        symbol, api_key, client=client, lookback_days=lookback_days
    )
    return series[0] if series else None


def _forward_returns(closes: list[float], horizon: int) -> list[float]:
    rets: list[float] = []
    n = len(closes)
    for i in range(n - horizon):
        a, b = closes[i], closes[i + horizon]
        if a <= 0:
            continue
        rets.append((b - a) / a)
    return rets


def _confidence_from_sample(n: int, returns: list[float]) -> float:
    """Heuristic 0–1: more samples + lower dispersion → higher (still not investment advice)."""
    if n < 5:
        return 0.15
    size_factor = min(1.0, n / 120.0)
    if len(returns) < 2:
        return round(0.25 * size_factor, 3)
    stdev = statistics.pstdev(returns)
    # Typical daily-return stdev ~0.02–0.05; scale down confidence if very volatile
    vol_penalty = min(1.0, max(0.0, stdev * 4))
    raw = size_factor * max(0.2, 1.0 - vol_penalty)
    return round(min(1.0, max(0.05, raw)), 3)


def build_price_forecast(
    closes: list[float],
    horizons: tuple[int, ...] = (10, 20, 30),
) -> dict[str, Any]:
    """
    For each horizon:
    - prob_up: historical fraction of positive H-day forward returns
    - median_forward_return: median of those returns
    - predicted_price: last_close * (1 + median_forward_return)
    - confidence: heuristic based on sample size and return dispersion
    """
    last = closes[-1]
    horizons_out: list[dict[str, Any]] = []

    for h in horizons:
        rets = _forward_returns(closes, h)
        if not rets:
            horizons_out.append(
                {
                    "horizon_trading_days": h,
                    "sample_size": 0,
                    "prob_up": None,
                    "median_forward_return": None,
                    "predicted_price": None,
                    "confidence": 0.0,
                }
            )
            continue
        n = len(rets)
        prob_up = round(sum(1 for r in rets if r > 0) / n, 4)
        sorted_rets = sorted(rets)
        median_r = sorted_rets[n // 2]
        predicted = round(last * (1 + median_r), 2)
        conf = _confidence_from_sample(n, rets)
        horizons_out.append(
            {
                "horizon_trading_days": h,
                "sample_size": n,
                "prob_up": prob_up,
                "median_forward_return": round(median_r, 6),
                "predicted_price": predicted,
                "confidence": conf,
            }
        )

    return {
        "last_close": round(last, 4),
        "horizons": horizons_out,
        "methodology": (
            "Empirical: uses Finnhub daily closes; for each horizon H, computes historical "
            "H-trading-day forward returns and reports P(up), median return, and price implied by median. "
            "Not a forecast of actual future price; markets are not stationary."
        ),
    }
