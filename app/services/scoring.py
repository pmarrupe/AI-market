from __future__ import annotations

from datetime import datetime, timezone
import json

from app.models import Article, StockScore
from app.services.llm import llm_json_completion
from app.services.market_data import MarketSnapshot


def _news_confidence(linked_count: int, sentiment: float) -> float:
    """Confidence in the *news* leg only. 0..1."""
    evidence = min(1.0, linked_count / 4)
    signal = min(1.0, abs(sentiment))
    return round((0.7 * evidence) + (0.3 * signal), 3)


def _normalize(value: float, scale: float) -> float:
    """Map a signed value (e.g. day_change=0.04 → 1.0 if scale=0.04) into [-1,1]."""
    if scale <= 0:
        return 0.0
    return max(-1.0, min(1.0, value / scale))


def _technical_score(
    *,
    momentum: float,
    day_change: float,
    liquidity: float,
    valuation_sanity: float,
    relative_strength_5d: float = 0.0,
) -> float:
    """How energetic is this ticker on the chart, regardless of news? 0..1.

    Magnitude-only on raw momentum (we want the *opportunity*; direction is
    captured elsewhere). Relative strength vs benchmark is *signed* — only
    OUTPERFORMING the benchmark adds to the score, underperformance gets 0
    bonus (but isn't punished). 5d ±5% relative outperformance maps to 1.0.
    """
    m_strength = abs(_normalize(momentum, 0.08))
    dc_strength = abs(_normalize(day_change, 0.04))
    rs_bonus = max(0.0, _normalize(relative_strength_5d, 0.05))
    return round(
        0.40 * m_strength
        + 0.20 * dc_strength
        + 0.15 * rs_bonus
        + 0.15 * max(0.0, min(1.0, liquidity))
        + 0.10 * max(0.0, min(1.0, valuation_sanity)),
        3,
    )


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
    benchmark: MarketSnapshot | None = None,
) -> list[StockScore]:
    """Three-leg scoring: news + technical + valuation.

    No leg can zero out the others. A ticker with strong technicals but no news
    will still score in the 0.3–0.6 range; a ticker with strong news AND
    technicals will score 0.6+. `min_confidence` is now a soft floor — below it
    the explanation flags low confidence, but the score itself isn't nuked
    (the user can decide whether to act on it).
    """
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

        news_conf = _news_confidence(len(linked), sentiment)
        # Relative strength vs benchmark (5d). Positive = outperforming.
        bench_mom = benchmark.momentum_5d if benchmark else 0.0
        rs_5d = momentum - bench_mom
        tech_score = _technical_score(
            momentum=momentum,
            day_change=day_change,
            liquidity=liquidity,
            valuation_sanity=valuation_sanity,
            relative_strength_5d=rs_5d,
        )

        # News leg score (only meaningful when there's actual coverage). We
        # treat positive sentiment as bullish and negative as bearish; the
        # *magnitude* of sentiment is captured in news_conf above.
        bullish_sentiment = max(0.0, sentiment)  # only positive counts here
        news_score = round(0.65 * relevance + 0.35 * bullish_sentiment, 3)

        # Combine legs as "probability either signal fires" — i.e.
        #   total = 1 − (1 − news) × (1 − tech)
        # This way a strong tech score is never *reduced* by mediocre news;
        # corroborating news only boosts it. Single-leg strength is preserved.
        if len(linked) >= 2 and news_conf >= min_confidence:
            news_part = news_score
            confidence = round(max(news_conf, 0.55), 3)
            leg = "news+tech"
        elif len(linked) >= 1:
            # Some news but lower-confidence — discount the news leg
            news_part = news_score * 0.6
            confidence = round(max(news_conf, 0.40 + 0.25 * tech_score), 3)
            leg = "tech-led"
        else:
            news_part = 0.0
            # No news → confidence climbs with technical signal strength only.
            confidence = round(0.30 + 0.40 * tech_score, 3)
            leg = "tech-only"

        # Probability-style blend: either leg firing produces a good score
        either_fires = 1.0 - (1.0 - news_part) * (1.0 - tech_score)
        # When neither leg fires meaningfully, fall back to valuation_sanity
        # as a tiny prior (0.05 floor) so totally-flat stocks still rank.
        total = round(max(0.05 * valuation_sanity, either_fires), 3)

        total = round(max(0.0, min(1.0, total)), 3)
        confidence = round(max(0.0, min(1.0, confidence)), 3)

        explanation = (
            f"[{leg}] news_conf={news_conf} relevance={relevance} sentiment={sentiment} "
            f"tech_score={tech_score} momentum={momentum} day_change={day_change} "
            f"rs_5d={round(rs_5d, 4)} liquidity={liquidity} "
            f"valuation_sanity={valuation_sanity} news_links={len(linked)}."
        )
        if confidence < min_confidence:
            explanation += f" (confidence below threshold {min_confidence})"
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
