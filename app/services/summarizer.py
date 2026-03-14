from __future__ import annotations

import re

from app.models import Article
from app.services.llm import llm_json_completion


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _summary_confidence(article: Article) -> float:
    evidence = 0.2
    if article.tickers:
        evidence += 0.45
    if abs(article.sentiment) > 0:
        evidence += 0.25
    if len(_clean_text(article.title).split()) >= 5:
        evidence += 0.1
    if article.source_excerpt:
        evidence += 0.05
    return round(min(1.0, evidence), 3)


def _factuality_check(article: Article) -> tuple[bool, str]:
    source_text = _clean_text(f"{article.title} {article.source_excerpt}".lower())
    if not source_text:
        return False, "missing-source-text"
    title_tokens = set(re.findall(r"[a-z0-9]{4,}", article.title.lower()))
    if not title_tokens:
        return True, "ok"
    overlap = [token for token in title_tokens if token in source_text]
    if len(overlap) < max(2, len(title_tokens) // 4):
        return False, "low-title-source-overlap"
    return True, "ok"


def _llm_summary(article: Article, llm: dict) -> dict | None:
    system_prompt = llm.get(
        "summary_system_prompt",
        (
            "You are a financial intelligence analyst. "
            "Return strict JSON with keys: summary, confidence, catalyst_type, ticker_hints. "
            "summary must be factual, concise, and only grounded in the provided source text."
        ),
    )
    suffix = llm.get(
        "summary_user_prompt_suffix",
        (
            "Requirements:\n"
            "- 2-3 sentence summary.\n"
            "- confidence is a number from 0 to 1.\n"
            "- catalyst_type is one of: product_launch, research, partnership, regulation, other.\n"
            "- ticker_hints is an array of uppercase tickers if strongly implied, else [].\n"
        ),
    )
    user_prompt = (
        f"Title: {article.title}\n"
        f"Source: {article.source}\n"
        f"URL: {article.url}\n"
        f"Excerpt: {article.source_excerpt}\n\n"
        f"{suffix}"
    )
    return llm_json_completion(
        enabled=llm.get("enabled", False),
        api_key=llm.get("api_key", ""),
        base_url=llm.get("base_url", ""),
        model=llm.get("model", ""),
        temperature=llm.get("temperature", 0.2),
        max_tokens=llm.get("max_tokens", 500),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def summarize_article(
    article: Article, min_confidence: float = 0.35, llm: dict | None = None
) -> Article:
    # Minimal deterministic summary fallback for MVP reliability.
    title = _clean_text(article.title)
    tickers = ", ".join(article.tickers) if article.tickers else "No clear public ticker mapping"
    direction = "positive" if article.sentiment > 0 else "negative" if article.sentiment < 0 else "neutral"
    confidence = _summary_confidence(article)
    factual_ok, factual_reason = _factuality_check(article)
    if confidence < min_confidence:
        return article.model_copy(
            update={
                "summary": (
                    "Insufficient evidence to publish a grounded summary for this item. "
                    f"confidence={confidence}, threshold={min_confidence}. "
                    f"Source link: {article.url}"
                )
            }
        )
    if not factual_ok:
        return article.model_copy(
            update={
                "summary": (
                    "Insufficient evidence due to factuality validation failure. "
                    f"reason={factual_reason}. Source link: {article.url}"
                )
            }
        )

    if llm:
        llm_out = _llm_summary(article, llm=llm)
        if llm_out:
            llm_confidence = float(llm_out.get("confidence", 0.0) or 0.0)
            llm_summary = _clean_text(str(llm_out.get("summary", "")))
            if llm_summary and llm_confidence >= min_confidence:
                catalyst = str(llm_out.get("catalyst_type", article.catalyst_type))
                if catalyst not in {"product_launch", "research", "partnership", "regulation", "other"}:
                    catalyst = article.catalyst_type
                llm_tickers = [
                    t.strip().upper()
                    for t in llm_out.get("ticker_hints", [])
                    if isinstance(t, str) and t.strip()
                ]
                merged_tickers = sorted(set(article.tickers + llm_tickers))
                return article.model_copy(
                    update={
                        "summary": f"{llm_summary} Source link: {article.url}.",
                        "catalyst_type": catalyst,
                        "tickers": merged_tickers,
                    }
                )

    return article.model_copy(
        update={
            "summary": (
                f"{title}. Market impact tone appears {direction}. "
                f"Linked tickers: {tickers}. Catalyst: {article.catalyst_type}. "
                f"Cluster: {article.cluster_id}. Source: {article.source}. Source link: {article.url}."
            )
        }
    )


def summarize_batch(
    articles: list[Article],
    min_confidence: float = 0.35,
    llm: dict | None = None,
    llm_max_articles: int = 8,
) -> list[Article]:
    out: list[Article] = []
    sorted_articles = sorted(articles, key=lambda a: a.signal_score, reverse=True)
    llm_urls = {str(article.url) for article in sorted_articles[: max(0, llm_max_articles)]}
    for article in articles:
        use_llm = llm if str(article.url) in llm_urls else None
        out.append(summarize_article(article, min_confidence=min_confidence, llm=use_llm))
    return out
