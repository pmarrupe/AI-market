"""
Daily OHLCV fetch for Explosive Move Radar (Finnhub first, Stooq CSV fallback).

Reuses Finnhub candle endpoint shape from price_forecast; adds open/high/low for gaps and ATR.
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO

import httpx

from app.services.market_data import _stooq_symbol
from app.services.price_forecast import FINNHUB_CANDLE_URL

# Enough for ~20-day relative volume, breakout window, and ATR(14)
MIN_BARS_RADAR = 25
DEFAULT_LOOKBACK_DAYS = 200


@dataclass(frozen=True)
class DailyBarSeries:
    """Oldest → newest aligned arrays."""

    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    source: str
    # Optional calendar dates (ISO YYYY-MM-DD) per bar — used for historical validation / as-of news.
    dates_iso: tuple[str, ...] | None = None


def slice_bars_at_end(series: DailyBarSeries, end_exclusive: int) -> DailyBarSeries:
    """Truncate to bars [0:end_exclusive) for point-in-time simulation."""
    n = max(0, min(end_exclusive, len(series.closes)))
    if n == 0:
        return DailyBarSeries(
            opens=[],
            highs=[],
            lows=[],
            closes=[],
            volumes=[],
            source=series.source,
            dates_iso=None,
        )
    d = series.dates_iso[:n] if series.dates_iso else None
    return DailyBarSeries(
        opens=list(series.opens[:n]),
        highs=list(series.highs[:n]),
        lows=list(series.lows[:n]),
        closes=list(series.closes[:n]),
        volumes=list(series.volumes[:n]),
        source=series.source,
        dates_iso=d,
    )


def _fetch_finnhub_ohlcv(
    symbol: str,
    api_key: str,
    *,
    client: httpx.Client,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_bars: int = MIN_BARS_RADAR,
) -> DailyBarSeries | None:
    sym = symbol.strip().upper()
    if not sym or not api_key.strip():
        return None
    to_ts = int(time.time())
    from_ts = to_ts - lookback_days * 86400
    try:
        resp = client.get(
            FINNHUB_CANDLE_URL,
            params={
                "symbol": sym,
                "resolution": "D",
                "from": from_ts,
                "to": to_ts,
                "token": api_key.strip(),
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    if data.get("s") != "ok":
        return None
    ts_list = data.get("t") or []
    opens_raw = data.get("o") or []
    highs_raw = data.get("h") or []
    lows_raw = data.get("l") or []
    closes_raw = data.get("c") or []
    vols_raw = data.get("v") or []
    n = len(ts_list)
    if not closes_raw or len(closes_raw) != n:
        return None
    if len(opens_raw) != n:
        opens_raw = closes_raw
    if len(highs_raw) != n:
        highs_raw = closes_raw
    if len(lows_raw) != n:
        lows_raw = closes_raw
    if len(vols_raw) != n:
        vols_raw = [0.0] * n

    pairs = sorted(
        zip(ts_list, opens_raw, highs_raw, lows_raw, closes_raw, vols_raw),
        key=lambda x: x[0],
    )
    o_out: list[float] = []
    h_out: list[float] = []
    l_out: list[float] = []
    c_out: list[float] = []
    v_out: list[float] = []
    d_out: list[str] = []
    for ts, ov, hv, lv, cv, vv in pairs:
        try:
            c = float(cv)
        except (TypeError, ValueError):
            continue
        if c <= 0:
            continue
        try:
            o = float(ov) if ov is not None else c
            h = float(hv) if hv is not None else c
            l = float(lv) if lv is not None else c
            v = float(vv) if vv is not None else 0.0
        except (TypeError, ValueError):
            continue
        o_out.append(max(o, 1e-6))
        h_out.append(max(h, 1e-6))
        l_out.append(max(l, 1e-6))
        c_out.append(c)
        v_out.append(max(0.0, v))
        try:
            d_out.append(
                datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
            )
        except (TypeError, ValueError, OSError):
            d_out.append("")
    if len(c_out) < min_bars:
        return None
    dates = tuple(d_out) if d_out and all(d_out) else None
    return DailyBarSeries(
        opens=o_out,
        highs=h_out,
        lows=l_out,
        closes=c_out,
        volumes=v_out,
        source="finnhub",
        dates_iso=dates,
    )


def _fetch_stooq_ohlcv(
    symbol: str,
    *,
    client: httpx.Client,
    min_bars: int = MIN_BARS_RADAR,
) -> DailyBarSeries | None:
    sym = symbol.strip().upper()
    if not sym:
        return None
    try:
        stooq_sym = _stooq_symbol(sym)
        resp = client.get(f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d")
        resp.raise_for_status()
        parsed = list(csv.DictReader(StringIO(resp.text)))
    except Exception:
        return None
    o_out: list[float] = []
    h_out: list[float] = []
    l_out: list[float] = []
    c_out: list[float] = []
    v_out: list[float] = []
    d_out: list[str] = []
    for row in parsed:
        try:
            c = float(row.get("Close", "0") or 0)
            o = float(row.get("Open", "0") or c)
            h = float(row.get("High", "0") or c)
            l_ = float(row.get("Low", "0") or c)
            v = float(row.get("Volume", "0") or 0)
        except ValueError:
            continue
        if c <= 0:
            continue
        o_out.append(max(o, 1e-6))
        h_out.append(max(h, 1e-6))
        l_out.append(max(l_, 1e-6))
        c_out.append(c)
        v_out.append(max(0.0, v))
        raw_d = str(row.get("Date", "") or "").strip()
        d_out.append(raw_d[:10] if raw_d else "")
    if len(c_out) < min_bars:
        return None
    dates = tuple(d_out) if d_out and all(d_out) else None
    return DailyBarSeries(
        opens=o_out,
        highs=h_out,
        lows=l_out,
        closes=c_out,
        volumes=v_out,
        source="stooq",
        dates_iso=dates,
    )


def fetch_daily_bars_for_radar(
    ticker: str,
    *,
    finnhub_enabled: bool = False,
    finnhub_api_key: str = "",
    client: httpx.Client | None = None,
) -> DailyBarSeries | None:
    """
    Prefer Finnhub OHLCV; fall back to Stooq daily CSV.
    """
    sym = ticker.strip().upper()
    if not sym:
        return None

    def _run(c: httpx.Client) -> DailyBarSeries | None:
        if finnhub_enabled and finnhub_api_key.strip():
            fh = _fetch_finnhub_ohlcv(sym, finnhub_api_key, client=c)
            if fh:
                return fh
        return _fetch_stooq_ohlcv(sym, client=c)

    if client is not None:
        return _run(client)
    with httpx.Client(timeout=15.0, follow_redirects=True) as c:
        return _run(c)
