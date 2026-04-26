"""Earnings calendar fetcher (Finnhub free tier).

Returns a list of upcoming earnings events for a ticker. Never invents dates —
if the API is unreachable or missing on the free tier, returns None.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

FINNHUB_EARNINGS_URL = "https://finnhub.io/api/v1/calendar/earnings"


def fetch_earnings_events(
    ticker: str,
    api_key: str,
    *,
    client: httpx.Client | None = None,
    horizon_days: int = 120,
) -> list[dict[str, Any]] | None:
    """Upcoming earnings events for `ticker` within `horizon_days` from today.

    Each event: {date: 'YYYY-MM-DD', epsEstimate, revenueEstimate, hour}.
    Returns None on API failure; [] if API succeeded but no events found.
    """
    sym = (ticker or "").strip().upper()
    if not sym or not api_key or not api_key.strip():
        return None

    today = datetime.now(timezone.utc).date()
    to_day = today + timedelta(days=horizon_days)

    def _run(c: httpx.Client) -> list[dict] | None:
        try:
            resp = c.get(
                FINNHUB_EARNINGS_URL,
                params={
                    "from": today.isoformat(),
                    "to": to_day.isoformat(),
                    "symbol": sym,
                    "token": api_key.strip(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        events = data.get("earningsCalendar") if isinstance(data, dict) else None
        if events is None:
            return []
        out: list[dict] = []
        for e in events:
            date = e.get("date")
            if not date:
                continue
            out.append({
                "date": date,
                "epsEstimate": e.get("epsEstimate"),
                "revenueEstimate": e.get("revenueEstimate"),
                "hour": e.get("hour", ""),
                "symbol": e.get("symbol", sym),
            })
        out.sort(key=lambda x: x["date"])
        return out

    if client is not None:
        return _run(client)
    with httpx.Client(timeout=10.0, follow_redirects=True) as c:
        return _run(c)


def days_to_next_event(events: list[dict] | None) -> int | None:
    """Days from today to the next upcoming earnings event. None if no events."""
    if not events:
        return None
    today = datetime.now(timezone.utc).date()
    future_days: list[int] = []
    for e in events:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        if d >= today:
            future_days.append((d - today).days)
    return min(future_days) if future_days else None
