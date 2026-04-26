"""Universe-level filters that should run *before* scoring so we don't waste
work on tickers that have no business being in a swing-trade decision feed.

- `is_etf()` — recognise common ETFs by symbol
- `filter_etfs()` — drop them from a ticker list
- `filter_by_liquidity()` — drop tickers whose avg daily $ volume is too thin

Both filters fail open: if data isn't available, the ticker stays.
"""
from __future__ import annotations

from typing import Iterable


# Curated list of the most common ETFs that would otherwise show up in a
# market-cap / momentum scanner. Not exhaustive — but it covers the ones
# that matter for a US large/mid-cap focused trade feed.
_KNOWN_ETFS: frozenset[str] = frozenset({
    # Broad index
    "SPY", "VOO", "IVV", "VTI", "VT", "ITOT", "SPLG",
    "QQQ", "QQQM", "DIA", "IWM", "IJR", "IJH", "MDY", "VTV", "VUG", "VEA", "VWO",
    "EFA", "EEM", "ACWI", "VOOG", "VOOV", "SCHB", "SCHX", "SCHA", "SCHM",
    # Sector SPDRs + similar
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC",
    "VGT", "VFH", "VHT", "VDE", "VDC", "VIS", "VPU", "VAW", "VNQ", "VOX",
    "SMH", "SOXX", "IBB", "IGV", "FDN", "ARKK", "ARKW", "ARKQ", "ARKG", "ARKF",
    # Bond
    "TLT", "IEF", "SHY", "AGG", "BND", "LQD", "HYG", "JNK", "TIP", "MUB", "BIL",
    # Commodity / FX
    "GLD", "SLV", "GDX", "GDXJ", "USO", "UNG", "DBC", "PDBC", "UUP", "FXE", "FXY",
    # Leveraged / inverse (often muddy data)
    "TQQQ", "SQQQ", "SOXL", "SOXS", "SPXL", "SPXS", "TNA", "TZA",
    "UPRO", "SPXU", "FNGU", "FNGD", "TMF", "TMV",
    # Volatility
    "UVXY", "VXX", "SVXY", "VIXY",
    # Style / smart beta
    "MTUM", "QUAL", "USMV", "VLUE", "SIZE", "VIG", "DGRO", "SCHD", "DVY",
    # International / region
    "FXI", "MCHI", "EWZ", "EWJ", "EWG", "EWU", "EWT", "EWY", "INDA",
    # Other popular thematics
    "JEPI", "JEPQ", "QYLD", "RYLD", "XYLD",
})


def is_etf(ticker: str) -> bool:
    return (ticker or "").strip().upper() in _KNOWN_ETFS


def filter_etfs(tickers: Iterable[str]) -> list[str]:
    """Drop tickers in the known-ETF set, preserve order, dedupe."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tickers:
        sym = (t or "").strip().upper()
        if not sym or sym in seen or sym in _KNOWN_ETFS:
            seen.add(sym)
            continue
        seen.add(sym)
        out.append(sym)
    return out


def filter_by_liquidity(
    tickers: Iterable[str],
    *,
    min_dollar_volume: float = 20_000_000,
    quotes: dict[str, dict] | None = None,
) -> list[str]:
    """Drop tickers whose avg daily $ volume is below the floor.

    `quotes` is a {ticker: {"price": float, "avg_volume": float}} dict — if
    omitted, no filtering happens (fail open).
    """
    if not quotes or min_dollar_volume <= 0:
        return list(tickers)
    out: list[str] = []
    for t in tickers:
        sym = (t or "").strip().upper()
        q = quotes.get(sym) or {}
        price = float(q.get("price") or 0)
        vol = float(q.get("avg_volume") or 0)
        if price <= 0 or vol <= 0:
            # Fail open — no data, keep the ticker (better than silently dropping
            # things just because we couldn't get a quote)
            out.append(sym)
            continue
        dollar_volume = price * vol
        if dollar_volume >= min_dollar_volume:
            out.append(sym)
    return out
