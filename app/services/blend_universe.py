"""
Blend **user symbols** (watchlist ∪ tracked, else DEFAULT_TICKERS) with **top movers**
(S&P subset ranked by Finnhub daily % change).

Always keeps the full anchor list first, then appends movers not already present until
``target_size`` is reached (or there are no more movers). If the anchor alone is
longer than ``target_size``, the returned list is the full anchor (user symbols win).
"""

from __future__ import annotations

from app.services.top_performer_universe import discover_top_performer_tickers
from app.services.universe import dedupe_tickers


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
) -> list[str]:
    anchor = dedupe_tickers(list(watchlist_tickers) + list(tracked_tickers))
    if not anchor:
        anchor = dedupe_tickers(default_tickers)
    mover_slots = max(0, target_size - len(anchor))
    if mover_slots <= 0:
        return anchor

    if not finnhub_enabled or not (finnhub_api_key or "").strip():
        return anchor

    # Ask for extra ranked names so we still fill slots after de-duping against anchor.
    fetch_n = min(pool_max, max(mover_slots * 3, target_size, 12))
    movers = discover_top_performer_tickers(
        finnhub_enabled=finnhub_enabled,
        finnhub_api_key=finnhub_api_key,
        max_tickers=fetch_n,
        pool_max=pool_max,
        min_price=min_price,
        fallback_tickers=default_tickers,
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
