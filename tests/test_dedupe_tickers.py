from app.services.universe import dedupe_tickers


def test_dedupe_tickers_order_and_case():
    assert dedupe_tickers(["aapl", "MSFT", " aapl ", "nvda"]) == ["AAPL", "MSFT", "NVDA"]


def test_dedupe_tickers_skips_empty():
    assert dedupe_tickers(["", "   ", "X"]) == ["X"]
