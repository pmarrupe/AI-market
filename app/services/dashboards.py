from __future__ import annotations

import re

from app.models import Article, StockScore

SECTOR_MAP = {
    "NVDA": "Semiconductors",
    "AMD": "Semiconductors",
    "TSM": "Semiconductors",
    "ASML": "Semiconductors",
    "AVGO": "Semiconductors",
    "QCOM": "Semiconductors",
    "INTC": "Semiconductors",
    "MSFT": "Cloud & Software",
    "GOOGL": "Cloud & Software",
    "AMZN": "Cloud & Software",
    "ORCL": "Cloud & Software",
    "CRM": "Cloud & Software",
    "ADBE": "Cloud & Software",
    "NOW": "Cloud & Software",
    "META": "Platforms",
    "AAPL": "Platforms",
    "NFLX": "Platforms",
    "UBER": "Platforms",
    "PANW": "Cybersecurity",
    "CRWD": "Cybersecurity",
    "ZS": "Cybersecurity",
    "FTNT": "Cybersecurity",
    "OKTA": "Cybersecurity",
    "SMCI": "Hardware",
    "DELL": "Hardware",
    "HPE": "Hardware",
    "ANET": "Hardware",
    "IBM": "Hardware",
    "UNH": "Healthcare AI",
    "ISRG": "Healthcare AI",
    "SYK": "Healthcare AI",
    "BSX": "Healthcare AI",
    "JNJ": "Healthcare AI",
}

SECTOR_BASELINES = {
    "Semiconductors": {"ai_revenue_share": 0.42, "gpu_shipments": 0.88, "datacenter_growth": 0.33},
    "Cloud & Software": {"ai_revenue_share": 0.28, "gpu_shipments": 0.46, "datacenter_growth": 0.29},
    "Platforms": {"ai_revenue_share": 0.18, "gpu_shipments": 0.21, "datacenter_growth": 0.19},
    "Cybersecurity": {"ai_revenue_share": 0.22, "gpu_shipments": 0.14, "datacenter_growth": 0.24},
    "Hardware": {"ai_revenue_share": 0.24, "gpu_shipments": 0.39, "datacenter_growth": 0.27},
    "Healthcare AI": {"ai_revenue_share": 0.14, "gpu_shipments": 0.07, "datacenter_growth": 0.17},
}

FUNDING_RE = re.compile(
    r"(?P<amount>\$?\d+(?:\.\d+)?)\s?(?P<unit>billion|million|bn|m)",
    re.IGNORECASE,
)
SERIES_STAGE_RE = re.compile(r"\bseries\s+([a-e])\b", re.IGNORECASE)


def _startup_name_from_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    parts = re.split(r"\b(raises|raised|secures|secured|funding|series)\b", cleaned, flags=re.IGNORECASE)
    candidate = parts[0].strip(" -:") if parts else cleaned
    words = candidate.split()
    return " ".join(words[:5]) if words else cleaned[:40]


def ai_startup_funding_tracker(articles: list[Article], limit: int = 10) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for article in articles:
        text = f"{article.title} {article.source_excerpt}".lower()
        has_funding_terms = any(
            term in text for term in ("raise", "raised", "funding", "seed", "series a", "series b", "series c")
        )
        has_series_stage = bool(SERIES_STAGE_RE.search(text))
        if not has_funding_terms and not has_series_stage:
            continue
        match = FUNDING_RE.search(f"{article.title} {article.source_excerpt}")
        if not match and not has_series_stage:
            continue
        amount = None
        if match:
            amount = f"{match.group('amount')} {match.group('unit')}".upper().replace("BN", "B")
        stage = "Funding"
        if "seed" in text:
            stage = "Seed"
        else:
            series_match = SERIES_STAGE_RE.search(text)
            if series_match:
                stage = f"Series {series_match.group(1).upper()}"
        out.append(
            {
                "startup": _startup_name_from_title(article.title),
                "amount": amount or "Undisclosed",
                "stage": stage,
                "source": article.source,
                "url": str(article.url),
                "published_at": article.published_at,
            }
        )
    return out[:limit]


def ai_product_launch_tracker(articles: list[Article], limit: int = 12) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for article in articles:
        text = f"{article.title} {article.summary}".lower()
        if article.catalyst_type != "product_launch" and not any(
            term in text for term in ("launch", "release", "introduced", "rolls out", "debut")
        ):
            continue
        out.append(
            {
                "product": article.title,
                "company_hint": article.source,
                "url": str(article.url),
                "published_at": article.published_at,
            }
        )
    return out[:limit]


def ai_research_dashboard(articles: list[Article], limit: int = 12) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for article in articles:
        text = f"{article.title} {article.summary}".lower()
        is_arxiv_source = "arxiv.org" in article.source
        if article.catalyst_type != "research" and not is_arxiv_source and not any(
            term in text for term in ("paper", "arxiv", "research", "study", "benchmark", "preprint")
        ):
            continue
        out.append(
            {
                "title": article.title,
                "source": article.source,
                "url": str(article.url),
                "published_at": article.published_at,
            }
        )
    return out[:limit]


def ai_stock_market_dashboard(stocks: list[StockScore]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for stock in stocks:
        sector = SECTOR_MAP.get(stock.ticker, "Other")
        base = SECTOR_BASELINES.get(
            sector,
            {"ai_revenue_share": 0.16, "gpu_shipments": 0.11, "datacenter_growth": 0.14},
        )
        ai_revenue_share = round(min(0.95, base["ai_revenue_share"] + (stock.relevance * 0.2)), 3)
        gpu_shipments = round(min(1.0, base["gpu_shipments"] + max(0.0, stock.momentum * 0.3)), 3)
        datacenter_growth = round(
            min(0.9, base["datacenter_growth"] + (stock.liquidity * 0.15) + max(0.0, stock.momentum * 0.25)),
            3,
        )
        rows.append(
            {
                "ticker": stock.ticker,
                "sector": sector,
                "price": stock.price,
                "day_change": stock.day_change,
                "score": stock.score,
                "ai_revenue_share": ai_revenue_share,
                "gpu_shipments": gpu_shipments,
                "datacenter_growth": datacenter_growth,
            }
        )
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows
