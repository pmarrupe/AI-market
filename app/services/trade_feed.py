"""Unified trade feed — merges the AI Stock Opportunity Scanner rows with the
Explosive Move Radar rows into a single list of trade ideas, normalized on
conviction / horizon / setup so the frontend can render one ranked list.

Design notes:
- Conviction: bucketed into High / Med / Low from score (0..1) for scanner rows
  and rankedOpportunityScore (0..100) for radar rows. On merge, take the higher
  bucket.
- Horizon: scanner provides it directly (Intraday/Short-term/Swing/Long-term).
  Radar doesn't — derive from setupType, with short-term as the default.
- Sources: each item carries a `sources` list (["scanner"], ["radar"], or both)
  so the drawer can decide which detail blocks to render.
"""
from __future__ import annotations

from typing import Any, Iterable


_HORIZON_BY_SETUP = {
    "Gap-and-Go Speculative Move": "Intraday",
    "Low Liquidity Spike": "Intraday",
    "Fresh IPO Momentum": "Short-term",
    "News Catalyst Breakout": "Short-term",
    "Weak Quality Spike": "Short-term",
    "Sector Sympathy Move": "Short-term",
    "High Volume Reversal": "Short-term",
    "Multi-Day Momentum Continuation": "Swing",
    "No Clear Edge": "Unclear",
}

_CONVICTION_ORDER = {"High": 3, "Med": 2, "Low": 1, "—": 0}


def _conviction_from_score01(score: float | None) -> str:
    if score is None:
        return "—"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "—"
    if s >= 0.60:
        return "High"
    if s >= 0.40:
        return "Med"
    return "Low"


def _conviction_from_score100(score: float | None) -> str:
    if score is None:
        return "—"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "—"
    if s >= 65:
        return "High"
    if s >= 40:
        return "Med"
    return "Low"


def _max_conviction(a: str, b: str) -> str:
    if _CONVICTION_ORDER.get(a, 0) >= _CONVICTION_ORDER.get(b, 0):
        return a
    return b


def _setup_from_signal(signal_label: str | None) -> str:
    if not signal_label:
        return "No Clear Edge"
    if signal_label.startswith("Strong Buy"):
        return "High-confidence setup"
    if signal_label == "Bullish":
        return "Bullish lean"
    if signal_label == "Watch":
        return "Watch"
    if signal_label == "Neutral":
        return "Neutral"
    return "Cautious"


def _scanner_to_item(row: dict[str, Any]) -> dict[str, Any]:
    conviction = _conviction_from_score01(row.get("score"))
    flags: list[str] = []
    status = row.get("status") or ""
    if status == "High Risk Setup":
        flags.append("High risk")
    if status == "Insufficient Evidence":
        flags.append("Low data")
    risk_level = row.get("riskLevel") or ""
    if risk_level == "High" and "High risk" not in flags:
        flags.append("High risk")

    why_bullets = row.get("whyNowBullets") or []
    top_reason = row.get("aiSummary") or (why_bullets[0] if why_bullets else "")

    return {
        "ticker": row.get("ticker"),
        "company": row.get("company"),
        "sector": row.get("sector"),
        "price": row.get("price"),
        "conviction": conviction,
        "horizon": row.get("timeHorizon") or "Unclear",
        "setup": _setup_from_signal(row.get("signalLabel")),
        "flags": flags,
        "topReason": top_reason,
        "sources": ["scanner"],
        # detail block for the drawer
        "scanner": {
            "score": row.get("score"),
            "confidence": row.get("confidence"),
            "momentum": row.get("momentum"),
            "scoreDelta": row.get("score_delta"),
            "evidenceCount": row.get("evidence_count"),
            "evidenceStrength": row.get("evidenceStrengthLabel"),
            "signalLabel": row.get("signalLabel"),
            "status": row.get("status"),
            "riskLevel": row.get("riskLevel"),
            "timeHorizon": row.get("timeHorizon"),
            "whyNowBullets": why_bullets,
            "linkedHeadlines": row.get("linked_headlines") or [],
            "recommendationNote": row.get("recommendationNote"),
            "aiSummary": row.get("aiSummary"),
            "dayChange": row.get("day_change"),
            "lastHeadlineAge": row.get("last_headline_age"),
            "lastHeadlineMinutes": row.get("last_headline_minutes"),
            "opportunityRank": row.get("opportunityRank"),
        },
    }


def _radar_to_item(row: dict[str, Any]) -> dict[str, Any]:
    conviction = _conviction_from_score100(row.get("rankedOpportunityScore"))
    flags: list[str] = []
    if row.get("fragileSetup"):
        flags.append("Fragile")
    conf = row.get("confidenceScore")
    # Tightened from 45 → 30: "Low data" should mean *starved*, not "middling".
    if conf is not None and conf < 30:
        flags.append("Low data")
    risk_score = row.get("riskScore")
    # Tightened from 65 → 75 to avoid "High risk" appearing on every radar row.
    if risk_score is not None and risk_score >= 75:
        flags.append("High risk")

    setup_type = row.get("setupType") or "No Clear Edge"
    horizon = _HORIZON_BY_SETUP.get(setup_type, "Short-term")

    return {
        "ticker": row.get("ticker"),
        "company": row.get("companyName"),
        "sector": row.get("sector"),
        "price": row.get("price"),
        "conviction": conviction,
        "horizon": horizon,
        "setup": setup_type,
        "flags": flags,
        "topReason": row.get("topReason") or row.get("setupDriver") or "",
        "sources": ["radar"],
        "radar": {
            "jumpScore": row.get("jumpScore"),
            "catalystScore": row.get("catalystScore"),
            "riskScore": row.get("riskScore"),
            "confidenceScore": row.get("confidenceScore"),
            "rankedOpportunityScore": row.get("rankedOpportunityScore"),
            "signalAgreementCount": row.get("signalAgreementCount"),
            "setupDriver": row.get("setupDriver"),
            "fragileSetup": row.get("fragileSetup"),
            "signalQualitySummary": row.get("signalQualitySummary"),
            "missingDataFields": row.get("missingDataFields") or [],
            "reasons": row.get("reasons") or [],
            "riskNotes": row.get("riskNotes") or [],
            "badges": row.get("badges") or [],
            "dataSource": row.get("dataSource"),
            "headlines": row.get("headlines") or [],
            "priceHistory": row.get("priceHistory") or [],
            "change1dPct": row.get("change1dPct"),
            "change3dPct": row.get("change3dPct"),
            "relativeVolume": row.get("relativeVolume"),
        },
    }


def _merge_items(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Merge two items for the same ticker. Field-level: prefer `base`, fill
    from `extra`; convictions take the higher bucket; sources union; flags
    union; setup from radar wins if present (more specific)."""
    merged = dict(base)
    merged["sources"] = sorted(set((base.get("sources") or []) + (extra.get("sources") or [])))
    merged["conviction"] = _max_conviction(base.get("conviction", "—"), extra.get("conviction", "—"))
    merged["flags"] = sorted(set((base.get("flags") or []) + (extra.get("flags") or [])))
    for key in ("company", "sector", "price", "topReason"):
        if not merged.get(key):
            merged[key] = extra.get(key)
    # Setup: prefer radar (more specific) when available
    if extra.get("setup") and extra.get("setup") != "No Clear Edge" and "radar" in (extra.get("sources") or []):
        merged["setup"] = extra["setup"]
    # Horizon: prefer the more specific (non-Unclear) one
    if merged.get("horizon") in (None, "", "Unclear") and extra.get("horizon") not in (None, "", "Unclear"):
        merged["horizon"] = extra["horizon"]
    # Detail blocks
    if "scanner" in extra and "scanner" not in merged:
        merged["scanner"] = extra["scanner"]
    if "radar" in extra and "radar" not in merged:
        merged["radar"] = extra["radar"]
    return merged


def _quality_score(item: dict[str, Any]) -> float:
    """Composite quality used as the conviction tiebreaker and as the
    standalone `quality_desc` sort. Combines model score with trade-plan R:R
    AND relative-volume confirmation so high-quality trades on heavy volume
    rank above the same setup on quiet volume."""
    radar = item.get("radar") or {}
    scanner = item.get("scanner") or {}
    plan = item.get("plan") or {}
    raw = max(
        float(scanner.get("score") or 0.0),
        float(radar.get("rankedOpportunityScore") or 0.0) / 100.0,
    )
    rr = float(plan.get("rewardRisk1") or 1.0)
    rr_capped = max(0.5, min(3.0, rr))
    # Volume boost: 1.0x = neutral; up to 1.4x for heavy institutional volume.
    rel_vol = float(plan.get("relativeVolume") or 1.0)
    vol_mult = max(0.7, min(1.4, 0.7 + rel_vol * 0.35))
    # Multiplicative; sqrt damps R:R extremes.
    return raw * (rr_capped ** 0.5) * vol_mult


def sort_items(items: list[dict[str, Any]], sort: str = "conviction_desc") -> list[dict[str, Any]]:
    """Public sort helper so consumers can re-sort after late mutations
    (e.g. earnings penalty) without rebuilding the feed."""
    key_fn, reverse = _sort_key(sort)
    items.sort(key=key_fn, reverse=reverse)
    return items


def _sort_key(sort: str):
    sort = (sort or "").lower()

    def conviction_rank(item: dict[str, Any]) -> tuple[float, float]:
        primary = float(_CONVICTION_ORDER.get(item.get("conviction", "—"), 0))
        # Within a conviction tier, rank by risk-adjusted quality.
        return (primary, _quality_score(item))

    if sort == "quality_desc":
        return _quality_score, True
    if sort == "delta_desc":
        return lambda x: float((x.get("scanner") or {}).get("scoreDelta") or 0), True
    if sort == "delta_asc":
        return lambda x: float((x.get("scanner") or {}).get("scoreDelta") or 0), False
    if sort == "headline_asc":
        # lowest minutes-since = freshest
        return (
            lambda x: float(
                (x.get("scanner") or {}).get("lastHeadlineMinutes") or 9e9
            ),
            False,
        )
    if sort == "jump_desc":
        return lambda x: float((x.get("radar") or {}).get("jumpScore") or 0), True
    # default: conviction desc
    return conviction_rank, True


def build_trade_feed(
    scanner_rows: Iterable[dict[str, Any]] | None,
    radar_items: Iterable[dict[str, Any]] | None,
    *,
    horizon: str | None = None,
    setup: str | None = None,
    sector: str | None = None,
    conviction: str | None = None,
    sort: str = "conviction_desc",
    limit: int = 100,
) -> dict[str, Any]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for r in scanner_rows or []:
        item = _scanner_to_item(r)
        t = item.get("ticker")
        if not t:
            continue
        by_ticker[t] = item
    for r in radar_items or []:
        item = _radar_to_item(r)
        t = item.get("ticker")
        if not t:
            continue
        if t in by_ticker:
            by_ticker[t] = _merge_items(by_ticker[t], item)
        else:
            by_ticker[t] = item

    items = list(by_ticker.values())

    # Filters
    def passes(it: dict[str, Any]) -> bool:
        if horizon and (it.get("horizon") or "").lower() != horizon.lower():
            return False
        if setup and (it.get("setup") or "") != setup:
            return False
        if sector and (it.get("sector") or "") != sector:
            return False
        if conviction and (it.get("conviction") or "") != conviction:
            return False
        return True

    items = [i for i in items if passes(i)]

    # Sort
    key_fn, reverse = _sort_key(sort)
    items.sort(key=key_fn, reverse=reverse)

    if limit and limit > 0:
        items = items[: min(limit, 500)]

    # Facets for filter dropdowns (over the unfiltered universe so the user
    # can see every option)
    universe = list(by_ticker.values())
    sectors_set = sorted({i.get("sector") for i in universe if i.get("sector")})
    setups_set = sorted({i.get("setup") for i in universe if i.get("setup")})
    horizons_set = sorted(
        {i.get("horizon") for i in universe if i.get("horizon")},
        key=lambda h: {"Intraday": 0, "Short-term": 1, "Swing": 2, "Long-term watch": 3, "Unclear": 4}.get(h, 9),
    )
    convictions_set = ["High", "Med", "Low"]

    summary = {
        "total": len(universe),
        "highConviction": sum(1 for i in universe if i.get("conviction") == "High"),
        "bothSources": sum(1 for i in universe if len(i.get("sources") or []) > 1),
        "radarOnly": sum(1 for i in universe if i.get("sources") == ["radar"]),
        "scannerOnly": sum(1 for i in universe if i.get("sources") == ["scanner"]),
    }

    return {
        "items": items,
        "summary": summary,
        "facets": {
            "sectors": sectors_set,
            "setups": setups_set,
            "horizons": horizons_set,
            "convictions": convictions_set,
        },
    }
