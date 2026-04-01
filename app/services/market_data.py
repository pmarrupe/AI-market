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


def fetch_market_snapshots(
    tickers: list[str],
    *,
    finnhub_enabled: bool = False,
    finnhub_api_key: str = "",
) -> dict[str, MarketSnapshot]:
    """
    Prefer Finnhub daily candles when enabled + API key; otherwise Stooq CSV.
    """
    out: dict[str, MarketSnapshot] = {}
    use_fh = bool(finnhub_enabled and finnhub_api_key.strip())

    # If providers respond but give us price=0.0, retry once briefly to reduce
    # transient outages/rate-limits showing up as "0.00" in the UI.
    max_attempts = 2
    retry_delay_s = 0.8

    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        for ticker in tickers:
            sym = ticker.strip().upper()
            snapshot: MarketSnapshot | None = None

            for attempt in range(max_attempts):
                try:
                    if use_fh:
                        series = fetch_finnhub_daily_series(
                            sym,
                            finnhub_api_key.strip(),
                            client=client,
                            lookback_days=120,
                            min_closes=6,
                        )
                        snapshot = (
                            _compute_from_closes(series[0], series[1])
                            if series
                            else None
                        )
                        if snapshot and snapshot.last_price > 0:
                            break

                        quote_snapshot = _fetch_finnhub_quote_snapshot(
                            sym,
                            api_key=finnhub_api_key.strip(),
                            client=client,
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

                # Retry only when we got a "0.0 price" outcome.
                if snapshot and snapshot.last_price > 0:
                    break
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay_s)

            out[ticker] = snapshot if snapshot else _fallback_snapshot(ticker)

    return out
