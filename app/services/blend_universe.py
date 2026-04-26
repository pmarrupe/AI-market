"""
Blend **user symbols** (watchlist ∪ tracked, else DEFAULT_TICKERS) with **top movers**
(S&P subset ranked by recent % change × dollar-volume rank, sourced from yfinance).

Always keeps the user anchor first (watchlist always wins), then appends movers
not already present until ``target_size`` is reached. If ``exclude_etfs`` is set,
ETFs are stripped from BOTH the anchor and the movers fill (they're noise in a
swing-trade decision feed).
"""

from __future__ import annotations

import logging

from app.services.top_performer_universe import discover_top_performer_tickers
from app.services.universe import dedupe_tickers
from app.services.universe_filters import filter_etfs, filter_by_liquidity
from app.services.yf_movers import discover_yf_movers

logger = logging.getLogger("uvicorn.error")


def build_blend_universe(
    *,
    watchlist_tickers: list[str],
    tracked_tickers: list[str],
    default_tickers: list[str],
    finnhub_enabled: bool,
    finnhub_api_key: str,
    target_size: int,
    pool_max: int,
    min_price: float,
    exclude_etfs: bool = True,
    min_dollar_volume: float = 0.0,
) -> list[str]:
    raw_anchor = dedupe_tickers(list(watchlist_tickers) + list(tracked_tickers))
    if not raw_anchor:
        raw_anchor = dedupe_tickers(default_tickers)

    anchor = filter_etfs(raw_anchor) if exclude_etfs else raw_anchor

    mover_slots = max(0, target_size - len(anchor))
    if mover_slots <= 0:
        return anchor

    # New path: yfinance movers (no API key needed, replaces dead Finnhub path).
    movers, mover_quotes = discover_yf_movers(
        pool_max=pool_max,
        target_size=mover_slots * 2,  # over-fetch for dedup overhead
        min_dollar_volume=min_dollar_volume,
        fallback_tickers=[],
    )

    # If yfinance returned nothing (network down, etc.), try the legacy
    # Finnhub path as a soft fallback.
    if not movers and finnhub_enabled and (finnhub_api_key or "").strip():
        logger.info("yf_movers empty — falling back to legacy Finnhub movers")
        movers = discover_top_performer_tickers(
            finnhub_enabled=finnhub_enabled,
            finnhub_api_key=finnhub_api_key,
            max_tickers=max(mover_slots * 3, target_size, 12),
            pool_max=pool_max,
            min_price=min_price,
            fallback_tickers=default_tickers,
        )

    if exclude_etfs:
        movers = filter_etfs(movers)
    if min_dollar_volume > 0 and mover_quotes:
        movers = filter_by_liquidity(
            movers, min_dollar_volume=min_dollar_volume, quotes=mover_quotes
        )

    have = set(anchor)
    fill: list[str] = []
    for sym in movers:
        if sym in have:
            continue
        have.add(sym)
        fill.append(sym)
        if len(fill) >= mover_slots:
            break

    return anchor + fill
