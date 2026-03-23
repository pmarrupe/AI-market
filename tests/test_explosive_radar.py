"""Unit tests for Explosive Move Radar scoring (no network)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import HttpUrl

from app.models import Article, StockScore
from app.services.explosive_radar import (
    classify_setup_deterministic,
    compute_explosive_radar_row,
    filter_explosive_radar_rows,
    load_explosive_radar_weights,
    sort_radar_rows,
)
from app.services.explosive_radar_data import DailyBarSeries
from app.services.explosive_radar_validation import forward_outcomes_from_index


def _stock(ticker: str = "NVDA", liquidity: float = 0.45) -> StockScore:
    return StockScore(
        ticker=ticker,
        price=100.0,
        day_change=0.02,
        score=0.5,
        confidence=0.6,
        momentum=0.04,
        liquidity=liquidity,
        valuation_sanity=0.7,
        sentiment=0.1,
        relevance=0.5,
        explanation="",
        updated_at=datetime.now(timezone.utc),
    )


def _article(ticker: str = "NVDA") -> Article:
    return Article(
        title="Company announces AI partnership and defense contract",
        source="test",
        url=HttpUrl("https://example.com/news/1"),
        published_at=datetime.now(timezone.utc),
        summary="Semiconductor firm expands government work",
        tickers=[ticker],
        sentiment=0.15,
    )


def _volatile_bars() -> DailyBarSeries:
    """Uptrend with elevated last-day volume and breakout."""
    closes = [10.0 + i * 0.15 for i in range(30)]
    closes[-1] = max(closes[-2], max(closes[-22:-1])) * 1.03 + 0.5
    volumes = [800_000.0] * 20 + [900_000.0] * 9 + [6_000_000.0]
    highs = [c * 1.015 for c in closes]
    lows = [c * 0.985 for c in closes]
    opens = [closes[0]] + closes[:-1]
    opens[-1] = closes[-2] * 1.01
    return DailyBarSeries(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        source="test",
    )


def _microcap_spike_bars() -> DailyBarSeries:
    """Tiny dollar volume but huge RVOL — should not dominate jump after dvol gate."""
    closes = [5.0 + i * 0.01 for i in range(30)]
    closes[-1] = closes[-2] * 1.14
    volumes = [200.0] * 19 + [400.0] * 10 + [50_000.0]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    opens = [closes[0]] + closes[:-1]
    return DailyBarSeries(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        source="test",
    )


def test_scores_clamped_0_100() -> None:
    w = load_explosive_radar_weights()
    row = compute_explosive_radar_row(
        "NVDA",
        _stock(),
        _volatile_bars(),
        [_article()],
        w,
    )
    for k in ("jumpScore", "catalystScore", "riskScore", "confidenceScore", "rankedOpportunityScore"):
        assert 0 <= row[k] <= 100


def test_reasons_populated_with_news() -> None:
    w = load_explosive_radar_weights()
    row = compute_explosive_radar_row("NVDA", _stock(), _volatile_bars(), [_article()], w)
    assert len(row["reasons"]) >= 1
    assert any("headline" in r.lower() or "volume" in r.lower() for r in row["reasons"])


def test_graceful_without_bars() -> None:
    w = load_explosive_radar_weights()
    row = compute_explosive_radar_row("NVDA", _stock(), None, [], w)
    assert row["relativeVolume"] is None
    assert row["jumpScore"] >= 0
    assert any("unavailable" in r.lower() for r in row["reasons"])
    assert row["missingDataFields"]
    assert row["setupDriver"] in ("catalyst-backed", "price-driven", "mixed")


def test_confidence_drops_without_news_but_jump_high() -> None:
    w = load_explosive_radar_weights()
    row_news = compute_explosive_radar_row("NVDA", _stock(), _volatile_bars(), [_article()], w)
    row_none = compute_explosive_radar_row("NVDA", _stock(), _volatile_bars(), [], w)
    if row_none["jumpScore"] >= 48:
        assert row_none["confidenceScore"] <= row_news["confidenceScore"]


def test_micro_dvol_reduces_jump_vs_quality_bars() -> None:
    w = load_explosive_radar_weights()
    good = compute_explosive_radar_row("NVDA", _stock(liquidity=0.55), _volatile_bars(), [], w)
    junk = compute_explosive_radar_row("NVDA", _stock(liquidity=0.55), _microcap_spike_bars(), [], w)
    assert junk["jumpScore"] < good["jumpScore"]


def test_ranked_and_agreement_present() -> None:
    w = load_explosive_radar_weights()
    row = compute_explosive_radar_row("NVDA", _stock(), _volatile_bars(), [_article()], w)
    assert row["signalAgreementCount"] >= 0
    assert row["rankedOpportunityScore"] >= 0


def test_sort_radar_rows_opportunity_vs_jump() -> None:
    rows = [
        {"jumpScore": 90, "catalystScore": 20, "rankedOpportunityScore": 40, "confidenceScore": 30},
        {"jumpScore": 50, "catalystScore": 80, "rankedOpportunityScore": 72, "confidenceScore": 80},
    ]
    sort_radar_rows(rows, "opportunity")
    assert rows[0]["rankedOpportunityScore"] >= rows[1]["rankedOpportunityScore"]
    rows2 = list(reversed(rows))
    sort_radar_rows(rows2, "jump")
    assert rows2[0]["jumpScore"] >= rows2[1]["jumpScore"]


def test_filter_min_jump() -> None:
    rows = [
        {"ticker": "A", "jumpScore": 80, "riskScore": 40, "setupType": "Multi-Day Momentum Continuation"},
        {"ticker": "B", "jumpScore": 30, "riskScore": 50, "setupType": "No Clear Edge"},
    ]
    out = filter_explosive_radar_rows(rows, min_jump=60)
    assert len(out) == 1 and out[0]["ticker"] == "A"


def test_classify_setup_deterministic_returns_label() -> None:
    label = classify_setup_deterministic(
        jump_score=70,
        catalyst_score=60,
        change_1d=0.05,
        change_3d=0.08,
        change_5d=0.1,
        rvol=4.0,
        gap=0.01,
        open_last=100.0,
        close_last=103.0,
        keyword_labels=["ai"],
        news_count=3,
        low_float_heuristic=False,
        sector_sympathy=False,
        ipo_buzz=False,
        liquidity=0.5,
        dvol=50_000_000.0,
        breakout=True,
        weak_quality=False,
    )
    assert isinstance(label, str)
    assert len(label) > 2


def test_forward_outcomes_sane() -> None:
    closes = [10.0, 10.5, 11.0, 10.8, 12.0]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    fo = forward_outcomes_from_index(highs, lows, closes, 1)
    assert fo["max_fwd_return_1d"] is not None
    assert fo["max_fwd_return_1d"] > 0
