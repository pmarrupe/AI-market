"""yfinance-based movers/liquidity scanner.

Picks candidate tickers from the S&P 500 universe by combining recent price
% change and dollar-volume rank, then filters by a liquidity floor.

This replaces the dead Finnhub-movers path on the free tier.

Implementation notes:
- We do NOT call `Ticker.info` per symbol (slow + scrape-heavy). Instead we
  use `yf.download(group=...)` to batch-fetch the last 7 days of OHLCV across
  the candidate pool in one HTTP round-trip.
- Stable daily-shuffled subset means refreshing twice in a row doesn't churn
  the candidate pool.
- All scoring is local; no LLM, no API key.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Iterable

from app.services.sp500 import load_sp500_universe
from app.services.universe_filters import filter_etfs, filter_by_liquidity

logger = logging.getLogger("uvicorn.error")


def _daily_shuffled_pool(symbols: list[str], pool_max: int) -> list[str]:
    """Stable daily-shuffled subset so a refresh doesn't churn the pool."""
    if not symbols:
        return []
    seed = datetime.now(timezone.utc).strftime("%Y%m%d")
    rng = random.Random(seed)
    pool = list(symbols)
    rng.shuffle(pool)
    return pool[: max(1, pool_max)]


def _batch_quote_summary(symbols: list[str]) -> dict[str, dict]:
    """Fetch last-7d OHLCV for a batch of tickers in one round-trip.

    Returns: {ticker: {"price": float, "avg_volume": float, "pct_change": float}}
    `pct_change` is 5-day percent move (today close vs 5-bars-ago close).
    Missing tickers are simply absent from the result.
    """
    if not symbols:
        return {}
    try:
        import yfinance as yf
    except ImportError:
        return {}

    out: dict[str, dict] = {}
    try:
        df = yf.download(
            tickers=" ".join(symbols),
            period="7d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.warning("yf.download batch failed: %s", exc)
        return {}

    if df is None or df.empty:
        return {}

    for sym in symbols:
        try:
            sub = df[sym] if isinstance(df.columns, type(df.columns)) and sym in df.columns.get_level_values(0) else None
        except Exception:
            sub = None
        if sub is None or sub.empty:
            continue
        try:
            closes = sub["Close"].dropna().tolist()
            volumes = sub["Volume"].dropna().tolist()
        except Exception:
            continue
        if not closes or not volumes:
            continue
        last_close = float(closes[-1])
        if last_close <= 0:
            continue
        avg_volume = float(sum(volumes) / max(1, len(volumes)))
        if len(closes) >= 2:
            ref_idx = max(0, len(closes) - 6)
            ref = float(closes[ref_idx])
            pct_change = (last_close - ref) / ref if ref > 0 else 0.0
        else:
            pct_change = 0.0
        out[sym] = {
            "price": last_close,
            "avg_volume": avg_volume,
            "pct_change": pct_change,
        }
    return out


def discover_yf_movers(
    *,
    pool_max: int = 200,
    target_size: int = 50,
    min_dollar_volume: float = 20_000_000,
    fallback_tickers: list[str] | None = None,
) -> tuple[list[str], dict[str, dict]]:
    """Pick `target_size` movers from a daily-shuffled S&P 500 subset.

    Returns (tickers, quote_summary) — the quote summary is per-ticker
    {price, avg_volume, pct_change} for downstream consumers (so the universe
    filter doesn't need to refetch).
    """
    universe_rows = load_sp500_universe()
    all_symbols = [row["ticker"] for row in universe_rows if row.get("ticker")]
    all_symbols = filter_etfs(all_symbols)  # SP500 shouldn't have ETFs, but defensive

    if not all_symbols:
        return list(fallback_tickers or []), {}

    pool = _daily_shuffled_pool(all_symbols, pool_max=pool_max)
    quotes = _batch_quote_summary(pool)
    if not quotes:
        logger.warning("yf_movers: batch quote fetch returned empty — using fallback")
        return list(fallback_tickers or []), {}

    # Liquidity floor first — drop sub-threshold names entirely.
    liquid_pool = [
        sym for sym in pool
        if sym in quotes
        and (quotes[sym]["price"] * quotes[sym]["avg_volume"]) >= min_dollar_volume
    ]

    # Rank by composite: recent move magnitude × log of dollar volume.
    # Magnitude rather than signed change so we surface big drops too —
    # those are often actionable (mean reversion, news shocks).
    import math

    def composite(sym: str) -> float:
        q = quotes[sym]
        dv = q["price"] * q["avg_volume"]
        # log10 dampens the volume term so a $5B avg volume name doesn't
        # dominate over a $50M name with stronger move.
        vol_score = math.log10(max(dv, 1.0))
        move_score = abs(q["pct_change"])
        return move_score * 4.0 + vol_score * 0.15

    ranked = sorted(liquid_pool, key=composite, reverse=True)
    picked = ranked[: max(1, target_size)]

    return picked, {sym: quotes[sym] for sym in picked}
