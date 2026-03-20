export default function WatchlistBriefing({ data, isLoading, error }) {
  const hasItems = data && Array.isArray(data.items) && data.items.length > 0;

  return (
    <section id="watchlist-briefing" className="panel">
      <h2>Watchlist Briefing (AI)</h2>

      {isLoading && (
        <p>Generating briefing from latest scores…</p>
      )}

      {error && (
        <p className="error-text">
          Failed to generate watchlist briefing: {error}
        </p>
      )}

      {!isLoading && !error && data && (
        <>
          <p className="detail-note">
            {data.summary}
          </p>
          <p className="detail-meta">
            Watchlist: {data.tickers.join(", ")} · Generated at {data.generated_at}
          </p>

          {hasItems ? (
            <div className="watchlist-briefing-grid">
              {data.items.map((item) => (
                <div key={item.ticker} className="watchlist-briefing-card">
                  <div className="watchlist-briefing-header">
                    <span className="watchlist-briefing-ticker">{item.ticker}</span>
                    {item.stance && (
                      <span className="pill pill--soft">
                        {item.stance}
                      </span>
                    )}
                  </div>
                  {item.rationale && (
                    <p className="watchlist-briefing-text">{item.rationale}</p>
                  )}
                  {Array.isArray(item.key_risks) && item.key_risks.length > 0 && (
                    <ul className="watchlist-briefing-risks">
                      {item.key_risks.map((risk, idx) => (
                        <li key={idx}>{risk}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p>No active briefing items for the current watchlist.</p>
          )}
        </>
      )}
    </section>
  );
}

