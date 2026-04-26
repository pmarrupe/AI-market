from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.models import StockScore
from app.services.data_sources import fetch_articles, fetch_ticker_news, source_health
from app.services.explosive_radar import (
    build_explosive_radar_payload,
    build_explosive_radar_row_for_ticker,
    filter_explosive_radar_rows,
    load_explosive_radar_weights,
    mock_explosive_radar_rows,
    sort_radar_rows,
    summarize_radar_rows,
)
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
from app.services.trade_feed import build_trade_feed, sort_items
from app.services.trade_plan import compute_trade_plan
from app.services.market_data import fetch_stooq_ohlc, fetch_yfinance_ohlc, fetch_yfinance_ohlc_batch
from app.services.earnings import fetch_earnings_events, days_to_next_event
from app.services.plan_resolver import resolve_open_plans, compute_win_stats
from app.services.company_info import fetch_yfinance_company_info
from app.services.scoring import llm_enhance_scores, score_stocks
from app.services.summarizer import summarize_batch
from app.services.blend_universe import build_blend_universe
from app.services.top_performer_universe import discover_top_performer_tickers
from app.services.universe import dedupe_tickers, discover_top_tickers
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
    src = settings.universe_source
    if src == "top_performers":
        tickers = discover_top_performer_tickers(
            finnhub_enabled=settings.finnhub_enabled,
            finnhub_api_key=settings.finnhub_api_key,
            max_tickers=settings.dynamic_universe_size,
            pool_max=settings.top_performer_pool_max,
            min_price=settings.top_performer_min_price,
            fallback_tickers=settings.default_tickers,
        )
    elif src == "dynamic_llm":
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
    elif src == "static":
        tickers = settings.default_tickers
    elif src == "watchlist":
        tickers = dedupe_tickers(settings.watchlist_tickers) or settings.default_tickers
    elif src == "tracked":
        tickers = dedupe_tickers(settings.tracked_tickers) or settings.default_tickers
    elif src == "blend":
        tickers = build_blend_universe(
            watchlist_tickers=settings.watchlist_tickers,
            tracked_tickers=settings.tracked_tickers,
            default_tickers=settings.default_tickers,
            finnhub_enabled=settings.finnhub_enabled,
            finnhub_api_key=settings.finnhub_api_key,
            target_size=settings.dynamic_universe_size,
            pool_max=settings.top_performer_pool_max,
            min_price=settings.top_performer_min_price,
            exclude_etfs=settings.exclude_etfs,
            min_dollar_volume=settings.min_dollar_volume,
        )
    else:
        logger.warning("Unknown UNIVERSE_SOURCE=%r — using DEFAULT_TICKERS", src)
        tickers = settings.default_tickers

    # Apply universe-wide filters before scoring (blend mode already applied
    # them inline; for the others we apply here so the setting is universal).
    if settings.exclude_etfs and src != "blend":
        from app.services.universe_filters import filter_etfs
        before = len(tickers)
        tickers = filter_etfs(tickers)
        if before != len(tickers):
            logger.info("Filtered %d ETFs from universe", before - len(tickers))

    # Per-ticker news pass — yfinance gives ~4 fresh, ticker-tagged headlines
    # per name. This is the single biggest improvement to the news leg of
    # scoring because every ticker now has *some* coverage instead of relying
    # on the global RSS pipeline matching by keyword.
    try:
        ticker_articles = fetch_ticker_news(tickers, max_per_ticker=4)
        if ticker_articles:
            ticker_summarized = summarize_batch(
                ticker_articles,
                min_confidence=settings.summary_confidence_threshold,
                llm=llm_cfg,
                llm_max_articles=settings.llm_summary_max_articles,
            )
            # Dedupe by URL against the general pass
            existing_urls = {a.url for a in summarized}
            for a in ticker_summarized:
                if a.url not in existing_urls:
                    summarized.append(a)
                    existing_urls.add(a.url)
            logger.info(
                "Per-ticker news: fetched=%d added_after_dedup=%d",
                len(ticker_articles), len(ticker_summarized),
            )
    except Exception:
        logger.warning("Per-ticker news pass failed", exc_info=True)

    # Fetch the universe + SPY in one call; SPY is the relative-strength benchmark.
    benchmark_ticker = "SPY"
    market = fetch_market_snapshots(
        list(set(list(tickers) + [benchmark_ticker])),
        finnhub_enabled=settings.finnhub_enabled,
        finnhub_api_key=settings.finnhub_api_key,
    )
    benchmark_snapshot = market.get(benchmark_ticker)
    scores = score_stocks(
        tickers,
        summarized,
        market,
        min_confidence=settings.recommendation_confidence_threshold,
        weights=settings.scoring_weights,
        benchmark=benchmark_snapshot,
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
    use_finnhub = bool(settings.finnhub_enabled and settings.finnhub_api_key.strip())
    try:
        fh_detail = "Finnhub skipped (set FINNHUB_ENABLED=true and FINNHUB_API_KEY to try Finnhub first)" if not use_finnhub else ""
        closes: list[float] | None = None
        price_source: str | None = None
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            if use_finnhub:
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


def _explosive_radar_mock_enabled() -> bool:
    return os.getenv("EXPLOSIVE_RADAR_MOCK", "").strip().lower() in {"1", "true", "yes"}


@app.get("/api/explosive-radar/config")
def api_explosive_radar_config() -> dict[str, object]:
    weights = load_explosive_radar_weights()
    return {
        "weights": weights,
        "version": "explosive-radar-v2",
        "documentation": {
            "jumpScore": (
                "0–100 structural opportunity from volume, multi-day momentum, breakouts, gaps, and dollar volume. "
                "High jump alone can still be low quality — pair with confidence and ranked opportunity."
            ),
            "catalystScore": (
                "0–100 news/theme strength from linked headlines (sqrt-damped keyword stacking). "
                "Not verification of facts — only textual proximity to catalyst themes."
            ),
            "riskScore": (
                "0–100 failure-mode pressure: illiquidity, volatility expansion, orphan spikes, gap fades, micro dollar volume."
            ),
            "confidenceScore": (
                "0–100 how complete and cross-checkable the inputs are (bars, RVOL, dollar volume, news, agreement). "
                "Not bullish/bearish — low confidence means the jump signal is less trustworthy."
            ),
            "rankedOpportunityScore": (
                "Transparent composite ranking from weights: jump, catalyst, confidence, agreement minus risk. "
                "Tunable via ranked_* coefficients in explosive_radar_weights.json."
            ),
            "limitations": (
                "Rules-based snapshot; micro-caps and price-only spikes are penalized but not eliminated. "
                "Historical validation utility is diagnostic only, not a performance guarantee."
            ),
        },
    }


@app.get("/api/explosive-radar")
def api_explosive_radar(
    min_jump: int | None = None,
    max_risk: int | None = None,
    setup_type: str | None = None,
    sector: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    news_catalyst_only: bool = False,
    low_float_only: bool = False,
    limit: int = 100,
    sort: str | None = None,
) -> dict[str, object]:
    """
    Abnormal momentum / catalyst radar for the active scored universe (probabilistic, explainable).
    """
    weights = load_explosive_radar_weights()
    if _explosive_radar_mock_enabled():
        rows = mock_explosive_radar_rows()
        summary = summarize_radar_rows(rows, weights)
        filtered = filter_explosive_radar_rows(
            rows,
            min_jump=min_jump,
            max_risk=max_risk,
            setup_type=setup_type,
            sector=sector,
            min_price=min_price,
            max_price=max_price,
            news_catalyst_only=news_catalyst_only,
            low_float_only=low_float_only,
            float_reported_available=False,
        )[: max(1, min(limit, 200))]
        sort_radar_rows(filtered, sort)
        return {
            "disclaimer": (
                "Explosive move likelihood is a heuristic, not a prediction. "
                "MOCK payload (EXPLOSIVE_RADAR_MOCK) — not live data."
            ),
            "mock": True,
            "meta": {
                "floatReportedAvailable": False,
                "sort": (sort or "opportunity").strip().lower(),
            },
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "summary": summary,
            "items": filtered,
        }

    stocks = store.get_stock_scores(limit=100)
    articles = store.get_articles(limit=200)
    rows = build_explosive_radar_payload(
        stocks,
        articles,
        finnhub_enabled=settings.finnhub_enabled,
        finnhub_api_key=settings.finnhub_api_key,
        weights=weights,
        sort_by=sort or "opportunity",
    )
    summary = summarize_radar_rows(rows, weights)
    float_reported_available = any(
        bool((r.get("dataFlags") or {}).get("floatShares")) for r in rows
    )
    filtered = filter_explosive_radar_rows(
        rows,
        min_jump=min_jump,
        max_risk=max_risk,
        setup_type=setup_type,
        sector=sector,
        min_price=min_price,
        max_price=max_price,
        news_catalyst_only=news_catalyst_only,
        low_float_only=low_float_only,
        float_reported_available=float_reported_available,
    )[: max(1, min(limit, 200))]
    sort_radar_rows(filtered, sort)
    return {
        "disclaimer": (
            "Explosive move likelihood is a heuristic radar for abnormal breakout-style conditions, "
            "not a guarantee of future returns."
        ),
        "mock": False,
        "meta": {
            "floatReportedAvailable": float_reported_available,
            "sort": (sort or "opportunity").strip().lower(),
        },
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "summary": summary,
        "items": filtered,
    }


@app.get("/api/explosive-radar/{ticker}", response_model=None)
def api_explosive_radar_ticker(ticker: str):
    sym = (ticker or "").strip().upper()
    if not sym:
        return JSONResponse({"error": "ticker is required"}, status_code=400)
    weights = load_explosive_radar_weights()
    if _explosive_radar_mock_enabled():
        for row in mock_explosive_radar_rows():
            if row.get("ticker") == sym:
                return {
                    "disclaimer": "MOCK payload (EXPLOSIVE_RADAR_MOCK) — not live data.",
                    "mock": True,
                    "item": row,
                }
        return JSONResponse({"error": "Ticker not in mock sample (try MOCK1 or MOCK2)"}, status_code=404)

    stocks = store.get_stock_scores(limit=200)
    stock = next((s for s in stocks if s.ticker == sym), None)
    articles = store.get_articles(limit=200)
    if not stock:
        try:
            market = fetch_market_snapshots(
                [sym],
                finnhub_enabled=settings.finnhub_enabled,
                finnhub_api_key=settings.finnhub_api_key,
            )
        except Exception:
            market = {}
        snap = market.get(sym)
        if not snap or snap.last_price <= 0:
            return JSONResponse(
                {
                    "error": "Ticker not in active universe and quote unavailable.",
                    "hint": "Run refresh so the ticker is tracked, or check the symbol.",
                },
                status_code=404,
            )
        stock = StockScore(
            ticker=sym,
            price=snap.last_price,
            day_change=snap.day_change,
            score=0.0,
            confidence=0.0,
            momentum=snap.momentum_5d,
            liquidity=snap.liquidity_score,
            valuation_sanity=snap.valuation_sanity,
            sentiment=0.0,
            relevance=0.0,
            explanation="On-demand explosive radar row (not in stored universe).",
            updated_at=datetime.now(timezone.utc),
        )
        scored = score_stocks([sym], articles, market, min_confidence=0.0)
        if scored:
            stock = scored[0]

    item = build_explosive_radar_row_for_ticker(
        sym,
        stock,
        articles,
        finnhub_enabled=settings.finnhub_enabled,
        finnhub_api_key=settings.finnhub_api_key,
        weights=weights,
    )
    return {
        "disclaimer": (
            "Explosive move likelihood is a heuristic radar for abnormal breakout-style conditions, "
            "not a guarantee of future returns."
        ),
        "mock": False,
        "item": item,
    }


def _stocks_with_live_quotes(stocks: list[StockScore]) -> list[StockScore]:
    """Overlay Finnhub/Stooq snapshot on cached scores so the UI is not stuck at $0.00."""
    tickers = [s.ticker for s in stocks if s.ticker]
    if not tickers:
        return stocks
    try:
        live_map = fetch_market_snapshots(
            tickers,
            finnhub_enabled=settings.finnhub_enabled,
            finnhub_api_key=settings.finnhub_api_key,
        )
    except Exception:
        return stocks
    merged: list[StockScore] = []
    for s in stocks:
        snap = live_map.get(s.ticker)
        if snap and snap.last_price > 0:
            merged.append(
                s.model_copy(
                    update={
                        "price": snap.last_price,
                        "day_change": snap.day_change,
                        "momentum": snap.momentum_5d,
                        "liquidity": snap.liquidity_score,
                        "valuation_sanity": snap.valuation_sanity,
                    }
                )
            )
        else:
            # No fresh quote (e.g. Finnhub rate limit right after /refresh) =>
            # keep the stored price from the last scoring pass rather than zeroing.
            merged.append(s)
    return merged


@app.get("/api/dashboard")
def api_dashboard():
    """Aggregated dashboard payload consumed by the React frontend."""
    article_pool = store.get_articles(limit=180)
    stocks = _stocks_with_live_quotes(store.get_stock_scores(limit=10))
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
        "research_items": research_items,
    }


_MAX_PLANS_PER_REQUEST = 100  # high cap; batch fetch keeps this fast
_BARS_CACHE_TTL_HOURS = 12.0


def _load_bars_cached(ticker: str, *, force: bool = False) -> list[dict] | None:
    """Cached daily OHLC bars for a ticker. Tries yfinance (primary, no API key)
    then falls back to Stooq (likely dead since 2025 free-tier removal).
    Returns None if nothing works. `force=True` bypasses the cache."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    if not force:
        cached = store.get_cached_bars(sym, max_age_hours=_BARS_CACHE_TTL_HOURS)
        if cached:
            return cached
    bars = None
    source = ""
    try:
        bars = fetch_yfinance_ohlc(sym, min_rows=30)
        if bars:
            source = "yfinance"
    except Exception:
        bars = None
    if not bars:
        try:
            bars = fetch_stooq_ohlc(sym, min_rows=30)
            if bars:
                source = "stooq"
        except Exception:
            bars = None
    if bars:
        store.set_cached_bars(sym, bars, source=source)
    return bars


def _load_earnings_cached(ticker: str) -> list[dict] | None:
    """Cached upcoming earnings events for a ticker. None if unavailable."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return None
    cached = store.get_cached_earnings(sym, max_age_hours=24.0)
    if cached is not None:
        return cached
    if not settings.finnhub_enabled or not settings.finnhub_api_key:
        return None
    try:
        events = fetch_earnings_events(sym, settings.finnhub_api_key, horizon_days=120)
    except Exception:
        events = None
    if events is not None:
        store.set_cached_earnings(sym, events)
    return events


_EARNINGS_PENALTY_DAYS = 7
_DOWNGRADE = {"High": "Med", "Med": "Low", "Low": "Low"}


def _apply_earnings_penalty(items: list[dict], *, threshold_days: int = _EARNINGS_PENALTY_DAYS) -> int:
    """Downgrade conviction by one tier when earnings are within N days.
    Returns the number of items affected."""
    affected = 0
    for it in items:
        days = (it.get("earnings") or {}).get("daysToNext")
        if days is None or days > threshold_days:
            continue
        current = it.get("conviction")
        if current in _DOWNGRADE:
            new = _DOWNGRADE[current]
            if new != current:
                it["conviction"] = new
                it.setdefault("flags", []).append(f"Pre-earnings ({days}d)")
                affected += 1
    return affected


def _attach_earnings(items: list[dict], *, max_lookups: int = _MAX_PLANS_PER_REQUEST) -> int:
    """Mutate each item with an `earnings` dict. Parallelized so cold cache
    on a 50-ticker universe doesn't hang for ~30s."""
    work = items[:max_lookups]
    targets = [(idx, (it.get("ticker") or "").strip().upper()) for idx, it in enumerate(work)]
    targets = [(i, t) for i, t in targets if t]
    if not targets:
        return 0

    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout

    results: dict[str, list | None] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        future_to_sym = {ex.submit(_load_earnings_cached, t): t for _, t in targets}
        for fut in as_completed(future_to_sym):
            sym = future_to_sym[fut]
            try:
                results[sym] = fut.result(timeout=8.0)
            except (FutTimeout, Exception):
                results[sym] = None

    attached = 0
    for idx, sym in targets:
        events = results.get(sym)
        if events is None:
            continue
        days = days_to_next_event(events)
        next_event = next((e for e in events if e.get("date")), None) if events else None
        work[idx]["earnings"] = {
            "daysToNext": days,
            "nextDate": next_event["date"] if next_event else None,
            "nextHour": next_event.get("hour") if next_event else None,
            "eventCount": len(events),
        }
        attached += 1
    return attached


def _attach_trade_plans(
    items: list[dict],
    *,
    max_plans: int = _MAX_PLANS_PER_REQUEST,
    force: bool = False,
) -> int:
    """Mutate each item with a `plan` dict computed from daily bars. Returns the
    number of plans actually attached. Also persists new plans for track-record
    audit (no-op when an open plan already exists for the ticker).

    Strategy: split tickers into cached vs uncached. Batch-fetch uncached bars
    in ONE yfinance call so we don't pay N round-trips."""
    if not items:
        return 0
    work = items[:max_plans]

    bars_by_ticker: dict[str, list[dict]] = {}
    needs_fetch: list[str] = []

    for it in work:
        ticker = (it.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if not force:
            cached = store.get_cached_bars(ticker, max_age_hours=_BARS_CACHE_TTL_HOURS)
            if cached:
                bars_by_ticker[ticker] = cached
                continue
        needs_fetch.append(ticker)

    # ONE yfinance round-trip for everything uncached.
    if needs_fetch:
        try:
            fetched = fetch_yfinance_ohlc_batch(needs_fetch, min_rows=30)
        except Exception:
            fetched = {}
        for sym, bars in fetched.items():
            bars_by_ticker[sym] = bars
            try:
                store.set_cached_bars(sym, bars, source="yfinance")
            except Exception:
                pass

    attached = 0
    for it in work:
        ticker = (it.get("ticker") or "").strip().upper()
        bars = bars_by_ticker.get(ticker)
        if not bars:
            continue
        setup = it.get("setup") or ""
        breakout = "Breakout" in setup or "Gap" in setup
        plan = compute_trade_plan(bars, breakout_trigger=breakout)
        if not plan:
            continue
        # Last 60 closes for the drawer chart — keep the payload small
        recent = bars[-60:] if len(bars) > 60 else bars
        plan["recentCloses"] = [b["close"] for b in recent]
        plan["recentDates"] = [b["date"] for b in recent]
        it["plan"] = plan
        attached += 1
        if it.get("conviction") in {"High", "Med"}:
            try:
                store.record_trade_plan_if_no_open(
                    ticker=ticker,
                    entry=plan["entry"],
                    stop=plan["stop"],
                    target1=plan["target1"],
                    target2=plan["target2"],
                    atr=plan["atr14"],
                    conviction=it.get("conviction") or "",
                    setup=setup,
                )
            except Exception:
                pass
    return attached


@app.get("/api/ticker-info/{ticker}")
def api_ticker_info(ticker: str) -> dict[str, object]:
    """Company snapshot: business summary, industry, sector, market cap,
    quick links targets. Lazy-loaded by the drawer; cached 7 days."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return {"error": "ticker required"}
    cached = store.get_cached_company_info(sym, max_age_hours=168.0)
    if cached:
        return {"info": cached, "cached": True}
    info = fetch_yfinance_company_info(sym)
    if info:
        try:
            store.set_cached_company_info(sym, info)
        except Exception:
            pass
        return {"info": info, "cached": False}
    return {"info": None, "error": "no data available"}


@app.get("/api/chart/{ticker}")
def api_chart(ticker: str, period: str = "1y") -> dict[str, object]:
    """Lightweight chart endpoint — returns date+close arrays for the
    requested period. Used by the drawer's 60D / 1Y / 5Y toggle."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return {"error": "ticker required"}
    period_clean = period.strip().lower() if period else "1y"
    if period_clean not in {"60d", "6mo", "1y", "2y", "5y", "10y"}:
        period_clean = "1y"
    yf_period = {"60d": "90d"}.get(period_clean, period_clean)
    try:
        bars = fetch_yfinance_ohlc(sym, period=yf_period, min_rows=10)
    except Exception:
        bars = None
    if not bars:
        return {"ticker": sym, "period": period_clean, "closes": [], "dates": []}
    if period_clean == "60d":
        bars = bars[-60:]
    return {
        "ticker": sym,
        "period": period_clean,
        "closes": [b["close"] for b in bars],
        "dates": [b["date"] for b in bars],
    }


@app.get("/api/track-record")
def api_track_record(window_days: int = 30) -> dict[str, object]:
    """Win-rate summary for recorded trade plans. Resolves outcomes lazily on
    each call using cached bars."""
    counts = resolve_open_plans(store, load_bars_fn=_load_bars_cached)
    stats = compute_win_stats(store, since_days=window_days)
    return {
        "stats": stats,
        "resolution_counts": counts,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


@app.get("/api/trade-feed")
def api_trade_feed(
    horizon: str | None = None,
    setup: str | None = None,
    sector: str | None = None,
    conviction: str | None = None,
    sort: str = "conviction_desc",
    limit: int = 100,
    with_plans: bool = True,
    with_earnings: bool = True,
    hide_earnings_within_days: int | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Unified trade feed — merges scanner rows + radar items into one ranked list."""
    article_pool = store.get_articles(limit=180)
    stocks = _stocks_with_live_quotes(store.get_stock_scores(limit=100))
    previous_scores = store.get_previous_score_map()
    stock_market_rows = ai_stock_market_dashboard(stocks)
    opportunity = build_opportunity_view(
        stocks=stocks,
        articles=article_pool,
        previous_scores=previous_scores,
        stock_market_rows=stock_market_rows,
    )

    weights = load_explosive_radar_weights()
    if _explosive_radar_mock_enabled():
        radar_items = mock_explosive_radar_rows()
    else:
        radar_items = build_explosive_radar_payload(
            stocks,
            article_pool,
            finnhub_enabled=settings.finnhub_enabled,
            finnhub_api_key=settings.finnhub_api_key,
            weights=weights,
            sort_by="opportunity",
        )

    payload = build_trade_feed(
        scanner_rows=opportunity["rows"],
        radar_items=radar_items,
        horizon=horizon,
        setup=setup,
        sector=sector,
        conviction=conviction,
        sort=sort,
        limit=limit,
    )

    plans_attached = 0
    if with_plans:
        plans_attached = _attach_trade_plans(payload.get("items") or [], force=force)
    earnings_attached = 0
    if with_earnings:
        earnings_attached = _attach_earnings(payload.get("items") or [])

    # Apply earnings penalty AFTER attach (needs daysToNext) and BEFORE the
    # hide filter (so an explicit "hide earnings" still works on the raw set).
    earnings_penalized = _apply_earnings_penalty(payload.get("items") or [])

    if hide_earnings_within_days is not None and hide_earnings_within_days > 0:
        kept: list[dict] = []
        for it in payload.get("items") or []:
            e = it.get("earnings") or {}
            days = e.get("daysToNext")
            if days is not None and days <= hide_earnings_within_days:
                continue
            kept.append(it)
        payload["items"] = kept

    # Re-sort after penalty + plan/volume attach so rankings reflect the
    # quality_score that now includes relative volume + R:R.
    sort_items(payload.get("items") or [], sort=sort)

    payload.setdefault("summary", {})
    payload["summary"]["plansAttached"] = plans_attached
    payload["summary"]["earningsAttached"] = earnings_attached
    payload["summary"]["earningsPenalized"] = earnings_penalized

    payload["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    payload["disclaimer"] = (
        "Unified research view merging scanner + radar. Not personalized investment advice."
    )
    return payload


@app.get("/api/portfolio")
def api_portfolio(tickers: str = "") -> dict[str, object]:
    """Enrich an arbitrary list of tickers with current price + conviction + plan
    + earnings. Stateless — positions live in the client's localStorage."""
    raw = [t.strip().upper() for t in (tickers or "").split(",") if t.strip()]
    wanted = list(dict.fromkeys(raw))  # dedupe, preserve order
    if not wanted:
        return {"items": [], "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}

    article_pool = store.get_articles(limit=180)
    stocks = _stocks_with_live_quotes(store.get_stock_scores(limit=100))
    previous_scores = store.get_previous_score_map()
    stock_market_rows = ai_stock_market_dashboard(stocks)
    opportunity = build_opportunity_view(
        stocks=stocks,
        articles=article_pool,
        previous_scores=previous_scores,
        stock_market_rows=stock_market_rows,
    )
    weights = load_explosive_radar_weights()
    if _explosive_radar_mock_enabled():
        radar_items = mock_explosive_radar_rows()
    else:
        radar_items = build_explosive_radar_payload(
            stocks,
            article_pool,
            finnhub_enabled=settings.finnhub_enabled,
            finnhub_api_key=settings.finnhub_api_key,
            weights=weights,
            sort_by="opportunity",
        )
    feed = build_trade_feed(
        scanner_rows=opportunity["rows"],
        radar_items=radar_items,
        limit=500,
    )
    by_ticker = {it.get("ticker"): it for it in feed.get("items") or []}

    # Any wanted tickers not in the feed: fetch a live quote so we can still
    # show current price and P&L.
    missing = [t for t in wanted if t not in by_ticker]
    live_snapshots: dict = {}
    if missing:
        try:
            live_snapshots = fetch_market_snapshots(
                missing,
                finnhub_enabled=settings.finnhub_enabled,
                finnhub_api_key=settings.finnhub_api_key,
            )
        except Exception:
            live_snapshots = {}

    items: list[dict] = []
    for t in wanted:
        it = by_ticker.get(t)
        if it is None:
            snap = live_snapshots.get(t)
            it = {
                "ticker": t,
                "company": None,
                "sector": None,
                "price": snap.last_price if snap and snap.last_price > 0 else None,
                "conviction": "—",
                "horizon": "Unclear",
                "setup": "Off-feed",
                "flags": ["No coverage"],
                "topReason": "Not in the active scored universe — showing live price only.",
                "sources": [],
            }
        items.append(it)

    _attach_trade_plans(items, max_plans=len(items))
    _attach_earnings(items, max_lookups=len(items))

    return {
        "items": items,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "disclaimer": (
            "Position snapshots for the tickers you passed. P&L is computed client-side from your cost basis."
        ),
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
