from __future__ import annotations

import json
import random
import time

from app.models import Article
from app.services.llm import llm_json_completion

INDUSTRY_LEADERS: dict[str, list[str]] = {
    "semiconductors": ["NVDA", "AMD", "TSM", "ASML", "AVGO", "QCOM", "INTC"],
    "cloud_and_software": ["MSFT", "GOOGL", "AMZN", "ORCL", "CRM", "ADBE", "NOW"],
    "platforms_and_consumer": ["META", "AAPL", "NFLX", "UBER"],
    "industrial_automation": ["GE", "HON", "ETN", "ROK", "PH"],
    "cybersecurity": ["PANW", "CRWD", "ZS", "FTNT", "OKTA"],
    "data_and_hardware": ["DELL", "HPE", "SMCI", "ANET", "IBM"],
    "healthcare_ai": ["UNH", "ISRG", "SYK", "BSX", "JNJ"],
}


def _candidate_universe() -> list[str]:
    out: list[str] = []
    for tickers in INDUSTRY_LEADERS.values():
        out.extend(tickers)
    return sorted(set(out))


def discover_top_tickers(
    articles: list[Article],
    llm: dict,
    fallback_tickers: list[str],
    max_tickers: int = 12,
    previous_tickers: list[str] | None = None,
    blend_fallback: bool = True,
    explore_mode: bool = False,
    min_fresh_tickers: int = 3,
) -> list[str]:
    candidates = _candidate_universe()
    headlines = [a.title for a in articles[:25]]
    if not llm.get("enabled", False):
        return fallback_tickers[:max_tickers]

    system_prompt = (
        "You are an equity strategy assistant. Return strict JSON with key 'tickers' only. "
        "Choose top publicly traded stocks from leading industries most relevant to current AI cycle. "
        "Only choose from provided candidate tickers."
    )
    user_prompt = (
        "Candidate tickers by industry:\n"
        + json.dumps(INDUSTRY_LEADERS, ensure_ascii=True)
        + "\n\nRecent AI headlines:\n"
        + json.dumps(headlines, ensure_ascii=True)
        + f"\n\nReturn JSON like {{\"tickers\": [..]}} with at most {max_tickers} unique symbols."
    )
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
        return fallback_tickers[:max_tickers]

    selected = [
        str(t).strip().upper()
        for t in out.get("tickers", [])
        if isinstance(t, str) and str(t).strip()
    ]
    selected = [t for t in selected if t in candidates]
    dedup_selected: list[str] = []
    for ticker in selected:
        if ticker not in dedup_selected:
            dedup_selected.append(ticker)
    selected = dedup_selected[:max_tickers]

    previous = [ticker.upper() for ticker in (previous_tickers or [])]
    if explore_mode and selected:
        # Keep LLM relevance, but rotate in a few fresh names.
        rng = random.Random(time.time_ns())
        needed_fresh = max(1, min(min_fresh_tickers, max_tickers))
        current_fresh = len([ticker for ticker in selected if ticker not in previous])
        pool = [ticker for ticker in candidates if ticker not in selected]
        rng.shuffle(pool)
        candidate_fresh = [ticker for ticker in pool if ticker not in previous]
        inject = candidate_fresh[: max(0, needed_fresh - current_fresh)]
        if inject:
            keep_count = max(0, max_tickers - len(inject))
            selected = selected[:keep_count] + inject
            # Re-dedupe and trim.
            merged_unique: list[str] = []
            for ticker in selected:
                if ticker not in merged_unique:
                    merged_unique.append(ticker)
            selected = merged_unique[:max_tickers]

    if blend_fallback:
        merged: list[str] = []
        for ticker in selected + fallback_tickers:
            if ticker not in merged:
                merged.append(ticker)
            if len(merged) >= max_tickers:
                break
        if merged:
            return merged

    if selected:
        return selected[:max_tickers]

    if not fallback_tickers:
        return fallback_tickers[:max_tickers]
    return fallback_tickers[:max_tickers]
