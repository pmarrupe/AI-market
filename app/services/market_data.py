from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO

import httpx
import time

from app.services.price_forecast import fetch_finnhub_daily_series


@dataclass(frozen=True)
class MarketSnapshot:
    last_price: float
    day_change: float
    momentum_5d: float
    liquidity_score: float
    valuation_sanity: float


def _stooq_symbol(ticker: str) -> str:
    return f"{ticker.lower()}.us"


def fetch_yfinance_ohlc(
    ticker: str,
    *,
    min_rows: int = 30,
    period: str = "90d",
) -> list[dict] | None:
    """Daily OHLC bars oldest→newest from Yahoo Finance via the `yfinance`
    package. Returns None on any failure — never raises.

    Yahoo is free and doesn't require an API key. This is the primary source
    for historical bars after Stooq pulled free CSV access in 2025.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=False)
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    bars: list[dict] = []
    for idx, row in hist.iterrows():
        try:
            o = float(row["Open"])
            h = float(row["High"])
            lo = float(row["Low"])
            c = float(row["Close"])
            v = float(row.get("Volume", 0) or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if c <= 0 or h <= 0 or lo <= 0:
            continue
        bars.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(lo, 4),
            "close": round(c, 4),
            "volume": v,
        })
    return bars if len(bars) >= min_rows else None


def fetch_yfinance_ohlc_batch(
    tickers: list[str],
    *,
    min_rows: int = 30,
    period: str = "90d",
) -> dict[str, list[dict]]:
    """Batch-fetch daily OHLC bars for many tickers in ONE yfinance HTTP call.

    Returns: {ticker: [{date, open, high, low, close, volume}, ...]} for tickers
    that have at least `min_rows` valid bars. Tickers that fail are simply
    absent from the result.

    This replaces N sequential `fetch_yfinance_ohlc` calls when computing
    trade plans across the whole feed.
    """
    syms = [t.strip().upper() for t in tickers if t and t.strip()]
    syms = list(dict.fromkeys(syms))  # dedupe, preserve order
    if not syms:
        return {}
    try:
        import yfinance as yf
    except ImportError:
        return {}
    try:
        df = yf.download(
            tickers=" ".join(syms),
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception:
        return {}
    if df is None or df.empty:
        return {}

    out: dict[str, list[dict]] = {}
    # `group_by="ticker"` produces a MultiIndex on columns even for a single
    # ticker, so always access via df[sym] when the column is multi-level.
    is_multi = hasattr(df.columns, "levels")
    for sym in syms:
        try:
            sub = df[sym] if is_multi else df
        except Exception:
            continue
        if sub is None or sub.empty:
            continue
        bars: list[dict] = []
        for idx, row in sub.iterrows():
            try:
                o = float(row["Open"])
                h = float(row["High"])
                lo = float(row["Low"])
                c = float(row["Close"])
                v = float(row.get("Volume", 0) or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if c <= 0 or h <= 0 or lo <= 0:
                continue
            bars.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(lo, 4),
                "close": round(c, 4),
                "volume": v,
            })
        if len(bars) >= min_rows:
            out[sym] = bars
    return out


def fetch_stooq_ohlc(
    ticker: str,
    client: httpx.Client | None = None,
    *,
    min_rows: int = 30,
) -> list[dict] | None:
    """Daily OHLC bars oldest→newest from Stooq CSV.

    Deprecated 2025: Stooq pulled free CSV download; the endpoint now returns
    an API-key prompt. Kept as a fallback in case a STOOQ_API_KEY becomes
    available later, but expected to return None on the free path.
    Prefer fetch_yfinance_ohlc.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return None

    def _run(c: httpx.Client) -> list[dict] | None:
        try:
            symbol = _stooq_symbol(sym)
            resp = c.get(f"https://stooq.com/q/d/l/?s={symbol}&i=d")
            resp.raise_for_status()
            parsed = list(csv.DictReader(StringIO(resp.text)))
        except Exception:
            return None
        bars: list[dict] = []
        for row in parsed:
            try:
                o = float(row.get("Open", "0") or 0)
                h = float(row.get("High", "0") or 0)
                low = float(row.get("Low", "0") or 0)
                c_ = float(row.get("Close", "0") or 0)
                v = float(row.get("Volume", "0") or 0)
            except ValueError:
                continue
            if c_ <= 0 or h <= 0 or low <= 0:
                continue
            bars.append({
                "date": row.get("Date", ""),
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(low, 4),
                "close": round(c_, 4),
                "volume": v,
            })
        return bars if len(bars) >= min_rows else None

    if client is not None:
        return _run(client)
    with httpx.Client(timeout=12.0, follow_redirects=True) as c:
        return _run(c)


def fetch_stooq_daily_closes_for_forecast(
    ticker: str,
    client: httpx.Client | None = None,
    *,
    min_closes: int = 36,
) -> list[float] | None:
    """
    Daily closes oldest → newest from Stooq CSV (fallback when Finnhub candles fail).
    """
    sym = ticker.strip().upper()
    if not sym:
        return None

    def _run(c: httpx.Client) -> list[float] | None:
        try:
            symbol = _stooq_symbol(sym)
            resp = c.get(f"https://stooq.com/q/d/l/?s={symbol}&i=d")
            resp.raise_for_status()
            parsed = list(csv.DictReader(StringIO(resp.text)))
        except Exception:
            return None
        closes: list[float] = []
        for row in parsed:
            try:
                v = float(row.get("Close", "0") or 0)
            except ValueError:
                continue
            if v > 0:
                closes.append(v)
        return closes if len(closes) >= min_closes else None

    if client is not None:
        return _run(client)
    with httpx.Client(timeout=12.0, follow_redirects=True) as c:
        return _run(c)


def _fallback_snapshot(_ticker: str) -> MarketSnapshot:
    """
    Used when Finnhub/Stooq fail. Do NOT invent a fake price — that misleads users.
    Use zeros + neutral factors so UIs can show 'quote unavailable'.
    """
    return MarketSnapshot(
        last_price=0.0,
        day_change=0.0,
        momentum_5d=0.0,
        liquidity_score=0.3,
        valuation_sanity=0.5,
    )


def _compute_from_rows(rows: list[dict[str, str]]) -> MarketSnapshot | None:
    closes: list[float] = []
    volumes: list[float] = []
    for row in rows:
        try:
            close = float(row.get("Close", "0") or 0)
            volume = float(row.get("Volume", "0") or 0)
        except ValueError:
            continue
        if close <= 0:
            continue
        closes.append(close)
        if volume > 0:
            volumes.append(volume)
    if len(closes) < 6:
        return None
    latest = closes[-1]
    prev_day = closes[-2]
    prior = closes[-6]
    if prior <= 0:
        return None
    day_change = round((latest - prev_day) / prev_day, 3) if prev_day > 0 else 0.0
    momentum = round((latest - prior) / prior, 3)
    avg_volume = sum(volumes[-10:]) / max(1, len(volumes[-10:]))
    liquidity = round(min(1.0, avg_volume / 30_000_000), 3)
    dislocation = abs(momentum)
    valuation_sanity = round(max(0.0, 1.0 - (dislocation * 2.5)), 3)
    return MarketSnapshot(
        last_price=round(latest, 2),
        day_change=day_change,
        momentum_5d=momentum,
        liquidity_score=liquidity,
        valuation_sanity=valuation_sanity,
    )


def _compute_from_closes(closes: list[float], volumes: list[float] | None = None) -> MarketSnapshot | None:
    if len(closes) < 6:
        return None
    vols = volumes if volumes and len(volumes) == len(closes) else [0.0] * len(closes)
    latest = closes[-1]
    prev_day = closes[-2]
    prior = closes[-6]
    if prior <= 0:
        return None
    day_change = round((latest - prev_day) / prev_day, 3) if prev_day > 0 else 0.0
    momentum = round((latest - prior) / prior, 3)
    recent_v = [v for v in vols[-10:] if v > 0]
    if recent_v:
        avg_vol = sum(recent_v) / len(recent_v)
        liquidity = round(min(1.0, avg_vol / 30_000_000), 3)
    else:
        liquidity = 0.45
    dislocation = abs(momentum)
    valuation_sanity = round(max(0.0, 1.0 - (dislocation * 2.5)), 3)
    return MarketSnapshot(
        last_price=round(latest, 2),
        day_change=day_change,
        momentum_5d=momentum,
        liquidity_score=max(0.35, liquidity),
        valuation_sanity=valuation_sanity,
    )


def _fetch_finnhub_quote_snapshot(
    ticker: str,
    *,
    api_key: str,
    client: httpx.Client,
) -> MarketSnapshot | None:
    """
    Fallback when Finnhub candle endpoint is unavailable.
    Uses /quote (c,d,dp,pc) to populate a real latest price and 1D change.
    """
    if not ticker or not api_key:
        return None
    try:
        resp = client.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker.upper(), "token": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    try:
        price = float(data.get("c", 0) or 0)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        return None

    # Prefer dp (percent change), otherwise derive from c and pc.
    day_change = 0.0
    try:
        dp = data.get("dp")
        if dp is not None:
            day_change = float(dp) / 100.0
        else:
            prev_close = float(data.get("pc", 0) or 0)
            if prev_close > 0:
                day_change = (price - prev_close) / prev_close
    except (TypeError, ValueError, ZeroDivisionError):
        day_change = 0.0

    return MarketSnapshot(
        last_price=round(price, 2),
        day_change=round(day_change, 3),
        momentum_5d=0.0,       # unavailable from /quote alone
        liquidity_score=0.45,  # neutral fallback
        valuation_sanity=0.6,  # neutral fallback
    )


def _fetch_one_snapshot(
    ticker: str, *, finnhub_enabled: bool, finnhub_api_key: str
) -> MarketSnapshot:
    """Fetch one ticker's snapshot. Used by the parallel batch path."""
    sym = ticker.strip().upper()
    use_fh = bool(finnhub_enabled and finnhub_api_key.strip())
    snapshot: MarketSnapshot | None = None
    max_attempts = 2
    retry_delay_s = 0.8

    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
        for attempt in range(max_attempts):
            try:
                if use_fh:
                    series = fetch_finnhub_daily_series(
                        sym, finnhub_api_key.strip(), client=client,
                        lookback_days=120, min_closes=6,
                    )
                    snapshot = _compute_from_closes(series[0], series[1]) if series else None
                    if snapshot and snapshot.last_price > 0:
                        break
                    quote_snapshot = _fetch_finnhub_quote_snapshot(
                        sym, api_key=finnhub_api_key.strip(), client=client,
                    )
                    if quote_snapshot and quote_snapshot.last_price > 0:
                        snapshot = quote_snapshot
                        break
                symbol = _stooq_symbol(sym)
                resp = client.get(f"https://stooq.com/q/d/l/?s={symbol}&i=d")
                resp.raise_for_status()
                parsed = list(csv.DictReader(StringIO(resp.text)))
                computed = _compute_from_rows(parsed)
                snapshot = computed if computed else _fallback_snapshot(ticker)
            except Exception:
                snapshot = _fallback_snapshot(ticker)
            if snapshot and snapshot.last_price > 0:
                break
            if attempt < max_attempts - 1:
                time.sleep(retry_delay_s)
    return snapshot if snapshot else _fallback_snapshot(ticker)


def fetch_market_snapshots(
    tickers: list[str],
    *,
    finnhub_enabled: bool = False,
    finnhub_api_key: str = "",
    max_workers: int = 12,
    per_call_timeout_s: float = 12.0,
) -> dict[str, MarketSnapshot]:
    """Parallel snapshot fetch — was sequential, which made cold-cache loads
    take 1-3 minutes for a 50-ticker universe."""
    if not tickers:
        return {}
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout

    out: dict[str, MarketSnapshot] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_sym = {
            ex.submit(_fetch_one_snapshot, t,
                       finnhub_enabled=finnhub_enabled,
                       finnhub_api_key=finnhub_api_key): t
            for t in tickers
        }
        for fut in as_completed(future_to_sym):
            sym = future_to_sym[fut]
            try:
                out[sym] = fut.result(timeout=per_call_timeout_s)
            except (FutTimeout, Exception):
                out[sym] = _fallback_snapshot(sym)
    return out
