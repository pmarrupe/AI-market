from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, HttpUrl


class Article(BaseModel):
    title: str
    source: str
    url: HttpUrl
    published_at: datetime
    summary: str
    tickers: list[str]
    sentiment: float
    cluster_id: str = ""
    catalyst_type: str = "other"
    source_excerpt: str = ""
    signal_score: float = 0.0


class StockScore(BaseModel):
    ticker: str
    price: float
    day_change: float
    score: float
    confidence: float
    momentum: float
    liquidity: float
    valuation_sanity: float
    sentiment: float
    relevance: float
    explanation: str
    updated_at: datetime


class RecommendationAuditRecord(BaseModel):
    ticker: str
    model_version: str
    input_payload: str
    output_payload: str
    source_urls: list[str]
    created_at: datetime
