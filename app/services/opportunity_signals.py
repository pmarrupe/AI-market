from __future__ import annotations

from datetime import datetime, timezone


COMPANY_MAP = {
    "NVDA": "NVIDIA",
    "AMD": "Advanced Micro Devices",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "AAPL": "Apple",
    "PANW": "Palo Alto Networks",
    "CRM": "Salesforce",
    "ASML": "ASML",
    "QCOM": "Qualcomm",
    "UNH": "UnitedHealth",
    "AVGO": "Broadcom",
    "CRWD": "CrowdStrike",
    "TSM": "TSMC",
    "NFLX": "Netflix",
}


def _relative_age_minutes(published_at: datetime | None) -> int | None:
    if not published_at:
        return None
    now = datetime.now(timezone.utc)
    try:
        delta = now - published_at.astimezone(timezone.utc)
    except Exception:
        return None
    return max(0, int(delta.total_seconds() // 60))


def _relative_age_label(minutes: int | None) -> str:
    if minutes is None:
        return "n/a"
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


# Heuristic mapping for retail readability; tune these thresholds as needed.
def _signal_from_score(score: float) -> tuple[str, str]:
    if score >= 0.70:
        return "Strong Buy Signal", "signal-strong-buy"
    if score >= 0.50:
        return "Bullish", "signal-bullish"
    if score >= 0.30:
        return "Watch", "signal-watch"
    if score >= 0.10:
        return "Neutral", "signal-neutral"
    return "Avoid / Insufficient Setup", "signal-avoid"


def _risk_level(confidence: float, evidence_count: int, momentum: float) -> tuple[str, str]:
    if confidence < 0.35 or evidence_count <= 1:
        return "High", "risk-high"
    if confidence >= 0.7 and evidence_count >= 4 and abs(momentum) <= 0.12:
        return "Low", "risk-low"
    return "Medium", "risk-medium"


def _time_horizon(score: float, confidence: float, evidence_count: int, momentum: float, headline_age_mins: int | None) -> str:
    if confidence < 0.3 or evidence_count <= 1:
        return "Unclear"
    recent = headline_age_mins is not None and headline_age_mins <= 240
    if recent and abs(momentum) >= 0.045 and score >= 0.5:
        return "Intraday"
    if recent and abs(momentum) >= 0.02 and score >= 0.45:
        return "Short-term"
    if score >= 0.35 and confidence >= 0.45:
        return "Swing"
    if evidence_count >= 4 and abs(momentum) < 0.02:
        return "Long-term watch"
    return "Unclear"


def _evidence_strength_label(evidence_count: int) -> str:
    if evidence_count >= 6:
        return "Very strong"
    if evidence_count >= 4:
        return "Strong"
    if evidence_count >= 2:
        return "Moderate"
    return "Weak"


def _status(score: float, confidence: float, evidence_count: int, risk_level: str) -> tuple[str, str]:
    if evidence_count <= 1 or confidence < 0.25:
        return "Insufficient Evidence", "status-insufficient"
    if risk_level == "High" and score >= 0.30:
        return "High Risk Setup", "status-high-risk"
    if score >= 0.55 and confidence >= 0.55 and evidence_count >= 3 and risk_level != "High":
        return "Actionable", "status-actionable"
    if score >= 0.35 and confidence >= 0.45:
        return "Watchlist", "status-watchlist"
    return "Needs Confirmation", "status-confirm"


def _ai_summary(score: float, confidence: float, evidence_count: int, day_change: float, sentiment: float, momentum: float) -> str:
    if evidence_count <= 1 or confidence < 0.25:
        return "Too little evidence right now to support a decision."
    if score >= 0.7 and confidence >= 0.65 and sentiment > 0 and momentum > 0:
        return "Strong positive news support with improving momentum."
    if score >= 0.5 and confidence >= 0.5:
        return "High evidence and solid confidence make this a watchlist candidate."
    if sentiment > 0 and day_change > 0 and momentum >= 0:
        return "Positive news momentum is building; monitor for confirmation."
    if momentum < 0 and evidence_count >= 3:
        return "Momentum is weak despite headline coverage; wait for confirmation."
    return "Signal quality is mixed; treat as a monitoring setup."


def _recommendation_note(score: float, confidence: float, evidence_count: int, risk_level: str, momentum: float) -> str:
    if score >= 0.6 and confidence >= 0.55 and risk_level != "High":
        return "Momentum-supported bullish setup, worth immediate review."
    if evidence_count <= 1 or confidence < 0.3:
        return "Interesting but insufficient confirmation."
    if momentum > 0 and evidence_count >= 3:
        return "News-backed move; continue tracking for follow-through."
    return "News-backed move, but reliability remains low."


def _why_now_bullets(evidence_count: int, sentiment: float, day_change: float, momentum: float) -> list[str]:
    momentum_direction = "improving" if momentum > 0 else "weakening" if momentum < 0 else "flat"
    return [
        f"{evidence_count} linked headline{'s' if evidence_count != 1 else ''}",
        f"Sentiment {sentiment:+.2f}",
        f"Price move {day_change:+.2%} today",
        f"Momentum {momentum_direction}",
    ]


def _score_trend_points(score: float, score_delta: float | None, momentum: float, confidence: float) -> list[float]:
    prev = score - score_delta if score_delta is not None else max(0.0, score - 0.04)
    p1 = max(0.0, min(1.0, prev * 0.9))
    p2 = max(0.0, min(1.0, prev + (momentum * 0.6)))
    p3 = max(0.0, min(1.0, prev + (momentum * 0.9)))
    p4 = max(0.0, min(1.0, (score + prev) / 2))
    p5 = max(0.0, min(1.0, score))
    p6 = max(0.0, min(1.0, (score * 0.7) + (confidence * 0.3)))
    return [round(x, 3) for x in [p1, p2, p3, p4, p5, p6]]


def build_opportunity_view(
    *,
    stocks,
    articles,
    previous_scores: dict[str, float],
    stock_market_rows: list[dict[str, object]],
    last_updated: datetime | None = None,
) -> dict[str, object]:
    sector_by_ticker = {row["ticker"]: row["sector"] for row in stock_market_rows}
    rows: list[dict[str, object]] = []

    for stock in stocks:
        linked = [article for article in articles if stock.ticker in article.tickers]
        linked.sort(key=lambda article: article.published_at, reverse=True)
        evidence_count = len(linked)
        headline_age_mins = _relative_age_minutes(linked[0].published_at if linked else None)
        score_delta = None
        if stock.ticker in previous_scores:
            score_delta = round(stock.score - previous_scores[stock.ticker], 3)

        signal_label, signal_color = _signal_from_score(stock.score)
        risk_label, risk_color = _risk_level(stock.confidence, evidence_count, stock.momentum)
        horizon = _time_horizon(stock.score, stock.confidence, evidence_count, stock.momentum, headline_age_mins)
        status_label, status_color = _status(stock.score, stock.confidence, evidence_count, risk_label)
        why_bullets = _why_now_bullets(evidence_count, stock.sentiment, stock.day_change, stock.momentum)
        ai_summary = _ai_summary(
            stock.score, stock.confidence, evidence_count, stock.day_change, stock.sentiment, stock.momentum
        )
        recommendation_note = _recommendation_note(
            stock.score, stock.confidence, evidence_count, risk_label, stock.momentum
        )
        evidence_strength = _evidence_strength_label(evidence_count)
        trend_points = _score_trend_points(stock.score, score_delta, stock.momentum, stock.confidence)
        sector = sector_by_ticker.get(stock.ticker, "Other")
        opportunity_rank = round(
            (stock.score * 0.5)
            + (stock.confidence * 0.25)
            + (min(1.0, evidence_count / 6) * 0.2)
            + (max(0.0, stock.day_change) * 0.5),
            3,
        )

        rows.append(
            {
                "ticker": stock.ticker,
                "company": COMPANY_MAP.get(stock.ticker, stock.ticker),
                "sector": sector,
                "price": stock.price,
                "day_change": stock.day_change,
                "score": stock.score,
                "confidence": stock.confidence,
                "sentiment": stock.sentiment,
                "momentum": stock.momentum,
                "score_delta": score_delta,
                "signalLabel": signal_label,
                "signalColor": signal_color,
                "riskLevel": risk_label,
                "riskColor": risk_color,
                "timeHorizon": horizon,
                "status": status_label,
                "statusColor": status_color,
                "aiSummary": ai_summary,
                "recommendationNote": recommendation_note,
                "whyNowBullets": why_bullets,
                "evidence_count": evidence_count,
                "evidenceStrengthLabel": evidence_strength,
                "last_headline_age": _relative_age_label(headline_age_mins),
                "last_headline_minutes": headline_age_mins if headline_age_mins is not None else 999999,
                "opportunityRank": opportunity_rank,
                "scoreTrend": trend_points,
                "linked_headlines": [article.title for article in linked[:5]],
            }
        )

    rows.sort(key=lambda row: row["opportunityRank"], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["opportunityRank"] = idx

    actionable = [row for row in rows if row["status"] == "Actionable"]
    watchlist = [row for row in rows if row["status"] == "Watchlist"]
    insufficient = [row for row in rows if row["status"] == "Insufficient Evidence"]
    avg_sentiment = round(sum(row["sentiment"] for row in rows) / max(1, len(rows)), 3)

    top_candidates = [row for row in rows if row["status"] in {"Actionable", "Watchlist", "Needs Confirmation"}]
    if len(top_candidates) < 3:
        top_candidates = rows
    top3 = top_candidates[:3]

    summary = {
        "top_opportunities_today": len(top_candidates),
        "actionable_count": len(actionable),
        "watchlist_count": len(watchlist),
        "insufficient_count": len(insufficient),
        "avg_sentiment": avg_sentiment,
        "last_updated": (last_updated or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    return {
        "rows": rows,
        "summary": summary,
        "top3": top3,
        "sectors": sorted({row["sector"] for row in rows}),
        "signal_labels": sorted({row["signalLabel"] for row in rows}),
        "risk_levels": sorted({row["riskLevel"] for row in rows}),
        "time_horizons": sorted({row["timeHorizon"] for row in rows}),
        "statuses": sorted({row["status"] for row in rows}),
    }
