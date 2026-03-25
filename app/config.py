from __future__ import annotations

import os
import json
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_path: str
    refresh_interval_minutes: int
    news_feeds: list[str]
    default_tickers: list[str]
    scoring_weights: dict
    summary_confidence_threshold: float
    recommendation_confidence_threshold: float
    scoring_model_version: str
    watchlist_tickers: list[str]
    tracked_tickers: list[str]
    alert_score_threshold: float
    alert_sentiment_threshold: float
    alert_delta_threshold: float
    llm_enabled: bool
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    llm_temperature: float
    llm_max_tokens: int
    llm_summary_max_articles: int
    llm_score_system_prompt: str
    llm_score_user_prompt_prefix: str
    llm_summary_system_prompt: str
    llm_summary_user_prompt_suffix: str
    universe_source: str
    dynamic_universe_enabled: bool
    dynamic_universe_size: int
    dynamic_universe_explore_mode: bool
    dynamic_universe_blend_fallback: bool
    dynamic_universe_min_fresh: int
    top_performer_pool_max: int
    top_performer_min_price: float
    newsapi_enabled: bool
    newsapi_api_key: str
    finnhub_enabled: bool
    finnhub_api_key: str
    cors_origins: list[str]
    host: str
    port: int
    workers: int


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    return Settings(
        database_path=os.getenv("DATABASE_PATH", "./ai_market.db"),
        refresh_interval_minutes=int(os.getenv("REFRESH_INTERVAL_MINUTES", "60")),
        news_feeds=_split_csv(
            os.getenv(
                "NEWS_FEEDS",
                "https://techcrunch.com/category/artificial-intelligence/feed/,"
                "https://openai.com/news/rss.xml,"
                "https://blog.google/technology/ai/rss/,"
                "https://feeds.bloomberg.com/technology/news.rss,"
                "https://export.arxiv.org/rss/cs.AI",
            )
        ),
        default_tickers=_split_csv(
            os.getenv(
                "DEFAULT_TICKERS",
                # Fallback / safety list when Finnhub movers fail (keep short).
                "SPY,QQQ,NVDA,MSFT",
            )
        ),
        universe_source=os.getenv("UNIVERSE_SOURCE", "blend").strip().lower(),
        scoring_weights=json.loads(
            os.getenv(
                "SCORING_WEIGHTS_JSON",
                '{"relevance": 0.35, "sentiment": 0.20, "momentum": 0.20, "liquidity": 0.15, "valuation_sanity": 0.10}',
            )
        ),
        summary_confidence_threshold=float(os.getenv("SUMMARY_CONFIDENCE_THRESHOLD", "0.35")),
        recommendation_confidence_threshold=float(
            os.getenv("RECOMMENDATION_CONFIDENCE_THRESHOLD", "0.45")
        ),
        scoring_model_version=os.getenv("SCORING_MODEL_VERSION", "scoring-v1.1"),
        watchlist_tickers=_split_csv(os.getenv("WATCHLIST_TICKERS", "NVDA,MSFT,GOOGL")),
        tracked_tickers=_split_csv(os.getenv("TRACKED_TICKERS", "")),
        alert_score_threshold=float(os.getenv("ALERT_SCORE_THRESHOLD", "0.55")),
        alert_sentiment_threshold=float(os.getenv("ALERT_SENTIMENT_THRESHOLD", "0.35")),
        alert_delta_threshold=float(os.getenv("ALERT_DELTA_THRESHOLD", "0.08")),
        llm_enabled=_as_bool(os.getenv("LLM_ENABLED"), default=False),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "500")),
        llm_summary_max_articles=int(os.getenv("LLM_SUMMARY_MAX_ARTICLES", "8")),
        llm_score_system_prompt=os.getenv(
            "LLM_SCORE_SYSTEM_PROMPT",
            (
                "You are a quant research assistant. Return JSON with key 'adjustments'. "
                "adjustments is an array of objects: {ticker, delta, note}. "
                "delta must be between -0.15 and 0.15 and should be 0 when evidence is weak."
            ),
        ),
        llm_score_user_prompt_prefix=os.getenv(
            "LLM_SCORE_USER_PROMPT_PREFIX",
            "Review these computed stock scores and linked headlines. Apply small quality adjustments only when well supported.\n\n",
        ),
        llm_summary_system_prompt=os.getenv(
            "LLM_SUMMARY_SYSTEM_PROMPT",
            (
                "You are a financial intelligence analyst. "
                "Return strict JSON with keys: summary, confidence, catalyst_type, ticker_hints. "
                "summary must be factual, concise, and only grounded in the provided source text."
            ),
        ),
        llm_summary_user_prompt_suffix=os.getenv(
            "LLM_SUMMARY_USER_PROMPT_SUFFIX",
            (
                "Requirements:\n"
                "- 2-3 sentence summary.\n"
                "- confidence is a number from 0 to 1.\n"
                "- catalyst_type is one of: product_launch, research, partnership, regulation, other.\n"
                "- ticker_hints is an array of uppercase tickers if strongly implied, else [].\n"
            ),
        ),
        dynamic_universe_enabled=_as_bool(os.getenv("DYNAMIC_UNIVERSE_ENABLED"), default=True),
        dynamic_universe_size=int(os.getenv("DYNAMIC_UNIVERSE_SIZE", "12")),
        dynamic_universe_explore_mode=_as_bool(
            os.getenv("DYNAMIC_UNIVERSE_EXPLORE_MODE"), default=True
        ),
        dynamic_universe_blend_fallback=_as_bool(
            os.getenv("DYNAMIC_UNIVERSE_BLEND_FALLBACK"), default=False
        ),
        dynamic_universe_min_fresh=int(os.getenv("DYNAMIC_UNIVERSE_MIN_FRESH", "3")),
        top_performer_pool_max=int(os.getenv("TOP_PERFORMER_POOL_MAX", "100")),
        top_performer_min_price=float(os.getenv("TOP_PERFORMER_MIN_PRICE", "2.0")),
        newsapi_enabled=_as_bool(os.getenv("NEWSAPI_ENABLED"), default=False),
        newsapi_api_key=os.getenv("NEWSAPI_API_KEY", ""),
        finnhub_enabled=_as_bool(os.getenv("FINNHUB_ENABLED"), default=False),
        finnhub_api_key=os.getenv("FINNHUB_API_KEY", ""),
        cors_origins=_split_csv(
            os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        ),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        workers=int(os.getenv("WORKERS", "2")),
    )
