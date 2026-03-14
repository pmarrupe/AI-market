import { useState, useRef, useEffect } from "react";
import { searchSP500, getSP500Opinion } from "../api";

export default function HeroSearch() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [opinion, setOpinion] = useState(null);
  const [loading, setLoading] = useState(false);
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
    setLoading(true);
    setOpinion(null);
    try {
      const result = await getSP500Opinion(ticker);
      setOpinion(result);
    } catch {
      setOpinion({ error: "Failed to load opinion" });
    } finally {
      setLoading(false);
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

          {opinion.price > 0 && (
            <div className="opinion-price-row">
              <span className="opinion-price">${opinion.price?.toFixed(2)}</span>
              <span className={`opinion-change ${opinion.day_change > 0 ? "up" : opinion.day_change < 0 ? "down" : ""}`}>
                {opinion.day_change > 0 ? "+" : ""}{((opinion.day_change ?? 0) * 100).toFixed(2)}%
              </span>
            </div>
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
