import { useState, useRef, useEffect } from "react";
import { searchSP500, getSP500Opinion, fetchPriceForecast } from "../api";

export default function HeroSearch() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [opinion, setOpinion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [forecast, setForecast] = useState(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState(null);
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
    setForecastLoading(true);
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
