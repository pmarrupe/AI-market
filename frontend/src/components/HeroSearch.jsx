import { useState, useRef, useEffect } from "react";
import { searchSP500, getSP500Opinion, fetchPriceForecast, fetchPortfolio, fetchChart } from "../api";
import TradePlanChart from "./TradePlanChart";
import HowToRead from "./HowToRead";
import CompanySnapshot from "./CompanySnapshot";
import { macdLabel } from "../utils/macd";

const PORTFOLIO_KEY = "ai_market.portfolio_value";
const RISK_PCT_KEY = "ai_market.portfolio_risk_pct";

function readNum(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    if (!v) return fallback;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : fallback;
  } catch {
    return fallback;
  }
}

function suggestShares(portfolioValue, riskPct, riskPerShare) {
  if (!portfolioValue || !riskPct || !riskPerShare) return null;
  const dollars = portfolioValue * (riskPct / 100);
  const n = Math.floor(dollars / riskPerShare);
  return n > 0 ? n : null;
}

function indicatorTone(label) {
  if (label === "MACD↑" || label === "Oversold" || label === "20d HIGH") return "pos";
  if (label === "MACD↓" || label === "Overbought" || label === "20d LOW") return "neg";
  if (label && label.startsWith("VOL ")) return label === "VOL ↓" ? "neg" : "pos";
  return "neutral";
}

function HeroChart({ ticker, plan, currentPrice }) {
  const [period, setPeriod] = useState("60D");
  const [longCloses, setLongCloses] = useState(null);
  const [loading, setLoading] = useState(false);
  const periods = ["60D", "1Y", "5Y"];

  useEffect(() => {
    if (period === "60D") {
      setLongCloses(null);
      return;
    }
    let live = true;
    setLoading(true);
    fetchChart(ticker, period.toLowerCase())
      .then((r) => { if (live) setLongCloses(r?.closes || []); })
      .catch(() => { if (live) setLongCloses([]); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [ticker, period]);

  return (
    <>
      <div className="trade-feed__chart-head">
        <div className="chart-toggle" role="tablist">
          {periods.map((p) => (
            <button
              key={p}
              type="button"
              className={p === period ? "active" : ""}
              onClick={() => setPeriod(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      {loading && period !== "60D" ? (
        <div className="trade-chart__empty">Loading {period} chart…</div>
      ) : (
        <TradePlanChart
          plan={plan}
          currentPrice={currentPrice}
          closesOverride={period === "60D" ? null : longCloses}
          showLevels={period === "60D"}
        />
      )}
    </>
  );
}

function convictionTone(c) {
  if (c === "High") return "high";
  if (c === "Med") return "mid";
  if (c === "Low") return "low";
  return "neutral";
}

function convictionToSuggestion(c) {
  if (c === "High") return "Buy";
  if (c === "Med") return "Wait";
  if (c === "Low") return "Avoid";
  return "—";
}

export default function HeroSearch() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [opinion, setOpinion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [forecast, setForecast] = useState(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState(null);
  const [tradePlan, setTradePlan] = useState(null);
  const [tradePlanLoading, setTradePlanLoading] = useState(false);
  const debounceRef = useRef(null);
  const wrapRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setSuggestions([]);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleChange = (value) => {
    setQuery(value);
    clearTimeout(debounceRef.current);
    if (value.trim().length < 1) {
      setSuggestions([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await searchSP500(value);
        setSuggestions(results);
      } catch {
        setSuggestions([]);
      }
    }, 250);
  };

  const handleSelect = async (ticker) => {
    setQuery(ticker);
    setSuggestions([]);
    setForecast(null);
    setForecastError(null);
    setTradePlan(null);
    setLoading(true);
    setOpinion(null);
    let loaded = null;
    try {
      loaded = await getSP500Opinion(ticker);
      setOpinion(loaded);
    } catch {
      setOpinion({ error: "Failed to load opinion" });
    } finally {
      setLoading(false);
    }
    if (!loaded || loaded.error) return;
    // Kick off trade plan + forecast in parallel
    setTradePlanLoading(true);
    setForecastLoading(true);
    fetchPortfolio([ticker])
      .then((res) => {
        const item = (res?.items || []).find((i) => i.ticker === ticker.toUpperCase());
        setTradePlan(item || null);
      })
      .catch(() => setTradePlan(null))
      .finally(() => setTradePlanLoading(false));
    try {
      const fc = await fetchPriceForecast(ticker);
      setForecast(fc);
      setForecastError(null);
    } catch (e) {
      setForecast(null);
      setForecastError(e.message || "Price outlook unavailable");
    } finally {
      setForecastLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const term = query.trim();
      if (!term) return;
      handleSelect(term.toUpperCase());
    }
  };

  return (
    <section className="panel hero-search-panel">
      <div className="hero-search" ref={wrapRef}>
        <div className="hero-search-input-wrap">
          <span className="hero-search-icon">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
              <circle cx="9" cy="9" r="5.5" stroke="rgba(203,213,225,0.75)" strokeWidth="1.5" />
              <line x1="12.5" y1="12.5" x2="17" y2="17" stroke="rgba(203,213,225,0.75)" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </span>
          <input
            type="text"
            placeholder="Search S&P 500 ticker or company (ex: NVDA, Apple, Microsoft)"
            autoComplete="off"
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </div>

        {suggestions.length > 0 && (
          <ul className="search-suggestions">
            {suggestions.map((s) => (
              <li key={s.ticker} onClick={() => handleSelect(s.ticker)}>
                <strong>{s.ticker}</strong>
                <span>{s.name}</span>
                <span className="search-sector">{s.sector}</span>
              </li>
            ))}
          </ul>
        )}

        <p className="hero-search-hint">
          Press Enter or select from dropdown to get AI analysis.
        </p>
      </div>

      {loading && <div className="opinion-loading">Loading AI opinion…</div>}

      {opinion && !opinion.error && (
        <div className="opinion-card">
          <div className="opinion-header">
            <h3>{opinion.ticker}</h3>
            <span className="opinion-name">{opinion.name}</span>
            <span className="opinion-sector-badge">{opinion.sector}</span>
            {opinion.signal && (
              <span className={`opinion-signal opinion-signal--${(opinion.signal || "").toLowerCase().replace(/\s+/g, "-")}`}>
                {opinion.signal}
              </span>
            )}
          </div>

          {opinion.price > 0 ? (
            <div className="opinion-price-row">
              <span className="opinion-price">${opinion.price?.toFixed(2)}</span>
              <span className={`opinion-change ${opinion.day_change > 0 ? "up" : opinion.day_change < 0 ? "down" : ""}`}>
                {opinion.day_change > 0 ? "+" : ""}{((opinion.day_change ?? 0) * 100).toFixed(2)}%
              </span>
            </div>
          ) : (
            <p className="opinion-quote-unavailable">
              No live quote from Finnhub/Stooq for this ticker (or data failed). The price shown earlier
              may have been a placeholder — check <code>FINNHUB_API_KEY</code>, network, and try Refresh.
            </p>
          )}

          <div className="opinion-metrics">
            {opinion.price > 0 && (
              <div className="opinion-metric">
                <span className="opinion-metric-label">5D Momentum</span>
                <span className={`opinion-metric-value ${opinion.momentum > 0 ? "up" : opinion.momentum < 0 ? "down" : ""}`}>
                  {opinion.momentum > 0 ? "+" : ""}{((opinion.momentum ?? 0) * 100).toFixed(2)}%
                </span>
              </div>
            )}
            {opinion.liquidity != null && (
              <div className="opinion-metric">
                <span className="opinion-metric-label">Liquidity</span>
                <span className="opinion-metric-value">{opinion.liquidity?.toFixed(3)}</span>
              </div>
            )}
            {opinion.confidence > 0 && (
              <div className="opinion-metric">
                <span className="opinion-metric-label">AI Score</span>
                <span className="opinion-metric-value">{opinion.score?.toFixed(3)}</span>
              </div>
            )}
            {opinion.confidence > 0 && (
              <div className="opinion-metric">
                <span className="opinion-metric-label">Sentiment</span>
                <span className="opinion-metric-value">{opinion.sentiment?.toFixed(3)}</span>
              </div>
            )}
            {opinion.confidence > 0 && (
              <div className="opinion-metric">
                <span className="opinion-metric-label">Confidence</span>
                <span className="opinion-metric-value">{opinion.confidence?.toFixed(3)}</span>
              </div>
            )}
            {opinion.relevance > 0 && (
              <div className="opinion-metric">
                <span className="opinion-metric-label">Relevance</span>
                <span className="opinion-metric-value">{opinion.relevance?.toFixed(3)}</span>
              </div>
            )}
          </div>

          {opinion.confidence === 0 && (
            <p className="opinion-no-news-hint">
              No AI-related news coverage found — analysis is based on market data only.
            </p>
          )}

          <p className="opinion-thesis">{opinion.thesis}</p>

          {opinion.uncertainties?.length > 0 && (
            <div className="opinion-uncertainties">
              <span className="opinion-section-label">Uncertainties</span>
              <ul>
                {opinion.uncertainties.map((u, i) => (
                  <li key={i}>{u}</li>
                ))}
              </ul>
            </div>
          )}
          {opinion.headlines?.length > 0 && (
            <div className="opinion-headlines">
              <span className="opinion-section-label">Linked Headlines</span>
              <ul>
                {opinion.headlines.map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            </div>
          )}

          <CompanySnapshot ticker={opinion.ticker} sectorFallback={opinion.sector} />

          <div className="hero-trade-plan">
            <span className="opinion-section-label">Trade plan</span>
            <HowToRead />
            {tradePlanLoading && !tradePlan && (
              <p className="price-forecast-loading">Computing trade plan…</p>
            )}
            {tradePlan && (
              <>
                <div className="hero-trade-plan__chips">
                  <span
                    className={`radar-score radar-score--${convictionTone(tradePlan.conviction)}`}
                    title={`Model conviction: ${tradePlan.conviction}`}
                  >
                    Suggest: {convictionToSuggestion(tradePlan.conviction)}
                  </span>
                  <span className="pill radar-setup-pill">{tradePlan.setup}</span>
                  <span className="pill">Horizon: {tradePlan.horizon}</span>
                  {tradePlan.earnings && tradePlan.earnings.daysToNext != null && (
                    <span
                      className={`trade-feed__earnings${
                        tradePlan.earnings.daysToNext <= 7 ? " trade-feed__earnings--soon" : ""
                      }`}
                      title={`Next earnings ${tradePlan.earnings.nextDate || ""}`}
                    >
                      ⚡ Earnings in {tradePlan.earnings.daysToNext}d
                    </span>
                  )}
                  {(tradePlan.plan?.indicators || []).map((ind) => (
                    <span
                      key={ind}
                      className={`indicator-chip indicator-chip--${indicatorTone(ind)}`}
                    >
                      {ind}
                    </span>
                  ))}
                </div>

                {tradePlan.plan && (
                  <>
                    <div className="hero-trade-plan__chart">
                      <HeroChart
                        ticker={tradePlan.ticker}
                        plan={tradePlan.plan}
                        currentPrice={tradePlan.price}
                      />
                      <div className="trade-feed__chart-legend">
                        <span><i style={{ background: "#5dd39e" }} />Targets</span>
                        <span><i style={{ background: "#b0b1bf" }} />Entry</span>
                        <span><i style={{ background: "#ef8b7a" }} />Stop</span>
                        <span><i style={{ background: "#8b9ff8" }} />Price</span>
                      </div>
                    </div>

                    <div className="hero-trade-plan__grid">
                      <div><span className="opinion-metric-label">Entry</span><p className="opinion-metric-value">{Number.isFinite(tradePlan.plan.entry) ? `$${tradePlan.plan.entry.toFixed(2)}` : "—"}</p></div>
                      <div><span className="opinion-metric-label">Stop</span><p className="opinion-metric-value down">{Number.isFinite(tradePlan.plan.stop) ? `$${tradePlan.plan.stop.toFixed(2)}` : "—"}</p></div>
                      <div><span className="opinion-metric-label">Target 1</span><p className="opinion-metric-value up">{Number.isFinite(tradePlan.plan.target1) ? `$${tradePlan.plan.target1.toFixed(2)}` : "—"}</p></div>
                      <div><span className="opinion-metric-label">Target 2</span><p className="opinion-metric-value up">{Number.isFinite(tradePlan.plan.target2) ? `$${tradePlan.plan.target2.toFixed(2)}` : "—"}</p></div>
                      <div><span className="opinion-metric-label">ATR(14)</span><p className="opinion-metric-value">{Number.isFinite(tradePlan.plan.atr14) ? tradePlan.plan.atr14.toFixed(3) : "—"}</p></div>
                      <div><span className="opinion-metric-label">R:R</span><p className="opinion-metric-value">{tradePlan.plan.rewardRisk1 ?? "—"}× / {tradePlan.plan.rewardRisk2 ?? "—"}×</p></div>
                      {tradePlan.plan.rsi14 != null && (
                        <div>
                          <span className="opinion-metric-label">RSI(14)</span>
                          <p className={`opinion-metric-value ${
                            tradePlan.plan.rsi14 >= 70 ? "down" :
                            tradePlan.plan.rsi14 <= 30 ? "up" : ""
                          }`}>
                            {tradePlan.plan.rsi14.toFixed(1)}
                          </p>
                        </div>
                      )}
                      {tradePlan.plan.macd != null && (() => {
                        const ml = macdLabel(
                          tradePlan.plan.macd,
                          tradePlan.plan.macdSignal,
                          tradePlan.plan.rsi14,
                        );
                        return (
                          <div>
                            <span className="opinion-metric-label">
                              MACD / Signal{" "}
                              {ml && (
                                <>
                                  <span className={ml.tone} title={`MACD ${tradePlan.plan.macd.toFixed(2)} vs Signal ${tradePlan.plan.macdSignal.toFixed(2)}`}>
                                    {ml.arrow} {ml.label}
                                  </span>
                                  {ml.qualifier && (
                                    <span
                                      className={ml.qualifier.tone}
                                      title={`RSI ${tradePlan.plan.rsi14?.toFixed(1) ?? "—"} — ${ml.qualifier.text}`}
                                    >
                                      {" · "}{ml.qualifier.text}
                                    </span>
                                  )}
                                </>
                              )}
                            </span>
                            <p className={`opinion-metric-value ${ml ? ml.tone : ""}`}>
                              {tradePlan.plan.macd.toFixed(2)} / {tradePlan.plan.macdSignal.toFixed(2)}
                            </p>
                          </div>
                        );
                      })()}
                      <div>
                        <span className="opinion-metric-label">Risk / share</span>
                        <p className="opinion-metric-value">{Number.isFinite(tradePlan.plan.riskPerShare) ? `$${tradePlan.plan.riskPerShare.toFixed(2)}` : "—"}</p>
                      </div>
                      <div>
                        <span className="opinion-metric-label">Suggested shares</span>
                        <p className="opinion-metric-value">
                          {suggestShares(
                            readNum(PORTFOLIO_KEY, 10000),
                            readNum(RISK_PCT_KEY, 1),
                            tradePlan.plan.riskPerShare,
                          ) ?? "—"}
                        </p>
                      </div>
                    </div>
                    <p className="price-forecast-footnote">{tradePlan.plan.note}</p>
                  </>
                )}

                {!tradePlan.plan && (
                  <p className="price-forecast-loading">
                    No trade plan — historical bars unavailable for this ticker.
                  </p>
                )}
              </>
            )}
          </div>

          <div className="price-forecast-block">
            <span className="opinion-section-label">Price outlook (historical daily data)</span>
            <p className="price-forecast-disclaimer">
              Empirical only — not a buy/sell recommendation. Uses past daily returns; option 1 = P(up),
              option 2 = median-implied price.
            </p>
            {forecastLoading && (
              <p className="price-forecast-loading">Loading price outlook…</p>
            )}
            {forecastError && !forecastLoading && (
              <p className="price-forecast-error">{forecastError}</p>
            )}
            {forecast && !forecastLoading && (
              <>
                <p className="price-forecast-meta">
                  Last close ({forecast.data_source || "historical"}):{" "}
                  <strong>${forecast.last_close?.toFixed(2)}</strong>
                </p>
                <div className="price-forecast-table-wrap">
                  <table className="price-forecast-table">
                    <thead>
                      <tr>
                        <th>Horizon</th>
                        <th>P(up)</th>
                        <th>Median-implied price</th>
                        <th>Confidence</th>
                        <th>Note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(forecast.horizons || []).map((h) => (
                        <tr key={h.horizon_trading_days}>
                          <td>{h.horizon_trading_days} trading days</td>
                          <td>
                            {h.prob_up != null ? `${(h.prob_up * 100).toFixed(1)}%` : "—"}
                          </td>
                          <td>
                            {h.predicted_price != null
                              ? `$${Number(h.predicted_price).toFixed(2)}`
                              : "—"}
                          </td>
                          <td>{h.confidence != null ? h.confidence.toFixed(2) : "—"}</td>
                          <td className="price-forecast-note">{h.outlook_label || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="price-forecast-footnote">{forecast.methodology}</p>
              </>
            )}
          </div>
        </div>
      )}

      {opinion?.error && (
        <div className="opinion-card opinion-error">
          <p>{opinion.error}</p>
        </div>
      )}
    </section>
  );
}
