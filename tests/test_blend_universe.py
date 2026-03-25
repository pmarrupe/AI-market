from unittest.mock import patch

from app.services.blend_universe import build_blend_universe


@patch("app.services.blend_universe.discover_top_performer_tickers")
def test_blend_fills_mover_slots_after_anchor(mock_discover):
    mock_discover.return_value = ["ZZZ", "AAA", "NVDA", "QQQ"]
    out = build_blend_universe(
        watchlist_tickers=["nvda", "msft"],
        tracked_tickers=["MSFT"],
        default_tickers=["SPY"],
        finnhub_enabled=True,
        finnhub_api_key="k",
        target_size=5,
        pool_max=100,
        min_price=2.0,
    )
    assert out[:2] == ["NVDA", "MSFT"]
    assert len(out) == 5
    assert set(out) == {"NVDA", "MSFT", "ZZZ", "AAA", "QQQ"}
    mock_discover.assert_called_once()


@patch("app.services.blend_universe.discover_top_performer_tickers")
def test_blend_anchor_only_when_no_finnhub(mock_discover):
    out = build_blend_universe(
        watchlist_tickers=["A"],
        tracked_tickers=[],
        default_tickers=["SPY"],
        finnhub_enabled=False,
        finnhub_api_key="",
        target_size=10,
        pool_max=100,
        min_price=2.0,
    )
    assert out == ["A"]
    mock_discover.assert_not_called()


@patch("app.services.blend_universe.discover_top_performer_tickers")
def test_blend_fallback_anchor_uses_default_when_lists_empty(mock_discover):
    mock_discover.return_value = ["X", "Y"]
    out = build_blend_universe(
        watchlist_tickers=[],
        tracked_tickers=[],
        default_tickers=["SPY", "QQQ"],
        finnhub_enabled=True,
        finnhub_api_key="k",
        target_size=4,
        pool_max=100,
        min_price=2.0,
    )
    assert out[:2] == ["SPY", "QQQ"]
    assert len(out) == 4


@patch("app.services.blend_universe.discover_top_performer_tickers")
def test_blend_respects_long_anchor(mock_discover):
    anchor = ["A", "B", "C", "D", "E"]
    out = build_blend_universe(
        watchlist_tickers=anchor,
        tracked_tickers=[],
        default_tickers=["SPY"],
        finnhub_enabled=True,
        finnhub_api_key="k",
        target_size=3,
        pool_max=100,
        min_price=2.0,
    )
    assert out == anchor
    mock_discover.assert_not_called()
