from __future__ import annotations

from datetime import datetime, timezone
import json

from app.models import Article, StockScore
from app.services.llm import llm_json_completion
from app.services.market_data import MarketSnapshot


def _confidence(linked_count: int, sentiment: float) -> float:
    evidence = min(1.0, linked_count / 4)
    signal = min(1.0, abs(sentiment))
    return round((0.7 * evidence) + (0.3 * signal), 3)


def _linked_signal_score(linked: list[Article]) -> float:
    if not linked:
        return 0.0
    return round(sum(a.signal_score for a in linked) / len(linked), 3)


def score_stocks(
    tickers: list[str],
    articles: list[Article],
    market: dict[str, MarketSnapshot],
    min_confidence: float = 0.45,
    weights: dict | None = None,
) -> list[StockScore]:
    scored: list[StockScore] = []
    for ticker in tickers:
        linked = [a for a in articles if ticker in a.tickers]
        sentiment = round(sum(a.sentiment for a in linked) / max(1, len(linked)), 3)
        link_coverage = min(1.0, len(linked) / 5)
        linked_signal = _linked_signal_score(linked)
        relevance = round((0.6 * link_coverage) + (0.4 * linked_signal), 3)
        snapshot = market.get(
            ticker,
            MarketSnapshot(
                last_price=0.0,
                day_change=0.0,
                momentum_5d=0.0,
                liquidity_score=0.3,
                valuation_sanity=0.5,
            ),
        )
        price = snapshot.last_price
        day_change = snapshot.day_change
        momentum = snapshot.momentum_5d
        liquidity = snapshot.liquidity_score
        valuation_sanity = snapshot.valuation_sanity
        confidence = _confidence(len(linked), sentiment)
        w = weights or {
            "relevance": 0.35,
            "sentiment": 0.2,
            "momentum": 0.2,
            "liquidity": 0.15,
            "valuation_sanity": 0.1,
        }
        total = round(
            (float(w.get("relevance", 0.35)) * relevance)
            + (float(w.get("sentiment", 0.2)) * sentiment)
            + (float(w.get("momentum", 0.2)) * momentum)
            + (float(w.get("liquidity", 0.15)) * liquidity)
            + (float(w.get("valuation_sanity", 0.1)) * valuation_sanity),
            3,
        )
        if confidence < min_confidence:
            total = 0.0
            explanation = (
                "Insufficient evidence for recommendation confidence threshold. "
                f"confidence={confidence}, threshold={min_confidence}, news links={len(linked)}."
            )
        else:
            explanation = (
                "Score uses relevance, sentiment, 5d momentum, liquidity, and valuation sanity checks. "
                f"relevance={relevance}, sentiment={sentiment}, momentum={momentum}, "
                f"liquidity={liquidity}, valuation_sanity={valuation_sanity}, linked_signal={linked_signal}. "
                f"News links found: {len(linked)}."
            )
        scored.append(
            StockScore(
                ticker=ticker,
                price=price,
                day_change=day_change,
                score=total,
                confidence=confidence,
                momentum=momentum,
                liquidity=liquidity,
                valuation_sanity=valuation_sanity,
                sentiment=sentiment,
                relevance=relevance,
                explanation=explanation,
                updated_at=datetime.now(timezone.utc),
            )
        )
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def llm_enhance_scores(
    scores: list[StockScore],
    articles: list[Article],
    llm: dict,
) -> list[StockScore]:
    if not scores:
        return scores
    article_map: dict[str, list[str]] = {}
    for score in scores:
        linked = [a for a in articles if score.ticker in a.tickers][:4]
        article_map[score.ticker] = [a.title for a in linked]
    user_payload = {
        "scores": [s.model_dump(mode="json") for s in scores],
        "linked_headlines": article_map,
    }
    system_prompt = llm.get(
        "score_system_prompt",
        (
            "You are a quant research assistant. Return JSON with key 'adjustments'. "
            "adjustments is an array of objects: {ticker, delta, note}. "
            "delta must be between -0.15 and 0.15 and should be 0 when evidence is weak."
        ),
    )
    user_prompt_prefix = llm.get(
        "score_user_prompt_prefix",
        "Review these computed stock scores and linked headlines. "
        "Apply small quality adjustments only when well supported.\n\n",
    )
    user_prompt = user_prompt_prefix + json.dumps(user_payload, ensure_ascii=True)
    out = llm_json_completion(
        enabled=llm.get("enabled", False),
        api_key=llm.get("api_key", ""),
        base_url=llm.get("base_url", ""),
        model=llm.get("model", ""),
        temperature=llm.get("temperature", 0.2),
        max_tokens=llm.get("max_tokens", 500),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    if not out:
        return scores
    indexed = {s.ticker: s for s in scores}
    for item in out.get("adjustments", []):
        ticker = str(item.get("ticker", "")).upper()
        if ticker not in indexed:
            continue
        raw_delta = float(item.get("delta", 0.0) or 0.0)
        delta = max(-0.15, min(0.15, raw_delta))
        note = str(item.get("note", "")).strip()
        existing = indexed[ticker]
        new_score = round(max(0.0, min(1.0, existing.score + delta)), 3)
        suffix = f" LLM adjustment={delta:+.3f}."
        if note:
            suffix += f" Note: {note}"
        indexed[ticker] = existing.model_copy(
            update={"score": new_score, "explanation": f"{existing.explanation}{suffix}"}
        )
    rescored = list(indexed.values())
    rescored.sort(key=lambda s: s.score, reverse=True)
    return rescored
