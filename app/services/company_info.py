"""yfinance-backed company info — what the company does, sector, market cap, etc.

Used by the drawer "Company snapshot" panel so users don't have to Google
each ticker. Cached aggressively (7d) because this data rarely changes.
"""
from __future__ import annotations

from typing import Any


def fetch_yfinance_company_info(ticker: str) -> dict[str, Any] | None:
    """Pull `Ticker.info` from yfinance and return a compact, frontend-friendly
    dict. Returns None on any failure — never raises."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(sym).info or {}
    except Exception:
        return None
    if not info:
        return None

    # yfinance occasionally returns just `{"trailingPegRatio": None}` for
    # delisted / missing tickers. Treat anything without a longName as empty.
    if not info.get("longName") and not info.get("shortName"):
        return None

    # Pick a sensible market-cap label. yfinance sometimes returns marketCap
    # in raw dollars (e.g. 2.5e12), sometimes None.
    market_cap = info.get("marketCap")
    market_cap_label = None
    if isinstance(market_cap, (int, float)) and market_cap > 0:
        if market_cap >= 1e12:
            market_cap_label = f"${market_cap / 1e12:.2f}T"
        elif market_cap >= 1e9:
            market_cap_label = f"${market_cap / 1e9:.1f}B"
        elif market_cap >= 1e6:
            market_cap_label = f"${market_cap / 1e6:.0f}M"
        else:
            market_cap_label = f"${market_cap:,.0f}"

    summary = (info.get("longBusinessSummary") or info.get("summary") or "").strip()

    return {
        "ticker": sym,
        "name": info.get("longName") or info.get("shortName") or sym,
        "summary": summary,
        "industry": info.get("industry") or "",
        "sector": info.get("sector") or "",
        "country": info.get("country") or "",
        "website": info.get("website") or "",
        "marketCap": market_cap_label,
        "marketCapRaw": market_cap if isinstance(market_cap, (int, float)) else None,
        "employees": info.get("fullTimeEmployees"),
        "exchange": info.get("exchange") or info.get("fullExchangeName") or "",
        "currency": info.get("currency") or "USD",
        # Useful trailing fundamentals when present
        "trailingPE": info.get("trailingPE"),
        "forwardPE": info.get("forwardPE"),
        "dividendYield": info.get("dividendYield"),
        "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        "beta": info.get("beta"),
    }
