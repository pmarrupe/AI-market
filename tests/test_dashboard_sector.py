from datetime import datetime, timezone

from app.models import StockScore
from app.services.dashboards import ai_stock_market_dashboard, resolve_stock_sector


def test_resolve_sector_from_sp500_csv():
    assert resolve_stock_sector("TER") == "Information Technology"
    assert resolve_stock_sector("MPC") == "Energy"
    assert resolve_stock_sector("BG") == "Consumer Staples"


def test_curated_sector_map_overrides_sp500():
    assert resolve_stock_sector("NVDA") == "Semiconductors"


def test_ai_stock_market_dashboard_row_not_all_other():
    stock = StockScore(
        ticker="TER",
        price=100.0,
        day_change=0.01,
        score=0.5,
        confidence=0.5,
        momentum=0.2,
        liquidity=0.2,
        valuation_sanity=0.5,
        sentiment=0.1,
        relevance=0.1,
        explanation="",
        updated_at=datetime.now(timezone.utc),
    )
    rows = ai_stock_market_dashboard([stock])
    assert rows[0]["sector"] == "Information Technology"
    # "Other" baseline pins ai_revenue_share near 0.16; IT baseline is higher before tweaks.
    assert float(rows[0]["ai_revenue_share"]) > 0.2
