"""
Build the scored universe from **market performance** (Finnhub quote % change),
not a fixed watchlist.

Uses a **daily-shuffled subset** of S&P 500 names (from `sp500_universe.csv`) so each
refresh scans a broad slice without issuing 500 quote calls at once. Symbols with the
highest `dp` (Finnhub daily percent change) win.

Requires `FINNHUB_ENABLED` + `FINNHUB_API_KEY`. On failure, returns `fallback_tickers`.
"""

from __future__ import annotations

import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx

from app.services.sp500 import load_sp500_universe

logger = logging.getLogger("uvicorn.error")

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"


def _daily_shuffled_pool(all_symbols: list[str], pool_max: int, seed_day: str | None = None) -> list[str]:
    """Stable subset for a given UTC day so repeated refreshes see the same candidate pool."""
    if not all_symbols:
        return []
    day = seed_day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(int(day.replace("-", "")))
    shuffled = list(all_symbols)
    rng.shuffle(shuffled)
    return shuffled[: max(1, min(pool_max, len(shuffled)))]


def _fetch_quote_dp(
    symbol: str,
    *,
    api_key: str,
    min_price: float,
) -> tuple[str, float, float] | None:
    # Fresh client per call — safe with ThreadPoolExecutor (shared httpx.Client is not).
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = client.get(
                FINNHUB_QUOTE_URL,
                params={"symbol": symbol.upper(), "token": api_key.strip()},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None
    try:
        c = float(data.get("c") or 0)
        dp = data.get("dp")
        if dp is None:
            return None
        dp_f = float(dp)
    except (TypeError, ValueError):
        return None
    if c < min_price:
        return None
    return (symbol.upper(), dp_f, c)


def discover_top_performer_tickers(
    *,
    finnhub_enabled: bool,
    finnhub_api_key: str,
    max_tickers: int,
    pool_max: int = 100,
    min_price: float = 2.0,
    fallback_tickers: list[str] | None = None,
    max_workers: int = 12,
) -> list[str]:
    """
    Return up to `max_tickers` symbols ranked by Finnhub **daily % change** (`dp`)
    within the daily S&P 500 subset.

    If Finnhub is off, missing key, or no usable quotes, returns `fallback_tickers`
    (trimmed) or a short emergency slice of S&P symbols.
    """
    fb = [t.strip().upper() for t in (fallback_tickers or []) if t.strip()]
    if not finnhub_enabled or not (finnhub_api_key or "").strip():
        logger.warning("Top-performer universe skipped: Finnhub disabled or missing API key.")
        return fb[:max_tickers] if fb else _emergency_sp500_slice(max_tickers)

    rows = load_sp500_universe()
    all_syms = sorted({str(r.get("ticker", "")).upper() for r in rows if r.get("ticker")})
    if not all_syms:
        logger.warning("Top-performer universe: no S&P symbols loaded; using fallback.")
        return fb[:max_tickers] if fb else []

    pool = _daily_shuffled_pool(all_syms, pool_max)
    results: list[tuple[str, float, float]] = []

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(pool)))) as ex:
        futures = {
            ex.submit(
                _fetch_quote_dp,
                sym,
                api_key=finnhub_api_key,
                min_price=min_price,
            ): sym
            for sym in pool
        }
        for fut in as_completed(futures):
            out = fut.result()
            if out:
                results.append(out)

    if not results:
        logger.warning("Top-performer universe: no valid Finnhub quotes; using fallback.")
        return fb[:max_tickers] if fb else _emergency_sp500_slice(max_tickers)

    results.sort(key=lambda x: x[1], reverse=True)
    picked: list[str] = []
    for sym, _dp, _c in results:
        if sym not in picked:
            picked.append(sym)
        if len(picked) >= max_tickers:
            break

    # Pad from fallback if we have room (e.g. thin pool)
    for sym in fb:
        if sym not in picked:
            picked.append(sym)
        if len(picked) >= max_tickers:
            break

    return picked[:max_tickers]


def _emergency_sp500_slice(n: int) -> list[str]:
    rows = load_sp500_universe()
    syms = sorted({str(r.get("ticker", "")).upper() for r in rows if r.get("ticker")})
    return syms[: max(1, min(n, len(syms)))]
