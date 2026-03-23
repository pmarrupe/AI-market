"""Tests for top-performer universe (no live Finnhub)."""

from __future__ import annotations

from app.services.top_performer_universe import _daily_shuffled_pool, discover_top_performer_tickers


def test_daily_pool_stable_for_same_day() -> None:
    syms = [f"S{i}" for i in range(50)]
    a = _daily_shuffled_pool(syms, 10, seed_day="2030-01-15")
    b = _daily_shuffled_pool(syms, 10, seed_day="2030-01-15")
    assert a == b
    assert len(a) == 10


def test_daily_pool_changes_across_days() -> None:
    syms = [f"S{i}" for i in range(50)]
    a = _daily_shuffled_pool(syms, 10, seed_day="2030-01-15")
    b = _daily_shuffled_pool(syms, 10, seed_day="2030-01-16")
    assert a != b


def test_discover_without_finnhub_uses_fallback() -> None:
    out = discover_top_performer_tickers(
        finnhub_enabled=False,
        finnhub_api_key="",
        max_tickers=5,
        pool_max=20,
        fallback_tickers=["AAA", "BBB", "CCC"],
    )
    assert out == ["AAA", "BBB", "CCC"]


def test_discover_fallback_trim() -> None:
    out = discover_top_performer_tickers(
        finnhub_enabled=False,
        finnhub_api_key="",
        max_tickers=2,
        pool_max=20,
        fallback_tickers=["AAA", "BBB", "CCC"],
    )
    assert out == ["AAA", "BBB"]
