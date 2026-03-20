from __future__ import annotations

import json
import logging
import time

import httpx
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.data_sources import fetch_articles, source_health
from app.services.dashboards import (
    ai_product_launch_tracker,
    ai_research_dashboard,
    ai_startup_funding_tracker,
    ai_stock_market_dashboard,
)
from app.services.sp500 import search_sp500, get_sp500_entry
from app.services.llm import llm_json_completion
from app.services.market_data import fetch_market_snapshots, fetch_stooq_daily_closes_for_forecast
from app.services.price_forecast import (
    MIN_CLOSES_FORECAST,
    build_price_forecast,
    fetch_finnhub_daily_series_with_detail,
)
from app.services.opportunity_signals import build_opportunity_view
from app.services.scoring import llm_enhance_scores, score_stocks
from app.services.summarizer import summarize_batch
from app.services.universe import discover_top_tickers
from app.store import Store

settings = get_settings()
store = Store(settings.database_path)
templates = Jinja2Templates(directory="app/templates")
app = FastAPI(title="AI Market Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

REACT_BUILD_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)


def _watchlist_alerts(stocks, watchlist_tickers, score_threshold: float, sentiment_threshold: float):
    return _watchlist_alerts_with_delta(
        stocks, watchlist_tickers, {}, score_threshold, sentiment_threshold, 1.0
    )


def _watchlist_alerts_with_delta(
    stocks,
    watchlist_tickers,
    previous_scores: dict[str, float],
    score_threshold: float,
    sentiment_threshold: float,
    delta_threshold: float,
):
    watchset = {ticker.upper() for ticker in watchlist_tickers}
    alerts = []
    for stock in stocks:
        if stock.ticker not in watchset:
            continue
        reasons = []
        previous_score = previous_scores.get(stock.ticker)
        delta = None
        if previous_score is not None:
            delta = round(stock.score - previous_score, 3)
        if stock.score >= score_threshold:
            reasons.append(f"score {stock.score:.3f} >= {score_threshold:.3f}")
        if abs(stock.sentiment) >= sentiment_threshold:
            reasons.append(
                f"abs(sentiment) {abs(stock.sentiment):.3f} >= {sentiment_threshold:.3f}"
            )
        if delta is not None and abs(delta) >= delta_threshold:
            reasons.append(f"score delta {delta:+.3f} exceeds {delta_threshold:.3f}")
        if reasons:
            alerts.append(
                {
                    "ticker": stock.ticker,
                    "reason": "; ".join(reasons),
                    "score": stock.score,
                    "score_delta": delta,
                    "sentiment": stock.sentiment,
                    "updated_at": stock.updated_at,
                }
            )
    return alerts


def _analyst_cards(stocks, articles):
    cards = []
    for stock in stocks[:5]:
        linked = [a for a in articles if stock.ticker in a.tickers][:3]
        headlines = [a.title for a in linked]
        if stock.score <= 0:
            thesis = "Insufficient evidence to form a positive stock thesis."
        elif stock.relevance >= 0.6 and stock.sentiment > 0:
            thesis = "Strong AI-news linkage with positive tone supports near-term attention."
        elif stock.relevance >= 0.5:
            thesis = "Moderate AI-news linkage, but confirmation is still developing."
        else:
            thesis = "Weak direct linkage to current AI news cycle."
        uncertainties = []
        if stock.confidence < 0.55:
            uncertainties.append("Evidence confidence remains moderate/low.")
        if abs(stock.momentum) > 0.12:
            uncertainties.append("Recent momentum is elevated and may mean-revert.")
        if not headlines:
            uncertainties.append("No directly linked headlines in current snapshot.")
        if not uncertainties:
            uncertainties.append("No critical flags detected in current ruleset.")
        cards.append(
            {
                "ticker": stock.ticker,
                "score": stock.score,
                "thesis": thesis,
                "evidence": headlines,
                "confidence": stock.confidence,
                "uncertainties": uncertainties,
            }
        )
    return cards


def _industry_map(stock_market_rows):
    groups: dict[str, dict[str, object]] = {}
    for row in stock_market_rows:
        sector = row["sector"]
        if sector not in groups:
            groups[sector] = {"sector": sector, "tickers": [], "avg_score": 0.0, "count": 0}
        groups[sector]["tickers"].append(row["ticker"])
        groups[sector]["avg_score"] += float(row["score"])
        groups[sector]["count"] += 1
    out = []
    for sector_data in groups.values():
        count = max(1, int(sector_data["count"]))
        avg_score = round(float(sector_data["avg_score"]) / count, 3)
        out.append(
            {
                "sector": sector_data["sector"],
                "tickers": sector_data["tickers"],
                "avg_score": avg_score,
            }
        )
    out.sort(key=lambda x: x["avg_score"], reverse=True)
    return out


def refresh_data() -> dict[str, object]:
    started = time.perf_counter()
    llm_cfg = {
        "enabled": settings.llm_enabled,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "score_system_prompt": settings.llm_score_system_prompt,
        "score_user_prompt_prefix": settings.llm_score_user_prompt_prefix,
        "summary_system_prompt": settings.llm_summary_system_prompt,
        "summary_user_prompt_suffix": settings.llm_summary_user_prompt_suffix,
    }
    health_rows = source_health(
        settings.news_feeds,
        newsapi_enabled=settings.newsapi_enabled,
        newsapi_api_key=settings.newsapi_api_key,
        finnhub_enabled=settings.finnhub_enabled,
        finnhub_api_key=settings.finnhub_api_key,
    )
    fetched = fetch_articles(
        settings.news_feeds,
        max_per_feed=12,
        newsapi_enabled=settings.newsapi_enabled,
        newsapi_api_key=settings.newsapi_api_key,
        finnhub_enabled=settings.finnhub_enabled,
        finnhub_api_key=settings.finnhub_api_key,
    )
    summarized = summarize_batch(
        fetched,
        min_confidence=settings.summary_confidence_threshold,
        llm=llm_cfg,
        llm_max_articles=settings.llm_summary_max_articles,
    )
    if settings.dynamic_universe_enabled:
        previous_universe = [score.ticker for score in store.get_stock_scores(limit=100)]
        tickers = discover_top_tickers(
            summarized,
            llm=llm_cfg,
            fallback_tickers=settings.default_tickers,
            max_tickers=settings.dynamic_universe_size,
            previous_tickers=previous_universe,
            blend_fallback=settings.dynamic_universe_blend_fallback,
            explore_mode=settings.dynamic_universe_explore_mode,
            min_fresh_tickers=settings.dynamic_universe_min_fresh,
        )
    else:
        tickers = settings.default_tickers
    market = fetch_market_snapshots(
        tickers,
        finnhub_enabled=settings.finnhub_enabled,
        finnhub_api_key=settings.finnhub_api_key,
    )
    scores = score_stocks(
        tickers,
        summarized,
        market,
        min_confidence=settings.recommendation_confidence_threshold,
        weights=settings.scoring_weights,
    )
    scores = llm_enhance_scores(scores, summarized, llm=llm_cfg)
    store.upsert_articles(summarized)
    store.replace_stock_scores(scores)
    store.append_recommendation_audit(scores, summarized, model_version=settings.scoring_model_version)
    store.append_source_health(health_rows)
    elapsed_s = round(time.perf_counter() - started, 2)
    logger.info(
        "Refresh complete: articles=%s stocks=%s sources=%s universe=%s elapsed_s=%s",
        len(summarized),
        len(scores),
        len(health_rows),
        ",".join(tickers),
        elapsed_s,
    )
    return {
        "articles": len(summarized),
        "stocks": len(scores),
        "sources": len(health_rows),
        "universe_size": len(tickers),
        "universe": tickers,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/refresh")
def refresh() -> dict[str, object]:
    return refresh_data()


@app.get("/api/articles")
def api_articles(limit: int = 25):
    return store.get_articles(limit=limit)


@app.get("/api/stocks")
def api_stocks(limit: int = 10):
    return store.get_stock_scores(limit=limit)


@app.get("/api/innovations")
def api_innovations(limit: int = 10):
    articles = store.get_articles(limit=50)
    return ai_product_launch_tracker(articles, limit=limit)


@app.get("/api/alerts")
def api_alerts():
    stocks = store.get_stock_scores(limit=100)
    previous_scores = store.get_previous_score_map()
    return _watchlist_alerts_with_delta(
        stocks,
        settings.watchlist_tickers,
        previous_scores,
        settings.alert_score_threshold,
        settings.alert_sentiment_threshold,
        settings.alert_delta_threshold,
    )


@app.get("/api/watchlist-briefing")
def api_watchlist_briefing():
    """
    AI-generated briefing for the configured watchlist tickers.

    Uses the existing opportunity view as structured input to the LLM and
    returns a compact summary plus per-ticker notes.
    """
    watchlist = [ticker.upper() for ticker in settings.watchlist_tickers]
    if not watchlist:
        return {
            "tickers": [],
            "summary": "No watchlist configured yet.",
            "items": [],
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }

    article_pool = store.get_articles(limit=180)
    stocks = store.get_stock_scores(limit=100)
    previous_scores = store.get_previous_score_map()
    opportunity = build_opportunity_view(
        stocks=stocks,
        articles=article_pool,
        previous_scores=previous_scores,
        stock_market_rows=ai_stock_market_dashboard(stocks),
    )

    rows = [
        row
        for row in opportunity["rows"]
        if row.get("ticker", "").upper() in watchlist
    ]

    def _fallback_response() -> dict[str, object]:
        """Deterministic fallback if there is no LLM or it fails."""
        if not rows:
            return {
                "tickers": watchlist,
                "summary": "No current scores for watchlist tickers in the active universe.",
                "items": [],
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            }
        sorted_rows = sorted(rows, key=lambda r: r.get("opportunityRank", 9999))
        top = sorted_rows[: min(3, len(sorted_rows))]
        summary = (
            "Watchlist overview based on current scores and signals. "
            f"Top names today: {', '.join(r['ticker'] for r in top)}."
        )
        items = []
        for row in sorted_rows:
            items.append(
                {
                    "ticker": row["ticker"],
                    "stance": row.get("status") or row.get("signalLabel") or "Watchlist",
                    "rationale": row.get("recommendationNote") or row.get("aiSummary") or "",
                    "key_risks": [],
                }
            )
        return {
            "tickers": watchlist,
            "summary": summary,
            "items": items,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }

    if not settings.llm_enabled or not settings.llm_api_key:
        return _fallback_response()

    system_prompt = (
        "You are a buy-side analyst creating a concise watchlist briefing for a portfolio owner. "
        "You will receive structured JSON rows for several tickers. "
        "Return strict JSON with keys: summary (string) and items (array). "
        "Each item must be {ticker, stance, rationale, key_risks}. "
        "stance is a short label like 'Actionable', 'Watch', or 'High risk'. "
        "rationale is 2-3 short sentences grounded only in the provided data. "
        "key_risks is an array of 1-3 short bullet phrases, or [] if nothing material."
    )

    user_payload = {
        "watchlist_tickers": watchlist,
        "rows": rows,
    }
    user_prompt = (
        "User watchlist tickers:\n"
        f"{', '.join(watchlist)}\n\n"
        "Structured data for each ticker (JSON):\n"
        f"{json.dumps(user_payload, default=str)}\n\n"
        "Generate a concise briefing focused on near-term opportunity and risk."
    )

    llm_out = llm_json_completion(
        enabled=settings.llm_enabled,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=min(settings.llm_max_tokens, 800),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    if not llm_out:
        return _fallback_response()

    summary = str(llm_out.get("summary") or "").strip()
    items = llm_out.get("items") or []
    if not summary or not isinstance(items, list):
        return _fallback_response()

    normalized_items: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").upper()
        if not ticker:
            continue
        normalized_items.append(
            {
                "ticker": ticker,
                "stance": str(item.get("stance") or "").strip() or "Watchlist",
                "rationale": str(item.get("rationale") or "").strip(),
                "key_risks": item.get("key_risks") if isinstance(item.get("key_risks"), list) else [],
            }
        )
    if not normalized_items:
        return _fallback_response()

    return {
        "tickers": watchlist,
        "summary": summary,
        "items": normalized_items,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


@app.get("/api/audit")
def api_audit(limit: int = 100):
    return store.get_recommendation_audit(limit=limit)


@app.get("/api/source-health")
def api_source_health(limit: int = 50):
    return store.get_source_health(limit=limit)


@app.get("/api/startup-funding")
def api_startup_funding(limit: int = 12):
    articles = store.get_articles(limit=120)
    return ai_startup_funding_tracker(articles, limit=limit)


@app.get("/api/product-launches")
def api_product_launches(limit: int = 12):
    articles = store.get_articles(limit=120)
    return ai_product_launch_tracker(articles, limit=limit)


@app.get("/api/ai-stock-dashboard")
def api_ai_stock_dashboard(limit: int = 20):
    stocks = store.get_stock_scores(limit=limit)
    return ai_stock_market_dashboard(stocks)


@app.get("/api/top-stocks")
def api_top_stocks(limit: int = 8):
    scores = store.get_stock_scores(limit=100)
    scores.sort(key=lambda s: s.score, reverse=True)
    top = scores[: max(1, min(limit, 20))]
    return [
        {
            "ticker": s.ticker,
            "score": s.score,
            "sentiment": s.sentiment,
            "sector": next(
                (row["sector"] for row in ai_stock_market_dashboard([s])),  # simple reuse
                "Other",
            ),
        }
        for s in top
    ]


@app.get("/api/price-forecast")
def api_price_forecast(ticker: str):
    """
    Empirical forward outlook from Finnhub daily history: P(up) and median-implied price
    at 10 / 20 / 30 trading-day horizons. Not investment advice.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return JSONResponse({"error": "ticker is required"}, status_code=400)
    if not settings.finnhub_enabled or not settings.finnhub_api_key.strip():
        return JSONResponse(
            {
                "error": "Finnhub required: set FINNHUB_ENABLED=true and FINNHUB_API_KEY in .env",
            },
            status_code=503,
        )
    try:
        fh_detail = ""
        closes: list[float] | None = None
        price_source: str | None = None
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            series, fh_detail = fetch_finnhub_daily_series_with_detail(
                sym,
                settings.finnhub_api_key.strip(),
                client=client,
                lookback_days=550,
                min_closes=MIN_CLOSES_FORECAST,
            )
            if series:
                closes = list(series[0])
                price_source = "finnhub"
            if not closes:
                closes = fetch_stooq_daily_closes_for_forecast(
                    sym, client, min_closes=MIN_CLOSES_FORECAST
                )
                if closes:
                    price_source = "stooq"
        if not closes:
            return JSONResponse(
                {
                    "error": "No usable daily history for price forecast.",
                    "finnhub_detail": fh_detail or None,
                    "hint": (
                        "Finnhub /stock/candle often returns no_data on free accounts. "
                        "This endpoint falls back to Stooq; if both fail, check the ticker (US: NVDA) "
                        "and your Finnhub key at finnhub.io."
                    ),
                },
                status_code=404,
            )
        body = build_price_forecast(closes)
        # Optional simple "stance" from prob_up + confidence (still not a buy recommendation)
        enriched_horizons = []
        for h in body.get("horizons", []):
            row = dict(h)
            pu = row.get("prob_up")
            conf = row.get("confidence") or 0.0
            if pu is not None and conf >= 0.55 and pu >= 0.58:
                row["outlook_label"] = "historically skewed positive (weak signal)"
            elif pu is not None and conf >= 0.55 and pu <= 0.42:
                row["outlook_label"] = "historically skewed negative (weak signal)"
            else:
                row["outlook_label"] = "no strong historical skew"
            enriched_horizons.append(row)
        body["horizons"] = enriched_horizons
        return {
            "ticker": sym,
            "data_source": price_source,
            "disclaimer": (
                "Research only — not investment advice. Based on past daily returns; "
                "does not predict actual future prices."
            ),
            **body,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("price-forecast failed for %s: %s", sym, exc)
        return JSONResponse(
            {"error": f"Finnhub or forecast error: {exc!s}"},
            status_code=502,
        )


@app.get("/api/sp500/search")
def api_sp500_search(q: str, limit: int = 8):
    return search_sp500(q, limit=limit)


@app.get("/api/sp500/opinion")
def api_sp500_opinion(ticker: str):
    entry = get_sp500_entry(ticker)
    if not entry:
        return {"error": "Ticker not in S&P universe"}
    upper = entry["ticker"]
    is_tracked = False

    scores = store.get_stock_scores(limit=200)
    score = next((s for s in scores if s.ticker == upper), None)
    if score:
        is_tracked = True

    articles = store.get_articles(limit=180)

    if not score:
        try:
            market = fetch_market_snapshots(
                [upper],
                finnhub_enabled=settings.finnhub_enabled,
                finnhub_api_key=settings.finnhub_api_key,
            )
        except Exception:
            market = {}
        scored = score_stocks([upper], articles, market, min_confidence=0.0)
        score = scored[0] if scored else None

    if not score:
        return {
            "ticker": upper,
            "name": entry["name"],
            "sector": entry["sector"],
            "score": 0.0,
            "sentiment": 0.0,
            "confidence": 0.0,
            "price": 0.0,
            "day_change": 0.0,
            "momentum": 0.0,
            "thesis": "Unable to retrieve market data for this ticker right now.",
            "uncertainties": ["Market data source may be temporarily unavailable."],
            "headlines": [],
        }

    # Always refresh quote for display (stored scores may be stale or from old placeholder logic).
    try:
        live = fetch_market_snapshots(
            [upper],
            finnhub_enabled=settings.finnhub_enabled,
            finnhub_api_key=settings.finnhub_api_key,
        ).get(upper)
    except Exception:
        live = None
    if live and live.last_price > 0:
        score = score.model_copy(
            update={
                "price": live.last_price,
                "day_change": live.day_change,
                "momentum": live.momentum_5d,
                "liquidity": live.liquidity_score,
                "valuation_sanity": live.valuation_sanity,
            }
        )
    else:
        # Do not trust cached price if live fetch failed (avoids showing old fake placeholder quotes).
        score = score.model_copy(
            update={
                "price": 0.0,
                "day_change": 0.0,
                "momentum": 0.0,
            }
        )

    linked = [a for a in articles if score.ticker in a.tickers][:5]
    headlines = [a.title for a in linked]
    has_news = len(linked) > 0

    llm_cfg = {
        "enabled": settings.llm_enabled,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }

    llm_opinion = _llm_stock_opinion(
        llm=llm_cfg,
        ticker=upper,
        name=entry["name"],
        sector=entry["sector"],
        score=score,
        headlines=headlines,
        is_tracked=is_tracked,
    )

    if llm_opinion:
        thesis = llm_opinion.get("thesis", "")
        uncertainties = llm_opinion.get("uncertainties", [])
        signal = llm_opinion.get("signal", "")
    else:
        thesis = _build_opinion_thesis(score, has_news, is_tracked)
        uncertainties = _build_opinion_uncertainties(score, has_news, is_tracked)
        signal = ""

    result = {
        "ticker": upper,
        "name": entry["name"],
        "sector": entry["sector"],
        "score": score.score,
        "sentiment": score.sentiment,
        "confidence": score.confidence,
        "price": score.price,
        "day_change": score.day_change,
        "momentum": score.momentum,
        "liquidity": score.liquidity,
        "relevance": score.relevance,
        "thesis": thesis,
        "uncertainties": uncertainties,
        "headlines": headlines,
    }
    if signal:
        result["signal"] = signal
    return result


def _llm_stock_opinion(
    *,
    llm: dict,
    ticker: str,
    name: str,
    sector: str,
    score,
    headlines: list[str],
    is_tracked: bool,
) -> dict | None:
    """Ask the LLM for a rich analytical opinion on a single stock."""
    if not llm.get("enabled") or not llm.get("api_key"):
        return None

    context = {
        "ticker": ticker,
        "company": name,
        "sector": sector,
        "price": score.price,
        "day_change_pct": round(score.day_change * 100, 2),
        "momentum_5d_pct": round(score.momentum * 100, 2),
        "ai_score": score.score,
        "sentiment": score.sentiment,
        "confidence": score.confidence,
        "relevance": score.relevance,
        "liquidity": score.liquidity,
        "valuation_sanity": score.valuation_sanity,
        "is_actively_tracked": is_tracked,
        "linked_headlines": headlines,
    }

    system_prompt = (
        "You are a senior equity research analyst specializing in AI and technology stocks. "
        "You write concise, actionable analysis grounded in the data provided. "
        "Return strict JSON with these keys:\n"
        '- "thesis": a 2-4 sentence analytical thesis covering price action, momentum, '
        "AI-sector relevance, and outlook. Be specific to THIS stock.\n"
        '- "signal": one of "Bullish", "Cautiously Bullish", "Neutral", "Cautiously Bearish", "Bearish"\n'
        '- "uncertainties": an array of 1-3 short risk factors or caveats (one sentence each)\n'
        "Do not hallucinate facts. If data is limited, say so honestly. "
        "Base your analysis only on the provided metrics and headlines."
    )

    user_prompt = (
        f"Analyze {ticker} ({name}) in the {sector} sector.\n\n"
        f"Market data & scores:\n{json.dumps(context, indent=2)}\n\n"
        "Provide your analysis."
    )

    try:
        result = llm_json_completion(
            enabled=True,
            api_key=llm["api_key"],
            base_url=llm.get("base_url", "https://api.openai.com/v1"),
            model=llm.get("model", "gpt-4o-mini"),
            temperature=llm.get("temperature", 0.3),
            max_tokens=llm.get("max_tokens", 400),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        if not result or "thesis" not in result:
            return None
        return {
            "thesis": str(result["thesis"]),
            "signal": str(result.get("signal", "")),
            "uncertainties": [str(u) for u in result.get("uncertainties", [])],
        }
    except Exception:
        return None


def _build_opinion_thesis(score, has_news: bool, is_tracked: bool) -> str:
    parts = []

    if score.price > 0:
        pct = score.day_change * 100
        direction = "up" if pct > 0 else "down" if pct < 0 else "flat"
        parts.append(f"Trading at ${score.price:.2f}, {direction} {abs(pct):.2f}% today.")

    mom = score.momentum
    if abs(mom) >= 0.03:
        trend = "positive" if mom > 0 else "negative"
        parts.append(f"5-day momentum is {trend} at {mom*100:+.1f}%.")
    elif score.price > 0:
        parts.append("5-day momentum is neutral.")

    if has_news and score.relevance >= 0.6 and score.sentiment > 0:
        parts.append(
            "Strong AI-news linkage with positive tone supports monitoring this name."
        )
    elif has_news and score.relevance >= 0.5:
        parts.append("Moderate AI linkage; signals are promising but need confirmation.")
    elif has_news:
        parts.append("Some AI-related news coverage exists but linkage is limited.")
    elif is_tracked:
        parts.append("No AI headlines linked in the current news snapshot.")
    else:
        parts.append(
            "This ticker is not in the actively tracked universe. "
            "Analysis is based on market data and any incidental news mentions."
        )

    if score.liquidity >= 0.7:
        parts.append("Liquidity is strong.")
    elif score.liquidity >= 0.4:
        parts.append("Liquidity is moderate.")

    return " ".join(parts)


def _build_opinion_uncertainties(score, has_news: bool, is_tracked: bool) -> list[str]:
    items = []
    if not is_tracked:
        items.append(
            "Not in the actively tracked universe — score is computed on-demand "
            "with limited data."
        )
    if score.confidence < 0.55:
        items.append("Evidence confidence is moderate/low.")
    if abs(score.momentum) > 0.12:
        items.append("Recent momentum is elevated and may mean-revert.")
    if not has_news:
        items.append("No directly linked AI headlines in the current snapshot.")
    if not items:
        items.append("No critical flags detected in current ruleset.")
    return items


@app.get("/api/research")
def api_research(limit: int = 12):
    articles = store.get_articles(limit=120)
    return ai_research_dashboard(articles, limit=limit)


@app.get("/api/analysis-cards")
def api_analysis_cards(limit: int = 5):
    stocks = store.get_stock_scores(limit=20)
    articles = store.get_articles(limit=80)
    return _analyst_cards(stocks[:limit], articles)


@app.get("/api/dashboard")
def api_dashboard():
    """Aggregated dashboard payload consumed by the React frontend."""
    article_pool = store.get_articles(limit=180)
    stocks = store.get_stock_scores(limit=10)
    previous_scores = store.get_previous_score_map()
    startup_funding = ai_startup_funding_tracker(article_pool, limit=8)
    product_launches = ai_product_launch_tracker(article_pool, limit=8)
    stock_market_rows = ai_stock_market_dashboard(stocks)
    opportunity = build_opportunity_view(
        stocks=stocks,
        articles=article_pool,
        previous_scores=previous_scores,
        stock_market_rows=stock_market_rows,
    )
    industry_map = _industry_map(stock_market_rows)
    research_items = ai_research_dashboard(article_pool, limit=8)
    return {
        "stocks": [s.__dict__ if hasattr(s, "__dict__") else s for s in stocks],
        "startup_funding": startup_funding,
        "product_launches": product_launches,
        "stock_market_rows": stock_market_rows,
        "stock_rows": opportunity["rows"],
        "stock_summary": opportunity["summary"],
        "stock_sectors": opportunity["sectors"],
        "stock_signal_labels": opportunity["signal_labels"],
        "stock_risk_levels": opportunity["risk_levels"],
        "stock_time_horizons": opportunity["time_horizons"],
        "stock_statuses": opportunity["statuses"],
        "industry_map": industry_map,
        "research_items": research_items,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Serve React SPA if built, otherwise fall back to Jinja2 template."""
    react_index = REACT_BUILD_DIR / "index.html"
    if react_index.exists():
        return FileResponse(react_index)

    article_pool = store.get_articles(limit=180)
    stocks = store.get_stock_scores(limit=10)
    previous_scores = store.get_previous_score_map()
    alerts = _watchlist_alerts_with_delta(
        stocks,
        settings.watchlist_tickers,
        previous_scores,
        settings.alert_score_threshold,
        settings.alert_sentiment_threshold,
        settings.alert_delta_threshold,
    )
    analysis_cards = _analyst_cards(stocks, store.get_articles(limit=80))
    startup_funding = ai_startup_funding_tracker(article_pool, limit=8)
    product_launches = ai_product_launch_tracker(article_pool, limit=8)
    stock_market_rows = ai_stock_market_dashboard(stocks)
    opportunity = build_opportunity_view(
        stocks=stocks,
        articles=article_pool,
        previous_scores=previous_scores,
        stock_market_rows=stock_market_rows,
    )
    industry_map = _industry_map(stock_market_rows)
    research_items = ai_research_dashboard(article_pool, limit=8)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "articles": store.get_articles(limit=20),
            "stocks": stocks,
            "alerts": alerts,
            "watchlist_tickers": settings.watchlist_tickers,
            "analysis_cards": analysis_cards,
            "startup_funding": startup_funding,
            "product_launches": product_launches,
            "stock_market_rows": stock_market_rows,
            "stock_rows": opportunity["rows"],
            "stock_summary": opportunity["summary"],
            "top_picks": opportunity["top3"],
            "stock_sectors": opportunity["sectors"],
            "stock_signal_labels": opportunity["signal_labels"],
            "stock_risk_levels": opportunity["risk_levels"],
            "stock_time_horizons": opportunity["time_horizons"],
            "stock_statuses": opportunity["statuses"],
            "industry_map": industry_map,
            "research_items": research_items,
        },
    )


# Serve React static assets, PWA manifest, and icons when the build exists
if REACT_BUILD_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_BUILD_DIR / "assets")), name="react-assets")
    icons_dir = REACT_BUILD_DIR / "icons"
    if icons_dir.exists():
        app.mount("/icons", StaticFiles(directory=str(icons_dir)), name="pwa-icons")


@app.get("/manifest.webmanifest")
def manifest():
    """Serve PWA manifest for Add to Home Screen (no-cost app install)."""
    path = REACT_BUILD_DIR / "manifest.webmanifest"
    if path.exists():
        return FileResponse(path, media_type="application/manifest+json")
    return JSONResponse({"error": "not found"}, status_code=404)
