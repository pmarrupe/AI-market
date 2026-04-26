"""Resolve open trade plans against observed daily OHLC bars.

For each open plan we walk forward through the bars since the plan was recorded
and mark the first day where the bar's high reached target1 (target_hit) or the
bar's low reached the stop (stop_hit). Anything open past 30 calendar days is
marked expired.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable


_DEFAULT_EXPIRY_DAYS = 30


def resolve_open_plans(
    store,
    *,
    load_bars_fn: Callable[[str], list[dict] | None],
    expiry_days: int = _DEFAULT_EXPIRY_DAYS,
) -> dict:
    """Resolve every open plan whose outcome we can now determine.

    Returns a counts dict: {target_hit, stop_hit, expired, still_open}.
    """
    now = datetime.now(timezone.utc)
    expiry_cutoff = now - timedelta(days=expiry_days)

    counts = {"target_hit": 0, "stop_hit": 0, "expired": 0, "still_open": 0}
    open_plans = store.get_open_trade_plans()

    for plan in open_plans:
        ticker = plan["ticker"]
        try:
            created = datetime.fromisoformat(plan["created_at"])
        except Exception:
            created = now
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        bars = None
        try:
            bars = load_bars_fn(ticker)
        except Exception:
            bars = None

        outcome: str | None = None
        if bars:
            for bar in bars:
                try:
                    bar_date = datetime.strptime(bar["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except (KeyError, ValueError, TypeError):
                    continue
                if bar_date.date() < created.date():
                    continue
                high = float(bar.get("high") or 0)
                low = float(bar.get("low") or 0)
                # Target first: if price hit target on this day, mark as win.
                if high >= plan["target1"] > 0:
                    outcome = "target_hit"
                    break
                if low > 0 and low <= plan["stop"]:
                    outcome = "stop_hit"
                    break

        if outcome is None and created < expiry_cutoff:
            outcome = "expired"

        if outcome is None:
            counts["still_open"] += 1
            continue

        store.resolve_trade_plan(plan["id"], outcome)
        counts[outcome] = counts.get(outcome, 0) + 1

    return counts


def compute_win_stats(store, *, since_days: int = 30) -> dict:
    """Enriched summary: adds avg implied return per outcome."""
    stats = store.get_trade_plan_stats(since_days=since_days)
    # Compute implied avg return: target_hit => +R1 move, stop_hit => -risk move,
    # expired => 0. These are approximations (we don't store exit price yet).
    # Pull raw plans in window to estimate per-outcome.
    import sqlite3
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT entry, stop, target1, outcome
            FROM trade_plan_audit
            WHERE created_at >= ?
            """,
            (cutoff,),
        ).fetchall()
    returns: list[float] = []
    for entry, stop, target1, outcome in rows:
        if entry <= 0:
            continue
        if outcome == "target_hit":
            returns.append((target1 - entry) / entry)
        elif outcome == "stop_hit":
            returns.append((stop - entry) / entry)
        elif outcome == "expired":
            returns.append(0.0)
    if returns:
        stats["avg_return"] = round(sum(returns) / len(returns), 4)
    else:
        stats["avg_return"] = None
    return stats
