import { useState, useEffect, useCallback } from "react";
import { fetchDashboard } from "./api";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import KPIGrid from "./components/KPIGrid";
import HeroSearch from "./components/HeroSearch";
import StockScanner from "./components/StockScanner";
import IndustryMap from "./components/IndustryMap";
import StockDashboard from "./components/StockDashboard";
import SummaryBar from "./components/SummaryBar";
import StartupFunding from "./components/StartupFunding";
import ProductLaunches from "./components/ProductLaunches";
import Research from "./components/Research";

export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSection, setActiveSection] = useState("overview");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchDashboard();
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleNavigate = (section) => {
    setActiveSection(section);
    const el = document.getElementById(section);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="app-shell">
      <Sidebar activeSection={activeSection} onNavigate={handleNavigate} />
      <main className="workspace">
        <Header onRefreshDone={loadData} />

        {loading && !data && (
          <div className="loading-state">
            <div className="loading-spinner" />
            <p>Loading dashboard data…</p>
          </div>
        )}

        {error && !data && (
          <div className="error-state">
            <p>Failed to load dashboard: {error}</p>
            <button onClick={loadData}>Retry</button>
          </div>
        )}

        {data && (
          <>
            <KPIGrid data={data} />

            <section className="panel disclaimer">
              <p>
                Research intelligence only. This dashboard is not personalized
                investment advice. Recommendations may be withheld when evidence
                confidence is too low.
              </p>
            </section>

            <HeroSearch />

            <StockScanner
              rows={data.stock_rows}
              sectors={data.stock_sectors}
              signalLabels={data.stock_signal_labels}
              riskLevels={data.stock_risk_levels}
              timeHorizons={data.stock_time_horizons}
              statuses={data.stock_statuses}
              isLoading={loading}
              onRequestRefresh={loadData}
            />

            <IndustryMap items={data.industry_map} />

            <StockDashboard rows={data.stock_market_rows} />

            <SummaryBar data={data} />

            <section className="panel-grid">
              <StartupFunding items={data.startup_funding} />
              <ProductLaunches items={data.product_launches} />
            </section>

            <Research items={data.research_items} />
          </>
        )}
      </main>
    </div>
  );
}
