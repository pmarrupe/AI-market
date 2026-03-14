from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import re
from urllib.parse import urlparse

import feedparser
import httpx

from app.models import Article

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def _load_json_env(name: str, default):
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        import json

        return json.loads(raw)
    except Exception:
        logger.warning("Failed to parse JSON for env %s, using defaults", name)
        return default


TICKER_KEYWORDS = _load_json_env(
    "TICKER_KEYWORDS_JSON",
    {
        "NVDA": ["nvidia", "gpu", "cuda"],
        "MSFT": ["microsoft", "azure", "copilot"],
        "GOOGL": ["google", "gemini", "deepmind"],
        "AMZN": ["amazon", "aws", "bedrock"],
        "META": ["meta", "llama"],
        "AMD": ["amd"],
        "TSM": ["tsmc", "tsm"],
        "ASML": ["asml", "lithography"],
    },
)

POSITIVE_WORDS = set(
    _load_json_env(
        "POSITIVE_WORDS_JSON",
        ["gain", "up", "growth", "record", "improve", "launch", "beats"],
    )
)
NEGATIVE_WORDS = set(
    _load_json_env(
        "NEGATIVE_WORDS_JSON",
        ["drop", "down", "risk", "delay", "cuts", "miss", "lawsuit"],
    )
)
CATALYST_KEYWORDS = {
    "product_launch": {"launch", "launched", "debut", "release"},
    "research": {"paper", "arxiv", "preprint", "research"},
    "partnership": {"partner", "partnership", "collaboration", "agreement"},
    "regulation": {"regulation", "policy", "antitrust", "compliance"},
}
SOURCE_RELIABILITY = _load_json_env(
    "SOURCE_RELIABILITY_JSON",
    {
        "techcrunch.com": 0.78,
        "openai.com": 0.9,
        "venturebeat.com": 0.74,
        "bloomberg.com": 0.92,
        "blog.google": 0.86,
        "news.mit.edu": 0.89,
        "reuters.com": 0.9,
        "finnhub.io": 0.76,
        "newsapi.org": 0.76,
    },
)


def _sentiment_score(text: str) -> float:
    lowered = text.lower()
    pos = sum(1 for word in POSITIVE_WORDS if word in lowered)
    neg = sum(1 for word in NEGATIVE_WORDS if word in lowered)
    total = max(1, pos + neg)
    return round((pos - neg) / total, 3)


def _extract_tickers(text: str) -> list[str]:
    lowered = text.lower()
    matches = []
    for ticker, keywords in TICKER_KEYWORDS.items():
        kw_list = keywords if isinstance(keywords, (list, tuple, set)) else [keywords]
        if any(str(keyword).lower() in lowered for keyword in kw_list):
            matches.append(ticker)
    return matches


def _parse_datetime(struct_time_obj) -> datetime:
    if not struct_time_obj:
        return datetime.now(timezone.utc)
    return datetime(*struct_time_obj[:6], tzinfo=timezone.utc)


def _parse_datetime_text(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _catalyst_type(text: str) -> str:
    lowered = text.lower()
    for kind, keywords in CATALYST_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return kind
    return "other"


def _title_cluster_key(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    filtered = [w for w in words if len(w) > 3]
    top = sorted(set(filtered))[:5]
    return "-".join(top) if top else "misc"


def _parse_feed_url(client: httpx.Client, feed_url: str):
    response = client.get(
        feed_url,
        headers=REQUEST_HEADERS,
    )
    response.raise_for_status()
    return feedparser.parse(response.text)


def _build_article(
    *,
    title: str,
    link: str,
    source: str,
    published_at: datetime,
    excerpt: str,
    cluster_map: dict[str, int],
) -> Article:
    text_blob = f"{title} {excerpt}"
    cluster_key = _title_cluster_key(title)
    if cluster_key not in cluster_map:
        cluster_map[cluster_key] = len(cluster_map) + 1
    cluster_id = f"cluster-{cluster_map[cluster_key]:03d}"
    return Article(
        title=title,
        source=source,
        url=link,
        published_at=published_at,
        summary="",
        tickers=_extract_tickers(text_blob),
        sentiment=_sentiment_score(text_blob),
        cluster_id=cluster_id,
        catalyst_type=_catalyst_type(text_blob),
        source_excerpt=excerpt,
    )


def _fetch_newsapi_articles(
    client: httpx.Client, api_key: str, max_count: int
) -> list[dict[str, str]]:
    logger.info("NewsAPI fetch started: page_size=%s", max_count)
    response = client.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": '"artificial intelligence" OR "generative ai"',
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": max_count,
            "apiKey": api_key,
        },
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("articles", []) if isinstance(payload, dict) else []
    out: list[dict[str, str]] = []
    for row in rows:
        title = str(row.get("title", "")).strip()
        link = str(row.get("url", "")).strip()
        if not title or not link:
            continue
        source_name = str((row.get("source") or {}).get("name", "")).strip()
        source = urlparse(link).netloc or source_name.lower() or "newsapi.org"
        out.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "published_at": str(row.get("publishedAt", "")),
                "excerpt": _clean_text(str(row.get("description", "") or row.get("content", "")))[:500],
            }
        )
    logger.info("NewsAPI fetch complete: raw=%s usable=%s", len(rows), len(out))
    return out


def _fetch_finnhub_articles(
    client: httpx.Client, api_key: str, max_count: int
) -> list[dict[str, str]]:
    logger.info("Finnhub fetch started: max_count=%s", max_count)
    response = client.get(
        "https://finnhub.io/api/v1/news",
        params={"category": "general", "token": api_key},
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload if isinstance(payload, list) else []
    out: list[dict[str, str]] = []
    for row in rows[:max_count]:
        title = str(row.get("headline", "")).strip()
        link = str(row.get("url", "")).strip()
        if not title or not link:
            continue
        source = str(row.get("source", "")).strip().lower() or urlparse(link).netloc or "finnhub.io"
        out.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "published_at": datetime.fromtimestamp(int(row.get("datetime", 0)), tz=timezone.utc).isoformat()
                if row.get("datetime")
                else "",
                "excerpt": _clean_text(str(row.get("summary", "")))[:500],
            }
        )
    logger.info("Finnhub fetch complete: raw=%s usable=%s", len(rows), len(out))
    return out


def fetch_articles(
    feed_urls: list[str],
    max_per_feed: int = 10,
    newsapi_enabled: bool = False,
    newsapi_api_key: str = "",
    finnhub_enabled: bool = False,
    finnhub_api_key: str = "",
) -> list[Article]:
    logger.info(
        "Article refresh started: rss_sources=%s newsapi_enabled=%s finnhub_enabled=%s",
        len(feed_urls),
        newsapi_enabled,
        finnhub_enabled,
    )
    articles: list[Article] = []
    cluster_map: dict[str, int] = {}
    seen_urls: set[str] = set()
    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        for feed_url in feed_urls:
            source = urlparse(feed_url).netloc or "unknown"
            try:
                parsed = _parse_feed_url(client, feed_url)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response else "unknown"
                logger.warning("RSS fetch blocked: source=%s status=%s url=%s", source, status, feed_url)
                continue
            except httpx.HTTPError as exc:
                logger.warning("RSS fetch network error: source=%s url=%s error=%s", source, feed_url, str(exc))
                continue
            except Exception:
                logger.warning("RSS fetch failed: source=%s url=%s", source, feed_url, exc_info=True)
                continue
            source_count = 0
            for entry in parsed.entries[:max_per_feed]:
                title = entry.get("title", "Untitled")
                link = entry.get("link", "")
                if not link or link in seen_urls:
                    continue
                excerpt = _clean_text(entry.get("summary", "") or entry.get("description", ""))[:500]
                article = _build_article(
                    title=title,
                    link=link,
                    source=source,
                    published_at=_parse_datetime(entry.get("published_parsed")),
                    excerpt=excerpt,
                    cluster_map=cluster_map,
                )
                articles.append(article)
                seen_urls.add(link)
                source_count += 1
            logger.info("RSS source fetched: source=%s entries_added=%s", source, source_count)

        if newsapi_enabled and newsapi_api_key:
            try:
                news_rows = _fetch_newsapi_articles(client, newsapi_api_key, max_count=max_per_feed * 3)
                added = 0
                for row in news_rows:
                    if row["url"] in seen_urls:
                        continue
                    article = _build_article(
                        title=row["title"],
                        link=row["url"],
                        source=row["source"],
                        published_at=_parse_datetime_text(row["published_at"]),
                        excerpt=row["excerpt"],
                        cluster_map=cluster_map,
                    )
                    articles.append(article)
                    seen_urls.add(row["url"])
                    added += 1
                logger.info("NewsAPI merged: added=%s deduped=%s", added, len(news_rows) - added)
            except Exception:
                logger.warning("NewsAPI fetch failed", exc_info=True)
        elif newsapi_enabled:
            logger.warning("NewsAPI enabled but api key missing")

        if finnhub_enabled and finnhub_api_key:
            try:
                fin_rows = _fetch_finnhub_articles(client, finnhub_api_key, max_count=max_per_feed * 3)
                added = 0
                for row in fin_rows:
                    if row["url"] in seen_urls:
                        continue
                    article = _build_article(
                        title=row["title"],
                        link=row["url"],
                        source=row["source"],
                        published_at=_parse_datetime_text(row["published_at"]),
                        excerpt=row["excerpt"],
                        cluster_map=cluster_map,
                    )
                    articles.append(article)
                    seen_urls.add(row["url"])
                    added += 1
                logger.info("Finnhub merged: added=%s deduped=%s", added, len(fin_rows) - added)
            except Exception:
                logger.warning("Finnhub fetch failed", exc_info=True)
        elif finnhub_enabled:
            logger.warning("Finnhub enabled but api key missing")

    cluster_counts: dict[str, int] = {}
    cluster_sources: dict[str, set[str]] = {}
    for article in articles:
        cluster_counts[article.cluster_id] = cluster_counts.get(article.cluster_id, 0) + 1
        if article.cluster_id not in cluster_sources:
            cluster_sources[article.cluster_id] = set()
        cluster_sources[article.cluster_id].add(article.source)

    enriched: list[Article] = []
    for article in articles:
        source_rel = SOURCE_RELIABILITY.get(article.source, 0.6)
        corroboration = min(1.0, (len(cluster_sources.get(article.cluster_id, set())) - 1) / 2)
        novelty = 1.0 / max(1.0, float(cluster_counts.get(article.cluster_id, 1)))
        ticker_presence = 1.0 if article.tickers else 0.0
        sentiment_strength = min(1.0, abs(article.sentiment))
        signal_score = round(
            (0.35 * source_rel)
            + (0.3 * corroboration)
            + (0.2 * novelty)
            + (0.1 * ticker_presence)
            + (0.05 * sentiment_strength),
            3,
        )
        enriched.append(article.model_copy(update={"signal_score": signal_score}))
    logger.info(
        "Article refresh complete: total_articles=%s unique_urls=%s clusters=%s",
        len(enriched),
        len(seen_urls),
        len(cluster_counts),
    )
    return enriched


def source_health(
    feed_urls: list[str],
    newsapi_enabled: bool = False,
    newsapi_api_key: str = "",
    finnhub_enabled: bool = False,
    finnhub_api_key: str = "",
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    logger.info(
        "Source health check started: rss_sources=%s newsapi_enabled=%s finnhub_enabled=%s",
        len(feed_urls),
        newsapi_enabled,
        finnhub_enabled,
    )
    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        for feed_url in feed_urls:
            source = urlparse(feed_url).netloc or "unknown"
            try:
                parsed = _parse_feed_url(client, feed_url)
                if parsed.bozo:
                    rows.append(
                        {"source": source, "status": "degraded", "detail": str(parsed.bozo_exception)}
                    )
                else:
                    rows.append(
                        {
                            "source": source,
                            "status": "ok",
                            "detail": f"entries={len(parsed.entries)}",
                        }
                    )
            except Exception as exc:
                rows.append({"source": source, "status": "error", "detail": str(exc)})
        if newsapi_enabled:
            if not newsapi_api_key:
                rows.append({"source": "newsapi.org", "status": "disabled", "detail": "missing api key"})
            else:
                try:
                    response = client.get(
                        "https://newsapi.org/v2/top-headlines",
                        params={"country": "us", "pageSize": 1, "apiKey": newsapi_api_key},
                    )
                    response.raise_for_status()
                    rows.append({"source": "newsapi.org", "status": "ok", "detail": "reachable"})
                except Exception as exc:
                    rows.append({"source": "newsapi.org", "status": "error", "detail": str(exc)})
        if finnhub_enabled:
            if not finnhub_api_key:
                rows.append({"source": "finnhub.io", "status": "disabled", "detail": "missing api key"})
            else:
                try:
                    response = client.get(
                        "https://finnhub.io/api/v1/news",
                        params={"category": "general", "token": finnhub_api_key},
                    )
                    response.raise_for_status()
                    rows.append({"source": "finnhub.io", "status": "ok", "detail": "reachable"})
                except Exception as exc:
                    rows.append({"source": "finnhub.io", "status": "error", "detail": str(exc)})
    ok = sum(1 for row in rows if row.get("status") == "ok")
    errors = sum(1 for row in rows if row.get("status") == "error")
    degraded = sum(1 for row in rows if row.get("status") == "degraded")
    disabled = sum(1 for row in rows if row.get("status") == "disabled")
    logger.info(
        "Source health check complete: total=%s ok=%s degraded=%s error=%s disabled=%s",
        len(rows),
        ok,
        degraded,
        errors,
        disabled,
    )
    return rows
